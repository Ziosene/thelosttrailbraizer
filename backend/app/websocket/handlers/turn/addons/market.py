"""
Active addon effects — market category.
Addons: 13, 45, 67, 89, 91, 93, 95, 108, 119, 124, 129, 130, 150
"""
from app.websocket.manager import manager
from app.websocket.game_helpers import _error, _broadcast_state
from app.game.engine_addons import has_addon as _has_addon_addon


async def handle_market_effects(addon_number, game, user_id, data, player, pa, db) -> bool | str:
    """
    Handle active addon effects for the market category.
    Returns 'done' if it already did commit+broadcast, True if state was modified, False if not handled.
    """

    # Addon 13 (AppExchange Marketplace): once per game, peek 3 addons from deck and pick 1
    if addon_number == 13:
        _cs13 = player.combat_state or {}
        if _cs13.get("appexchange_used"):
            await _error(game.code, user_id, "AppExchange Marketplace already used this game")
            pa.is_tapped = False
            return "done"
        choices_13 = []
        _deck13_1 = list(game.addon_deck or [])
        _deck13_2 = list(game.addon_deck or [])
        for _ in range(3):
            if _deck13_1:
                choices_13.append(_deck13_1.pop(0))
            elif _deck13_2:
                choices_13.append(_deck13_2.pop(0))
        if not choices_13:
            await _error(game.code, user_id, "No addons available in decks")
            pa.is_tapped = False
            return "done"
        game.addon_deck = _deck13_1
        game.addon_deck = _deck13_2
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

    # Addon 67 (Connected App Token): once per game, tap an opponent's addon for 1 turn
    elif addon_number == 67:
        _cs67 = player.combat_state or {}
        if _cs67.get("connected_app_used"):
            await _error(game.code, user_id, "Connected App Token already used this game")
            pa.is_tapped = False
            return "done"
        _target_id67 = data.get("target_player_id")
        _target_pa_id67 = data.get("target_addon_id")
        _target67 = next((p for p in game.players if p.id == _target_id67), None)
        if not _target67 or _target67.id == player.id:
            await _error(game.code, user_id, "Invalid target for Connected App Token")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerAddon as _PA67
        _target_pa67 = db.get(_PA67, _target_pa_id67)
        if not _target_pa67 or _target_pa67.player_id != _target67.id:
            await _error(game.code, user_id, "Addon not owned by target")
            pa.is_tapped = False
            return "done"
        # Addon 138 (Managed Package): target's addons are protected
        if _has_addon_addon(_target67, 138):
            await _error(game.code, user_id, "Target's addons are protected by Managed Package")
            pa.is_tapped = False
            return "done"
        _target_pa67.is_tapped = True
        _cs67_new = dict(_cs67)
        _cs67_new["connected_app_used"] = True
        player.combat_state = _cs67_new

    # Addon 89 (Data Migration Tool): once per game, swap one of your addons with an opponent's
    elif addon_number == 89:
        cs89 = player.combat_state or {}
        if cs89.get("data_migration_used"):
            await _error(game.code, user_id, "Data Migration Tool already used")
            pa.is_tapped = False
            return "done"
        my_pa_id89 = data.get("my_addon_id")
        their_pa_id89 = data.get("target_addon_id")
        from app.models.game import PlayerAddon as _PA89
        my_pa89 = db.get(_PA89, my_pa_id89)
        their_pa89 = db.get(_PA89, their_pa_id89)
        if not my_pa89 or my_pa89.player_id != player.id:
            await _error(game.code, user_id, "Invalid your addon")
            pa.is_tapped = False
            return "done"
        if not their_pa89 or their_pa89.player_id == player.id:
            await _error(game.code, user_id, "Invalid opponent addon")
            pa.is_tapped = False
            return "done"
        # Addon 138 (Managed Package): target's addons are protected
        _their_player89 = next((p for p in game.players if p.id == their_pa89.player_id), None)
        if _their_player89 and _has_addon_addon(_their_player89, 138):
            await _error(game.code, user_id, "Target's addons are protected by Managed Package")
            pa.is_tapped = False
            return "done"
        their_old_player_id = their_pa89.player_id
        my_pa89.player_id = their_old_player_id
        their_pa89.player_id = player.id
        cs89_new = dict(cs89)
        cs89_new["data_migration_used"] = True
        player.combat_state = cs89_new

    # Addon 91 (Free Trial): borrow a market addon for 1 full turn, then return it
    elif addon_number == 91:
        cs91 = player.combat_state or {}
        if cs91.get("free_trial_used"):
            await _error(game.code, user_id, "Free Trial already used")
            pa.is_tapped = False
            return "done"
        target_addon_id91 = data.get("target_addon_id")
        market91 = []
        if game.addon_market_1:
            market91.append(game.addon_market_1)
        if game.addon_market_2:
            market91.append(game.addon_market_2)
        if target_addon_id91 not in market91:
            await _error(game.code, user_id, "Addon not in market")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerAddon as _PA91
        temp_pa91 = _PA91(player_id=player.id, addon_id=target_addon_id91, is_tapped=False)
        db.add(temp_pa91)
        db.flush()
        cs91_new = dict(cs91)
        cs91_new["free_trial_used"] = True
        cs91_new["free_trial_borrowed_pa_id"] = temp_pa91.id
        cs91_new["free_trial_borrowed_addon_id"] = target_addon_id91
        player.combat_state = cs91_new

    # Addon 93 (Pilot Program): once per game, choose an addon from graveyard
    elif addon_number == 93:
        cs93 = player.combat_state or {}
        if cs93.get("pilot_program_used"):
            await _error(game.code, user_id, "Pilot Program already used")
            pa.is_tapped = False
            return "done"
        discard93 = list(game.addon_graveyard or [])
        if not discard93:
            await _error(game.code, user_id, "Addon graveyard is empty")
            pa.is_tapped = False
            return "done"
        cs93_new = dict(cs93)
        cs93_new["pilot_program_used"] = True
        cs93_new["pilot_program_pending"] = True
        player.combat_state = cs93_new
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "pilot_program_options",
            "addon_card_ids": discard93,
        })
        await _broadcast_state(game, db)
        return "done"

    # Addon 95 (Sprint Review): once per game, swap one of your addons with an opponent's
    elif addon_number == 95:
        cs95 = player.combat_state or {}
        if cs95.get("sprint_review_used"):
            await _error(game.code, user_id, "Sprint Review already used")
            pa.is_tapped = False
            return "done"
        my_pa_id95 = data.get("my_addon_id")
        their_pa_id95 = data.get("target_addon_id")
        from app.models.game import PlayerAddon as _PA95
        my_pa95 = db.get(_PA95, my_pa_id95)
        their_pa95 = db.get(_PA95, their_pa_id95)
        if not my_pa95 or my_pa95.player_id != player.id:
            await _error(game.code, user_id, "Invalid your addon")
            pa.is_tapped = False
            return "done"
        if not their_pa95 or their_pa95.player_id == player.id:
            await _error(game.code, user_id, "Invalid opponent addon")
            pa.is_tapped = False
            return "done"
        # Addon 138 (Managed Package): target's addons are protected
        _their_player95 = next((p for p in game.players if p.id == their_pa95.player_id), None)
        if _their_player95 and _has_addon_addon(_their_player95, 138):
            await _error(game.code, user_id, "Target's addons are protected by Managed Package")
            pa.is_tapped = False
            return "done"
        their_old_player_id = their_pa95.player_id
        my_pa95.player_id = their_old_player_id
        their_pa95.player_id = player.id
        cs95_new = dict(cs95)
        cs95_new["sprint_review_used"] = True
        player.combat_state = cs95_new

    # Addon 108 (Architecture Review): once per game, return up to 2 addons to deck, gain 8L each
    elif addon_number == 108:
        cs108 = player.combat_state or {}
        if cs108.get("architecture_review_used"):
            await _error(game.code, user_id, "Architecture Review already used")
            pa.is_tapped = False
            return "done"
        pa_ids108 = data.get("addon_ids", [])
        if not pa_ids108 or len(pa_ids108) > 2:
            await _error(game.code, user_id, "Provide 1-2 addon IDs to return")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerAddon as _PA108
        returned108 = 0
        for pa_id108 in pa_ids108:
            pa108 = db.get(_PA108, pa_id108)
            if not pa108 or pa108.player_id != player.id or pa108.id == pa.id:
                continue
            game.addon_deck = (game.addon_deck or []) + [pa108.addon_id]
            db.delete(pa108)
            player.licenze += 8
            returned108 += 1
        if returned108 == 0:
            await _error(game.code, user_id, "No valid addons to return")
            pa.is_tapped = False
            return "done"
        cs108_new = dict(cs108)
        cs108_new["architecture_review_used"] = True
        player.combat_state = cs108_new

    # Addon 119 (Queueable Job): once per game, buy any market addon for free
    elif addon_number == 119:
        cs119 = player.combat_state or {}
        if cs119.get("queueable_job_used"):
            await _error(game.code, user_id, "Queueable Job already used this game")
            pa.is_tapped = False
            return "done"
        target_addon_id119 = data.get("target_addon_id")
        market119 = []
        if game.addon_market_1:
            market119.append(game.addon_market_1)
        if game.addon_market_2:
            market119.append(game.addon_market_2)
        if target_addon_id119 not in market119:
            await _error(game.code, user_id, "Addon not in market")
            pa.is_tapped = False
            return "done"
        if game.addon_market_1 == target_addon_id119:
            game.addon_market_1 = game.addon_deck.pop(0) if game.addon_deck else (game.addon_deck.pop(0) if game.addon_deck else None)
        elif game.addon_market_2 == target_addon_id119:
            game.addon_market_2 = game.addon_deck.pop(0) if game.addon_deck else (game.addon_deck.pop(0) if game.addon_deck else None)
        from app.models.game import PlayerAddon as _PA119
        db.add(_PA119(player_id=player.id, addon_id=target_addon_id119, is_tapped=False))
        cs119_new = dict(cs119)
        cs119_new["queueable_job_used"] = True
        player.combat_state = cs119_new

    # Addon 124 (Bulk API): once per game, buy up to 3 addons in one turn ignoring 1-per-turn limit
    elif addon_number == 124:
        cs124 = player.combat_state or {}
        if cs124.get("bulk_api_used"):
            await _error(game.code, user_id, "Bulk API already used this game")
            pa.is_tapped = False
            return "done"
        cs124_new = dict(cs124)
        cs124_new["bulk_api_used"] = True
        cs124_new["bulk_api_purchases_remaining"] = 3
        player.combat_state = cs124_new

    # Addon 129 (Junction Object): once per turn, untap one of your tapped addons
    elif addon_number == 129:
        target_pa_id129 = data.get("target_addon_id")
        from app.models.game import PlayerAddon as _PA129
        target_pa129 = db.get(_PA129, target_pa_id129)
        if not target_pa129 or target_pa129.player_id != player.id:
            await _error(game.code, user_id, "Invalid addon for Junction Object")
            pa.is_tapped = False
            return "done"
        if not target_pa129.is_tapped:
            await _error(game.code, user_id, "Addon is not tapped")
            pa.is_tapped = False
            return "done"
        if target_pa129.id == pa.id:
            await _error(game.code, user_id, "Cannot untap itself")
            pa.is_tapped = False
            return "done"
        target_pa129.is_tapped = False

    # Addon 130 (External Object): once per game, choose addon from graveyard and acquire by paying cost
    elif addon_number == 130:
        cs130 = player.combat_state or {}
        if cs130.get("external_object_used"):
            await _error(game.code, user_id, "External Object already used this game")
            pa.is_tapped = False
            return "done"
        graveyard130 = list(game.addon_graveyard or [])
        if not graveyard130:
            await _error(game.code, user_id, "Addon graveyard is empty")
            pa.is_tapped = False
            return "done"
        cs130_new = dict(cs130)
        cs130_new["external_object_used"] = True
        cs130_new["external_object_pending"] = True
        player.combat_state = cs130_new
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "external_object_options",
            "addon_card_ids": graveyard130,
        })
        await _broadcast_state(game, db)
        return "done"

    # Addon 150 (Wildcards): for 1 full turn, play cards without limit and use all addons without limit
    elif addon_number == 150:
        cs150 = player.combat_state or {}
        if cs150.get("wildcards_used"):
            await _error(game.code, user_id, "Wildcards already used this game")
            pa.is_tapped = False
            return "done"
        cs150_new = dict(cs150)
        cs150_new["wildcards_used"] = True
        cs150_new["wildcards_active"] = True
        player.combat_state = cs150_new
        # With wildcards active, don't tap this addon (it stays available)
        pa.is_tapped = False

    else:
        return False

    return True
