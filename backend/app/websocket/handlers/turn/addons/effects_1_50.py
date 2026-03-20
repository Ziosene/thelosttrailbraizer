"""
Active addon effects for addon numbers 1-50.
"""
from app.websocket.manager import manager
from app.websocket.game_helpers import _error, _broadcast_state
from app.models.card import BossCard
from app.game import engine
from app.game.engine_addons import has_addon as _has_addon_addon


async def handle_effects_1_50(addon_number, game, user_id, data, player, pa, db) -> bool:
    """
    Handle active addon effects for addon numbers 1-50.
    Returns True if the addon was handled, False otherwise.
    """

    # Addon 3 (Einstein Prediction): reroll next dice roll (flag consumed in roll.py)
    if addon_number == 3:
        if not player.is_in_combat:
            await _error(game.code, user_id, "Einstein Prediction can only be used during combat")
            pa.is_tapped = False
            return "done"
        _cs3 = dict(player.combat_state or {})
        _cs3["einstein_prediction_pre_reroll"] = True
        player.combat_state = _cs3

    # Addon 9 (Debug Mode): once per game, send boss back to bottom of deck
    elif addon_number == 9:
        _cs9 = player.combat_state or {}
        if _cs9.get("debug_mode_used"):
            await _error(game.code, user_id, "Debug Mode already used this game")
            pa.is_tapped = False
            return "done"
        if not player.is_in_combat or not player.current_boss_id:
            await _error(game.code, user_id, "Debug Mode can only be used when in combat (right after drawing a boss)")
            pa.is_tapped = False
            return "done"
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
    elif addon_number == 13:
        _cs13 = player.combat_state or {}
        if _cs13.get("appexchange_used"):
            await _error(game.code, user_id, "AppExchange Marketplace already used this game")
            pa.is_tapped = False
            return "done"
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
            return "done"
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
        return True  # don't broadcast addon_used yet — wait for pick

    # Addon 18 (Field History Tracking): recover last discarded card to hand
    elif addon_number == 18:
        _cs18 = player.combat_state or {}
        _last_id18 = _cs18.get("last_discarded_card_id")
        if not _last_id18:
            await _error(game.code, user_id, "No discarded card to recover")
            pa.is_tapped = False
            return "done"
        _discard18 = list(game.action_discard or [])
        if _last_id18 in _discard18:
            _discard18.remove(_last_id18)
            game.action_discard = _discard18
            from app.models.game import PlayerHandCard as _PHC18
            db.add(_PHC18(player_id=player.id, action_card_id=_last_id18))
        cs18_new = dict(_cs18)
        cs18_new.pop("last_discarded_card_id", None)
        player.combat_state = cs18_new

    # Addon 19 (Chatter Feed): show your hand to a target and request a card
    elif addon_number == 19:
        _target19_id = data.get("target_player_id")
        _target19 = next((p for p in game.players if p.id == _target19_id), None)
        if not _target19 or _target19.id == player.id:
            await _error(game.code, user_id, "Invalid target for Chatter Feed")
            pa.is_tapped = False
            return "done"
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
        return "done"  # wait for chatter_feed_respond

    # Addon 24 (Einstein Next Best Action): once per combat, skip a round — neutral
    elif addon_number == 24:
        cs24 = player.combat_state or {}
        if cs24.get("einstein_nba_used"):
            await _error(game.code, user_id, "Einstein Next Best Action already used this combat")
            pa.is_tapped = False
            return "done"
        if not player.is_in_combat:
            await _error(game.code, user_id, "Can only use during combat")
            pa.is_tapped = False
            return "done"
        cs24_new = dict(cs24)
        cs24_new["einstein_nba_used"] = True
        cs24_new["skip_next_round_neutral"] = True
        player.combat_state = cs24_new

    # Addon 26 (Slack Connect): once per turn, pass 1 card from hand to any player
    elif addon_number == 26:
        target_id26 = data.get("target_player_id")
        hand_card_id26 = data.get("hand_card_id")
        target26 = next((p for p in game.players if p.id == target_id26), None)
        if not target26 or target26.id == player.id:
            await _error(game.code, user_id, "Invalid target player")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC26
        hc26 = db.get(_PHC26, hand_card_id26)
        if not hc26 or hc26.player_id != player.id:
            await _error(game.code, user_id, "Card not in your hand")
            pa.is_tapped = False
            return "done"
        hc26.player_id = target26.id

    # Addon 29 (Einstein Copilot): once per game, roll 3 dice — for each ≥8, gain 1 cert (max 2)
    elif addon_number == 29:
        cs29 = player.combat_state or {}
        if cs29.get("einstein_copilot_used"):
            await _error(game.code, user_id, "Einstein Copilot already used this game")
            pa.is_tapped = False
            return "done"
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
        return "done"

    # Addon 33 (Governor Limit Bypass): once per combat, roll 3 dice — hits deal separate damage
    elif addon_number == 33:
        cs33 = player.combat_state or {}
        if cs33.get("governor_bypass_used"):
            await _error(game.code, user_id, "Governor Limit Bypass already used this combat")
            pa.is_tapped = False
            return "done"
        if not player.is_in_combat or not player.current_boss_id:
            await _error(game.code, user_id, "Can only use during combat")
            pa.is_tapped = False
            return "done"
        boss33 = db.get(BossCard, player.current_boss_id)
        if not boss33:
            pa.is_tapped = False
            return "done"
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
        return "done"

    # Addon 37 (Deployment Pipeline): once per turn, allow 1 extra action card play
    elif addon_number == 37:
        cs37 = dict(player.combat_state or {})
        cs37["deployment_pipeline_extra_card"] = True
        player.combat_state = cs37

    # Addon 45 (CPQ Advanced): once per game, set next addon price to 0
    elif addon_number == 45:
        _cs45 = player.combat_state or {}
        if _cs45.get("cpq_advanced_used"):
            await _error(game.code, user_id, "CPQ Advanced already used this game")
            pa.is_tapped = False
            return "done"
        _cs45_new = dict(_cs45)
        _cs45_new["cpq_advanced_used"] = True
        _cs45_new["next_addon_price_fixed"] = 0
        player.combat_state = _cs45_new

    # Addon 49 (Metadata API): look at top 3 cards of action deck and reorder them
    elif addon_number == 49:
        _deck49 = game.action_deck_1 or game.action_deck_2
        _choices49 = (game.action_deck_1 or [])[:3]
        if not _choices49:
            await _error(game.code, user_id, "No cards in deck")
            pa.is_tapped = False
            return "done"
        _cs49 = dict(player.combat_state or {})
        _cs49["metadata_api_pending"] = list(_choices49)
        player.combat_state = _cs49
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "metadata_api_peek",
            "player_id": player.id,
            "card_ids": list(_choices49),
        })
        await _broadcast_state(game, db)
        return "done"  # wait for metadata_api_reorder

    # Addon 50 (Tooling API): once per game, recover up to 2 cards from discard to hand
    elif addon_number == 50:
        _cs50 = player.combat_state or {}
        if _cs50.get("tooling_api_used"):
            await _error(game.code, user_id, "Tooling API already used this game")
            pa.is_tapped = False
            return "done"
        _discard50 = list(game.action_discard or [])
        if not _discard50:
            await _error(game.code, user_id, "Discard pile is empty")
            pa.is_tapped = False
            return "done"
        _recover50 = _discard50[-2:] if len(_discard50) >= 2 else _discard50[:]
        game.action_discard = _discard50[:-len(_recover50)]
        from app.models.game import PlayerHandCard as _PHC50
        for _cid50 in _recover50:
            db.add(_PHC50(player_id=player.id, action_card_id=_cid50))
        _cs50_new = dict(_cs50)
        _cs50_new["tooling_api_used"] = True
        player.combat_state = _cs50_new

    else:
        return False

    return True
