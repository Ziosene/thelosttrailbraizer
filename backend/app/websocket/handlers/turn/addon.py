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
from app.game.engine_addons import has_addon as _has_addon_addon


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

    # Addon 11 (Revenue Intelligence): other players with this addon earn +1L on each addon purchase
    for _other11 in game.players:
        if _other11.id != player.id and _has_addon_addon(_other11, 11):
            _other11.licenze += 1

    # Addon 12 (CPQ Engine): buying this addon sets next purchase to 5L
    if addon.number == 12:
        _cs12 = dict(player.combat_state or {})
        _cs12["next_addon_price_fixed"] = 5
        player.combat_state = _cs12

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

    # ── Active addon effects (1-20) ──────────────────────────────────────────

    # Addon 3 (Einstein Prediction): reroll next dice roll (flag consumed in roll.py)
    if addon.number == 3:
        if not player.is_in_combat:
            await _error(game.code, user_id, "Einstein Prediction can only be used during combat")
            pa.is_tapped = False
            return
        _cs3 = dict(player.combat_state or {})
        _cs3["einstein_prediction_pre_reroll"] = True
        player.combat_state = _cs3

    # Addon 9 (Debug Mode): once per game, send boss back to bottom of deck
    elif addon.number == 9:
        _cs9 = player.combat_state or {}
        if _cs9.get("debug_mode_used"):
            await _error(game.code, user_id, "Debug Mode already used this game")
            pa.is_tapped = False
            return
        if not player.is_in_combat or not player.current_boss_id:
            await _error(game.code, user_id, "Debug Mode can only be used when in combat (right after drawing a boss)")
            pa.is_tapped = False
            return
        boss_id_9 = player.current_boss_id
        source_9 = player.current_boss_source
        if source_9 in ("deck_1", "market_1"):
            game.boss_deck_1 = (game.boss_deck_1 or []) + [boss_id_9]
        else:
            game.boss_deck_2 = (game.boss_deck_2 or []) + [boss_id_9]
        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        player.current_boss_source = None
        player.combat_round = None
        from app.models.game import TurnPhase as _TP9
        game.current_phase = _TP9.action
        cs9_new = dict(_cs9)
        cs9_new["debug_mode_used"] = True
        player.combat_state = cs9_new

    # Addon 13 (AppExchange Marketplace): once per game, peek 3 addons from deck and pick 1
    elif addon.number == 13:
        _cs13 = player.combat_state or {}
        if _cs13.get("appexchange_used"):
            await _error(game.code, user_id, "AppExchange Marketplace already used this game")
            pa.is_tapped = False
            return
        choices_13 = []
        _deck13_1 = list(game.addon_deck_1 or [])
        _deck13_2 = list(game.addon_deck_2 or [])
        for _ in range(3):
            if _deck13_1:
                choices_13.append(_deck13_1.pop(0))
            elif _deck13_2:
                choices_13.append(_deck13_2.pop(0))
        if not choices_13:
            await _error(game.code, user_id, "No addons available in decks")
            pa.is_tapped = False
            return
        game.addon_deck_1 = _deck13_1
        game.addon_deck_2 = _deck13_2
        cs13_new = dict(_cs13)
        cs13_new["appexchange_pending"] = choices_13
        cs13_new["appexchange_used"] = True
        player.combat_state = cs13_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "appexchange_choices",
            "player_id": player.id,
            "addon_ids": choices_13,
        })
        await _broadcast_state(game, db)
        return  # don't broadcast addon_used yet — wait for pick

    # Addon 18 (Field History Tracking): recover last discarded card to hand
    elif addon.number == 18:
        _cs18 = player.combat_state or {}
        _last_id18 = _cs18.get("last_discarded_card_id")
        if not _last_id18:
            await _error(game.code, user_id, "No discarded card to recover")
            pa.is_tapped = False
            return
        _discard18 = list(game.action_discard or [])
        if _last_id18 in _discard18:
            _discard18.remove(_last_id18)
            game.action_discard = _discard18
            from app.models.game import PlayerHandCard as _PHC18
            db.add(_PHC18(player_id=player.id, action_card_id=_last_id18))
        cs18_new = dict(_cs18)
        cs18_new.pop("last_discarded_card_id", None)
        player.combat_state = cs18_new

    # Addon 24 (Einstein Next Best Action): once per combat, skip a round — neutral
    elif addon.number == 24:
        cs24 = player.combat_state or {}
        if cs24.get("einstein_nba_used"):
            await _error(game.code, user_id, "Einstein Next Best Action already used this combat")
            pa.is_tapped = False
            return
        if not player.is_in_combat:
            await _error(game.code, user_id, "Can only use during combat")
            pa.is_tapped = False
            return
        cs24_new = dict(cs24)
        cs24_new["einstein_nba_used"] = True
        cs24_new["skip_next_round_neutral"] = True
        player.combat_state = cs24_new

    # Addon 26 (Slack Connect): once per turn, pass 1 card from hand to any player
    elif addon.number == 26:
        target_id26 = data.get("target_player_id")
        hand_card_id26 = data.get("hand_card_id")
        target26 = next((p for p in game.players if p.id == target_id26), None)
        if not target26 or target26.id == player.id:
            await _error(game.code, user_id, "Invalid target player")
            pa.is_tapped = False
            return
        from app.models.game import PlayerHandCard as _PHC26
        hc26 = db.get(_PHC26, hand_card_id26)
        if not hc26 or hc26.player_id != player.id:
            await _error(game.code, user_id, "Card not in your hand")
            pa.is_tapped = False
            return
        hc26.player_id = target26.id

    # Addon 29 (Einstein Copilot): once per game, roll 3 dice — for each ≥8, gain 1 cert (max 2)
    elif addon.number == 29:
        cs29 = player.combat_state or {}
        if cs29.get("einstein_copilot_used"):
            await _error(game.code, user_id, "Einstein Copilot already used this game")
            pa.is_tapped = False
            return
        rolls29 = [engine.roll_d10() for _ in range(3)]
        certs_gained = min(2, sum(1 for r in rolls29 if r >= 8))
        player.certificazioni += certs_gained
        cs29_new = dict(cs29)
        cs29_new["einstein_copilot_used"] = True
        player.combat_state = cs29_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "einstein_copilot_result",
            "player_id": player.id,
            "rolls": rolls29,
            "certs_gained": certs_gained,
        })
        await _broadcast_state(game, db)
        return

    # Addon 33 (Governor Limit Bypass): once per combat, roll 3 dice — hits deal separate damage
    elif addon.number == 33:
        cs33 = player.combat_state or {}
        if cs33.get("governor_bypass_used"):
            await _error(game.code, user_id, "Governor Limit Bypass already used this combat")
            pa.is_tapped = False
            return
        if not player.is_in_combat or not player.current_boss_id:
            await _error(game.code, user_id, "Can only use during combat")
            pa.is_tapped = False
            return
        boss33 = db.get(BossCard, player.current_boss_id)
        if not boss33:
            pa.is_tapped = False
            return
        threshold33 = boss33.dice_threshold
        rolls33 = [engine.roll_d10() for _ in range(3)]
        hits33 = sum(1 for r in rolls33 if r >= threshold33)
        boss_hp_lost33 = 0
        if hits33 > 0:
            player.current_boss_hp = max(0, (player.current_boss_hp or 0) - hits33)
            boss_hp_lost33 = hits33
        cs33_new = dict(cs33)
        cs33_new["governor_bypass_used"] = True
        player.combat_state = cs33_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "governor_bypass_result",
            "player_id": player.id,
            "rolls": rolls33,
            "hits": hits33,
            "boss_hp_lost": boss_hp_lost33,
        })
        # If boss is defeated, set a flag — roll.py will handle on next roll, or handle here
        if (player.current_boss_hp or 0) <= 0:
            from app.websocket.handlers.combat.roll import _boss_defeat_sequence as _bds33
            boss33_fresh = db.get(BossCard, player.current_boss_id)
            if boss33_fresh:
                await _bds33(player, game, db, boss33_fresh)
        db.commit()
        db.refresh(game)
        await _broadcast_state(game, db)
        return

    # Addon 37 (Deployment Pipeline): once per turn, allow 1 extra action card play
    elif addon.number == 37:
        cs37 = dict(player.combat_state or {})
        cs37["deployment_pipeline_extra_card"] = True
        player.combat_state = cs37

    # Addon 19 (Chatter Feed): show your hand to a target and request a card
    elif addon.number == 19:
        _target19_id = data.get("target_player_id")
        _target19 = next((p for p in game.players if p.id == _target19_id), None)
        if not _target19 or _target19.id == player.id:
            await _error(game.code, user_id, "Invalid target for Chatter Feed")
            pa.is_tapped = False
            return
        _cs19_req = dict(player.combat_state or {})
        _cs19_req["chatter_feed_pending_from_id"] = player.id
        player.combat_state = _cs19_req
        _cs19_tgt = dict(_target19.combat_state or {})
        _cs19_tgt["chatter_feed_pending_requester_id"] = player.id
        _target19.combat_state = _cs19_tgt
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, _target19.user_id, {
            "type": "chatter_feed_request",
            "requester_id": player.id,
            "requester_hand": [
                {"id": hc19.id, "action_card_id": hc19.action_card_id}
                for hc19 in player.hand
            ],
        })
        await _broadcast_state(game, db)
        return  # wait for chatter_feed_respond

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_USED,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name, "effect": addon.effect},
    })
    await _broadcast_state(game, db)


