"""
Addon handlers: buy addon and use addon.
"""
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.models.card import AddonCard, BossCard
from app.game import engine


async def _handle_buy_addon(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.action:
        await _error(game.code, user_id, "Cannot buy addon now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    # source: "market_1" | "market_2" | "deck_1" | "deck_2"
    source = data.get("source", "market_1")
    if source not in ("market_1", "market_2", "deck_1", "deck_2"):
        await _error(game.code, user_id, "Invalid source (market_1/market_2/deck_1/deck_2)")
        return

    if source == "market_1":
        if not game.addon_market_1:
            await _error(game.code, user_id, "No addon in market slot 1")
            return
        addon_id = game.addon_market_1
    elif source == "market_2":
        if not game.addon_market_2:
            await _error(game.code, user_id, "No addon in market slot 2")
            return
        addon_id = game.addon_market_2
    elif source == "deck_1":
        if not game.addon_deck_1:
            await _error(game.code, user_id, "Addon deck 1 is empty")
            return
        addon_id = game.addon_deck_1.pop(0)
    else:  # deck_2
        if not game.addon_deck_2:
            await _error(game.code, user_id, "Addon deck 2 is empty")
            return
        addon_id = game.addon_deck_2.pop(0)

    addon = db.get(AddonCard, addon_id)
    if not addon:
        await _error(game.code, user_id, "Addon not found")
        return

    # Card 18 (Org Takeover): opponent blocked this player from buying addons next turn
    if (player.combat_state or {}).get("addons_blocked_next_turn"):
        await _error(game.code, user_id, "Addon purchases blocked this turn (Org Takeover)")
        return

    # Card 139 (Prospect Lifecycle): addon purchases blocked until next boss defeat
    if (player.combat_state or {}).get("addons_blocked_until_boss_defeat"):
        await _error(game.code, user_id, "Addon purchases blocked until you defeat a boss (Prospect Lifecycle)")
        return

    # Card 189 (Delete Records): specific addon IDs blocked from repurchase for N turns
    _blocked_addon_ids = list((player.combat_state or {}).get("deleted_addon_blocked_ids") or [])
    if addon_id in _blocked_addon_ids:
        await _error(game.code, user_id, "This addon was deleted and cannot be repurchased yet (Delete Records)")
        return

    # Boss 60 (Connected App Infiltrator): addon purchases are blocked during this combat
    if player.is_in_combat and player.current_boss_id:
        if engine.boss_blocks_addon_purchase(player.current_boss_id):
            await _error(game.code, user_id, "Addon purchases are blocked by the boss")
            return

    cost = addon.cost + (player.pending_addon_cost_penalty or 0)
    # Card 272 (ISV Ecosystem): fix next addon cost to 5 for this turn (one-shot)
    if (player.combat_state or {}).get("isv_ecosystem_active"):
        cost = 5
        _cs_isv = dict(player.combat_state)
        _cs_isv.pop("isv_ecosystem_active", None)
        player.combat_state = _cs_isv
    # Card 47 (Contracted Price): fix next addon cost to 5 (overrides base cost + penalty)
    _price_fixed = (player.combat_state or {}).get("next_addon_price_fixed")
    if _price_fixed is not None:
        cost = _price_fixed
    else:
        # Card 48 (Price Rule): reduce next addon cost by N
        _price_discount = (player.combat_state or {}).get("next_addon_price_discount", 0)
        cost = max(0, cost - _price_discount)
        # Card 124 (Price Book): halve next addon cost (floor, min 5)
        if (player.combat_state or {}).get("next_addon_price_half"):
            cost = max(5, cost // 2)
        # Card 161 (Promotions Engine): -2L addon cost for N turns
        if (player.combat_state or {}).get("promotions_engine_turns_remaining", 0) > 0:
            cost = max(1, cost - 2)
        # Card 154 (Sustainability Cloud): discount = HP lost since card played
        _sus_hp_lost = (player.combat_state or {}).get("sustainability_hp_lost", 0)
        if _sus_hp_lost > 0 and (player.combat_state or {}).get("sustainability_discount_pending"):
            cost = max(1, cost - _sus_hp_lost)
            _cs_sus_buy = dict(player.combat_state)
            _cs_sus_buy.pop("sustainability_discount_pending", None)
            _cs_sus_buy.pop("sustainability_hp_lost", None)
            player.combat_state = _cs_sus_buy
    if player.licenze < cost:
        await _error(game.code, user_id, f"Need {cost} Licenze (have {player.licenze})")
        return

    player.licenze -= cost
    player.pending_addon_cost_penalty = 0  # penalty consumed on first purchase (boss 26)
    # Card 87 (Block Pricing): track cumulative addon spend for payout calculation
    cs_spend = dict(player.combat_state or {})
    cs_spend["total_addon_licenze_spent"] = cs_spend.get("total_addon_licenze_spent", 0) + cost
    player.combat_state = cs_spend
    # Consume addon price modifiers
    _cs_price = player.combat_state or {}
    if _price_fixed is not None or _cs_price.get("next_addon_price_discount", 0) or _cs_price.get("next_addon_price_half"):
        cs_addon = dict(_cs_price)
        cs_addon.pop("next_addon_price_fixed", None)
        cs_addon.pop("next_addon_price_discount", None)
        cs_addon.pop("next_addon_price_half", None)
        player.combat_state = cs_addon

    # Bought addons are tracked as owned by player; market slot gets refilled
    if source == "market_1":
        game.addon_market_1 = game.addon_deck_1.pop(0) if game.addon_deck_1 else None
    elif source == "market_2":
        game.addon_market_2 = game.addon_deck_2.pop(0) if game.addon_deck_2 else None
    # deck_1 / deck_2: card already popped above, nothing else to do

    from app.models.game import PlayerAddon
    db.add(PlayerAddon(player_id=player.id, addon_id=addon_id))

    # Card 160 (Storefront Reference): mark that this player bought an addon this turn
    _cs_bat = dict(player.combat_state or {})
    _cs_bat["bought_addon_this_turn"] = True
    player.combat_state = _cs_bat

    # TODO: triggherare gli addon passivi con trigger "quando acquisti un addon" (sia il nuovo che quelli già posseduti).
    # Alcuni addon esistenti danno bonus al momento dell'acquisto di un nuovo addon.
    # Va chiamata trigger_passive_addons(event="on_addon_bought", player, game, new_addon=addon, db).
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_BOUGHT,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name},
    })
    await _broadcast_state(game, db)


