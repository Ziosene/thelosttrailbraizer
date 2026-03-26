"""
Addon buy handler: _handle_buy_addon.
"""
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.models.card import AddonCard
from app.game import engine
from app.game.engine_addons import has_addon as _has_addon_addon


async def _handle_buy_addon(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Cannot buy addon now")
        return
    # Addon 111 (Quick Deploy): allow buying addons during combat phase too
    _player_111 = _get_player(game, user_id)
    _allow_combat_buy = _player_111 and _has_addon_addon(_player_111, 111)
    if game.current_phase not in (TurnPhase.action,) and not (game.current_phase == TurnPhase.combat and _allow_combat_buy):
        await _error(game.code, user_id, "Cannot buy addon now")
        return

    player = _get_player(game, user_id)
    _fomo_bypass = player and (player.combat_state or {}).get("fomo_bypass_turn", False)
    if not player or (not _is_player_turn(game, player) and not _fomo_bypass):
        await _error(game.code, user_id, "Not your turn")
        return

    # source: "market_1" | "market_2" | "deck"
    source = data.get("source", "market_1")
    if source not in ("market_1", "market_2", "deck"):
        await _error(game.code, user_id, "Invalid source (market_1/market_2/deck)")
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
    else:  # deck
        if not game.addon_deck:
            await _error(game.code, user_id, "Addon deck is empty")
            return
        addon_id = game.addon_deck.pop(0)

    addon = db.get(AddonCard, addon_id)
    if not addon:
        await _error(game.code, user_id, "Addon not found")
        return

    # Addon 200 (The Lost Trailbraizer): block buying other addons while holding it
    if addon.number != 200 and _has_addon_addon(player, 200):
        await _error(game.code, user_id, "The Lost Trailbraizer: cannot buy addons while holding this card")
        return

    # Addon 200 (The Lost Trailbraizer): block others buying it if already owned
    if addon.number == 200:
        for _p200 in game.players:
            if _p200.id != player.id and _has_addon_addon(_p200, 200):
                await _error(game.code, user_id, "The Lost Trailbraizer is already owned by another player")
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
    # Addon 139 (Unmanaged Package): market costs +2L for all opponents of the player with this addon
    for _p139 in game.players:
        if _p139.id != player.id and _has_addon_addon(_p139, 139):
            cost += 2
            break  # one player with addon 139 is enough
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
    # Addon 80 (Field Dependency): if ≥3 addons owned, -2L on addon cost
    if _has_addon_addon(player, 80) and len(player.addons) >= 3:
        cost = max(0, cost - 2)

    # Addon 189 (ISV Ecosystem): if player owns ≥5 addons, new addons cost at most 5L
    if _has_addon_addon(player, 189) and len(list(player.addons)) >= 5:
        cost = min(cost, 5)

    # Role passive (Dev Lifecycle Architect / CTA): addon costs 8L instead of base 10
    from app.game import engine_role as _engine_role_buy
    _role_base_cost = addon.cost  # base cost before all modifiers
    if _role_base_cost == 10:  # only discount base-10-cost addons
        _role_cost = _engine_role_buy.get_addon_cost(player, cost)
        cost = min(cost, _role_cost)  # take the lower value

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

    # Addon 124 (Bulk API): check once-per-game bulk purchase slots
    _cs_buy124 = player.combat_state or {}
    _bulk_remaining = _cs_buy124.get("bulk_api_purchases_remaining", 0)
    if _bulk_remaining > 0:
        # Allow extra purchase, decrement counter
        _cs_new_buy124 = dict(_cs_buy124)
        _cs_new_buy124["bulk_api_purchases_remaining"] -= 1
        player.combat_state = _cs_new_buy124
    else:
        # Normal: check once-per-turn limit (not blocking for now — game uses bought_addon_this_turn
        # purely for information; actual enforcement done below if needed)
        pass

    # Bought addons are tracked as owned by player; market slot gets refilled
    if source == "market_1":
        game.addon_market_1 = game.addon_deck.pop(0) if game.addon_deck else None
    elif source == "market_2":
        game.addon_market_2 = game.addon_deck.pop(0) if game.addon_deck else None
    # deck: card already popped above, nothing else to do

    from app.models.game import PlayerAddon
    db.add(PlayerAddon(player_id=player.id, addon_id=addon_id))

    # Addon 198 (Trailhead Hoodie): cosmetic — on acquisition gain 1L once
    if addon.number == 198:
        player.licenze += 1

    # Addon 11 (Revenue Intelligence): other players with this addon earn +1L on each addon purchase
    for _other11 in game.players:
        if _other11.id != player.id and _has_addon_addon(_other11, 11):
            _other11.licenze += 1

    # Addon 12 (CPQ Engine): buying this addon sets next purchase to 5L
    if addon.number == 12:
        _cs12 = dict(player.combat_state or {})
        _cs12["next_addon_price_fixed"] = 5
        player.combat_state = _cs12

    # Addon 58 (High Availability): initialize 2 miss-absorb charges when acquired
    if addon.number == 58:
        _cs58_buy = dict(player.combat_state or {})
        _cs58_buy["ha_misses_remaining"] = 2
        player.combat_state = _cs58_buy

    # Card 160 (Storefront Reference): mark that this player bought an addon this turn
    _cs_bat = dict(player.combat_state or {})
    _cs_bat["bought_addon_this_turn"] = True
    player.combat_state = _cs_bat

    # Passive addon triggers on_addon_bought: handled above (addon 11, 12, 110, 147, 160).

    # Flush so we can reference the new PlayerAddon id for addon 92
    db.flush()
    from app.models.game import PlayerAddon as _PA_bought
    new_pa = db.query(_PA_bought).filter(
        _PA_bought.player_id == player.id,
        _PA_bought.addon_id == addon_id,
    ).order_by(_PA_bought.id.desc()).first()

    # Track addon acquisition turn for addon 133 (Winter Release) and 136 (Package Upgrade)
    # Always record acquisition turn in buyer's combat_state so future addons are covered
    if new_pa:
        _cs_acq = dict(player.combat_state or {})
        _aq_turns = dict(_cs_acq.get("addon_acquired_turns", {}))
        _aq_turns[str(new_pa.id)] = game.turn_number
        _cs_acq["addon_acquired_turns"] = _aq_turns
        player.combat_state = _cs_acq

    # Addon 151 (Certification Path): when this addon is bought, set pending flag for first cert
    if addon.number == 151:
        cs151_buy = dict(player.combat_state or {})
        cs151_buy["cert_path_double_pending"] = True
        player.combat_state = cs151_buy

    # Addon 92 (Beta Feature): offer to reject just-bought addon and draw another
    if _has_addon_addon(player, 92) and new_pa:
        cs92 = dict(player.combat_state or {})
        cs92["beta_feature_pending_pa_id"] = new_pa.id
        cs92["beta_feature_pending_addon_id"] = addon_id
        player.combat_state = cs92
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "beta_feature_option",
            "addon_card_id": addon_id,
            "message": "You can reject this addon and draw another",
        })
        await _broadcast_state(game, db)
        return

    # Addon 110 (Go-Live Celebration): all players gain 1L on any addon purchase
    for _p110 in game.players:
        if _has_addon_addon(_p110, 110):
            _cs110 = _p110.combat_state or {}
            _first110 = not _cs110.get("go_live_bought_this_turn")
            for _all110 in game.players:
                _all110.licenze += 1
            if player.id == _p110.id and _first110:
                player.licenze += 2  # extra 2 (already got 1 from loop above, total 3)
            _cs110_new = dict(_cs110)
            _cs110_new["go_live_bought_this_turn"] = True
            _p110.combat_state = _cs110_new
            break

    # Addon 147 (FOMO Trigger): when any opponent buys an addon, others with 147 can buy one immediately
    for _p147 in game.players:
        if _p147.id != player.id and _has_addon_addon(_p147, 147):
            cs147 = dict(_p147.combat_state or {})
            cs147["fomo_trigger_pending"] = True
            _p147.combat_state = cs147

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_BOUGHT,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name},
    })
    await _broadcast_state(game, db)