async def _handle_appexchange_pick(game, user_id: int, data: dict, db):
    """Handle the player picking one addon from AppExchange Marketplace choices."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    pending = list(cs.get("appexchange_pending") or [])
    if not pending:
        await _error(game.code, user_id, "No AppExchange choice pending")
        return
    chosen_id = data.get("addon_id")
    if chosen_id not in pending:
        await _error(game.code, user_id, "Invalid addon choice")
        return
    from app.models.game import PlayerAddon as _PAex
    db.add(_PAex(player_id=player.id, addon_id=chosen_id))
    # Return unchosen addons to front of deck_1
    for aid in pending:
        if aid != chosen_id:
            game.addon_deck_1 = [aid] + (game.addon_deck_1 or [])
    cs_new = dict(cs)
    cs_new.pop("appexchange_pending", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_BOUGHT,
        "player_id": player.id,
        "addon": {"id": chosen_id},
        "source": "appexchange",
    })
    await _broadcast_state(game, db)


async def _handle_chatter_feed_respond(game, user_id: int, data: dict, db):
    """Handle the target responding to a Chatter Feed card request."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    responder = _get_player(game, user_id)
    if not responder:
        return
    cs_resp = responder.combat_state or {}
    requester_id = cs_resp.get("chatter_feed_pending_requester_id")
    if not requester_id:
        await _error(game.code, user_id, "No Chatter Feed request pending")
        return
    requester19 = next((p for p in game.players if p.id == requester_id), None)
    if not requester19:
        return
    hand_card_id19 = data.get("hand_card_id")
    from app.models.game import PlayerHandCard as _PHC19r
    hc19r = db.get(_PHC19r, hand_card_id19)
    if not hc19r or hc19r.player_id != responder.id:
        await _error(game.code, user_id, "Card not in your hand")
        return
    # Transfer card to requester
    hc19r.player_id = requester19.id
    # Clear flags
    cs_resp_new = dict(cs_resp)
    cs_resp_new.pop("chatter_feed_pending_requester_id", None)
    responder.combat_state = cs_resp_new
    cs_req19 = dict(requester19.combat_state or {})
    cs_req19.pop("chatter_feed_pending_from_id", None)
    requester19.combat_state = cs_req19
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)