async def _handle_use_addon(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase not in (TurnPhase.action, TurnPhase.combat):
        await _error(game.code, user_id, "Cannot use addon now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    player_addon_id = data.get("player_addon_id")
    from app.models.game import PlayerAddon
    pa = db.get(PlayerAddon, player_addon_id)
    if not pa or pa.player_id != player.id:
        await _error(game.code, user_id, "Addon not owned by you")
        return

    addon = db.get(AddonCard, pa.addon_id)
    if not addon:
        await _error(game.code, user_id, "Addon not found")
        return

    if addon.addon_type.value != "Attivo":
        await _error(game.code, user_id, "Only active addons can be used manually")
        return

    if pa.is_tapped:
        await _error(game.code, user_id, "Addon is tapped (already used this turn)")
        return

    # Boss 31 (AppExchange Parasite): locked addon cannot be used during this fight
    if player.is_in_combat and player.combat_state:
        if player.combat_state.get("locked_addon_id") == pa.id:
            await _error(game.code, user_id, "This addon is locked by the boss for this fight")
            return

    # Boss 15 (trust.salesforce.DOOM) / Boss 79 (ISVForce Overlord): ALL addons disabled
    for p in game.players:
        if p.is_in_combat and p.current_boss_id:
            p_round = (p.combat_round or 0) + 1
            if engine.boss_disables_all_addons(p.current_boss_id, combat_round=p_round):
                await _error(game.code, user_id, "All addons are disabled while this boss is in play")
                return

    # Boss 4 (Cursed Friday Deployment) / Boss 77 (SFDX Imp): combatant's addons disabled
    if player.is_in_combat and player.current_boss_id:
        current_round = (player.combat_round or 0) + 1
        if engine.boss_addons_disabled(player.current_boss_id, current_round):
            await _error(game.code, user_id, "Addons are disabled by the boss this round")
            return

    pa.is_tapped = True

    # Card 185 (Record Triggered Flow): other players watching earn 1L when this player uses an addon
    for _watcher in game.players:
        if _watcher.id != player.id:
            _rtf = (_watcher.combat_state or {}).get("record_triggered_flow_remaining", 0)
            if _rtf > 0:
                _watcher.licenze += 1
                _wc_rtf = dict(_watcher.combat_state)
                _wc_rtf["record_triggered_flow_remaining"] = _rtf - 1
                if _wc_rtf["record_triggered_flow_remaining"] <= 0:
                    _wc_rtf.pop("record_triggered_flow_remaining", None)
                    _wc_rtf.pop("record_triggered_flow_watcher_id", None)
                _watcher.combat_state = _wc_rtf

    # Boss 49 (Managed Package Leech): boss heals 1 HP every time combatant activates an addon
    if player.is_in_combat and player.current_boss_id:
        boss_for_addon = db.get(BossCard, player.current_boss_id)
        heal = engine.boss_heals_on_addon_use(player.current_boss_id)
        if heal > 0 and boss_for_addon:
            player.current_boss_hp = min(boss_for_addon.hp, (player.current_boss_hp or 0) + heal)

    db.commit()
    db.refresh(game)

    # TODO: implementare gli effetti di tutti i 200 addon attivi.
    # Attualmente l'addon viene tappato ma il suo effetto NON viene applicato.
    # Ogni addon va gestito per nome (addon.name) o numero (addon.number) in
    # una funzione dedicata tipo apply_addon_effect(addon, player, game, db).
    # Gli addon Passivi hanno effetti che si attivano automaticamente in
    # determinati momenti del gioco (roll_dice, acquisto, inizio turno, ecc.)
    # e vanno anch'essi implementati nei punti giusti del flusso.
    # Vedere cards/addon_cards.md per l'effetto completo di ogni addon.

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_USED,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name, "effect": addon.effect},
    })
    await _broadcast_state(game, db)
