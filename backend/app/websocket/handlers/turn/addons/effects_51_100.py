"""
Active addon effects for addon numbers 51-100.
"""
from app.websocket.manager import manager
from app.websocket.game_helpers import _error, _broadcast_state
from app.models.card import BossCard
from app.game import engine
from app.game.engine_addons import has_addon as _has_addon_addon


async def handle_effects_51_100(addon_number, game, user_id, data, player, pa, db) -> bool:
    """
    Handle active addon effects for addon numbers 51-100.
    Returns True if the addon was handled, False otherwise.
    """

    # Addon 51 (Change Set): discard up to 3 cards from hand and draw the same number
    if addon_number == 51:
        _discard_ids51 = data.get("hand_card_ids", [])
        if not _discard_ids51 or len(_discard_ids51) > 3:
            await _error(game.code, user_id, "Provide 1-3 hand card IDs")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC51
        _to_discard51 = []
        for _hcid51 in _discard_ids51:
            _hc51 = db.get(_PHC51, _hcid51)
            if not _hc51 or _hc51.player_id != player.id:
                await _error(game.code, user_id, "Card not in your hand")
                pa.is_tapped = False
                return "done"
            _to_discard51.append(_hc51)
        _count51 = len(_to_discard51)
        for _hc51 in _to_discard51:
            game.action_discard = (game.action_discard or []) + [_hc51.action_card_id]
            db.delete(_hc51)
        for _ in range(_count51):
            if game.action_deck_1:
                _new_card51 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _new_card51 = game.action_deck_2.pop(0)
            else:
                break
            db.add(_PHC51(player_id=player.id, action_card_id=_new_card51))

    # Addon 53 (Version Control): once per game, recover last played card from discard to hand
    elif addon_number == 53:
        _cs53 = player.combat_state or {}
        if _cs53.get("version_control_used"):
            await _error(game.code, user_id, "Version Control already used this game")
            pa.is_tapped = False
            return "done"
        _last_id53 = _cs53.get("last_discarded_card_id")
        if not _last_id53:
            await _error(game.code, user_id, "No card to recover")
            pa.is_tapped = False
            return "done"
        if _last_id53 in (game.action_discard or []):
            _discard53 = list(game.action_discard)
            _discard53.remove(_last_id53)
            game.action_discard = _discard53
            from app.models.game import PlayerHandCard as _PHC53
            db.add(_PHC53(player_id=player.id, action_card_id=_last_id53))
        _cs53_new = dict(_cs53)
        _cs53_new["version_control_used"] = True
        _cs53_new.pop("last_discarded_card_id", None)
        player.combat_state = _cs53_new

    # Addon 55 (Data Loader Pro): once per game, draw 5 action cards
    elif addon_number == 55:
        _cs55 = player.combat_state or {}
        if _cs55.get("data_loader_used"):
            await _error(game.code, user_id, "Data Loader Pro already used this game")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC55
        _drawn55 = 0
        for _ in range(5):
            if game.action_deck_1:
                _cid55 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _cid55 = game.action_deck_2.pop(0)
            else:
                break
            db.add(_PHC55(player_id=player.id, action_card_id=_cid55))
            _drawn55 += 1
        _cs55_new = dict(_cs55)
        _cs55_new["data_loader_used"] = True
        player.combat_state = _cs55_new

    # Addon 62 (Field Audit Trail): once per turn, look at a target player's full hand
    elif addon_number == 62:
        _target_id62 = data.get("target_player_id")
        _target62 = next((p for p in game.players if p.id == _target_id62), None)
        if not _target62 or _target62.id == player.id:
            await _error(game.code, user_id, "Invalid target for Field Audit Trail")
            pa.is_tapped = False
            return "done"
        _hand62 = [{"id": hc.id, "action_card_id": hc.action_card_id} for hc in _target62.hand]
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "field_audit_trail_result",
            "target_player_id": _target62.id,
            "hand": _hand62,
        })
        await _broadcast_state(game, db)
        return "done"

    # Addon 63 (Sharing Rules): once per turn, peek at opponent's hand and copy one card
    elif addon_number == 63:
        _target_id63 = data.get("target_player_id")
        _target63 = next((p for p in game.players if p.id == _target_id63), None)
        if not _target63 or _target63.id == player.id:
            await _error(game.code, user_id, "Invalid target for Sharing Rules")
            pa.is_tapped = False
            return "done"
        _cs63 = dict(player.combat_state or {})
        _cs63["sharing_rules_pending_target_id"] = _target63.id
        player.combat_state = _cs63
        _hand63 = [{"id": hc.id, "action_card_id": hc.action_card_id} for hc in _target63.hand]
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "sharing_rules_peek",
            "target_player_id": _target63.id,
            "hand": _hand63,
        })
        await _broadcast_state(game, db)
        return "done"  # wait for sharing_rules_pick

    # Addon 64 (Role Hierarchy): PASSIVO — effetto automatico in play.py
    # Quando un avversario gioca una carta contro di te, se la tua seniority è maggiore, l'effetto è dimezzato.
    # Tipo Passivo: non si tappa, è sempre attivo.

    # Addon 66 (Trust Layer): once per game, protect from opponent cards for 1 turn
    elif addon_number == 66:
        _cs66 = player.combat_state or {}
        if _cs66.get("trust_layer_used"):
            await _error(game.code, user_id, "Trust Layer already used this game")
            pa.is_tapped = False
            return "done"
        _cs66_new = dict(_cs66)
        _cs66_new["trust_layer_used"] = True
        _cs66_new["trust_layer_active"] = True
        player.combat_state = _cs66_new

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

    # Addon 74 (Before/After Save Hook): discard 1 card and draw 1 new one (treat as Attivo)
    elif addon_number == 74:
        target_hc_id74 = data.get("hand_card_id")
        if not target_hc_id74:
            await _error(game.code, user_id, "Provide hand_card_id to discard")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC74
        hc74 = db.get(_PHC74, target_hc_id74)
        if not hc74 or hc74.player_id != player.id:
            await _error(game.code, user_id, "Card not in your hand")
            pa.is_tapped = False
            return "done"
        game.action_discard = (game.action_discard or []) + [hc74.action_card_id]
        db.delete(hc74)
        _new74 = None
        if game.action_deck_1:
            _new74 = game.action_deck_1.pop(0)
        elif game.action_deck_2:
            _new74 = game.action_deck_2.pop(0)
        if _new74 is not None:
            db.add(_PHC74(player_id=player.id, action_card_id=_new74))

    # Addon 81 (Boss Vulnerability Scan): once per combat, next dice roll has +4 bonus
    elif addon_number == 81:
        cs81 = player.combat_state or {}
        if cs81.get("vulnerability_scan_used"):
            await _error(game.code, user_id, "Boss Vulnerability Scan already used this combat")
            pa.is_tapped = False
            return "done"
        if not player.is_in_combat:
            await _error(game.code, user_id, "Must be in combat to use Boss Vulnerability Scan")
            pa.is_tapped = False
            return "done"
        cs81_new = dict(cs81)
        cs81_new["vulnerability_scan_used"] = True
        cs81_new["vulnerability_scan_bonus"] = 4
        player.combat_state = cs81_new

    # Addon 82 (Deployment Freeze): once per game, send current boss back to bottom of deck
    elif addon_number == 82:
        cs82 = player.combat_state or {}
        if cs82.get("deployment_freeze_used"):
            await _error(game.code, user_id, "Deployment Freeze already used this game")
            pa.is_tapped = False
            return "done"
        if not player.is_in_combat or not player.current_boss_id:
            await _error(game.code, user_id, "Must be in active combat to use Deployment Freeze")
            pa.is_tapped = False
            return "done"
        boss_id82 = player.current_boss_id
        source82 = player.current_boss_source
        if source82 and "2" in str(source82):
            game.boss_deck_2 = (game.boss_deck_2 or []) + [boss_id82]
        else:
            game.boss_deck_1 = (game.boss_deck_1 or []) + [boss_id82]
        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        player.current_boss_source = None
        player.combat_round = None
        cs82_new = dict(cs82)
        cs82_new["deployment_freeze_used"] = True
        player.combat_state = cs82_new
        from app.models.game import TurnPhase as _TP82
        game.current_phase = _TP82.action

    # Addon 85 (Instance Refresh): once per game, send just-drawn boss back to bottom of deck
    elif addon_number == 85:
        cs85 = player.combat_state or {}
        if cs85.get("instance_refresh_used"):
            await _error(game.code, user_id, "Instance Refresh already used this game")
            pa.is_tapped = False
            return "done"
        if not player.is_in_combat or not player.current_boss_id:
            await _error(game.code, user_id, "Must be in active combat to use Instance Refresh")
            pa.is_tapped = False
            return "done"
        boss_id85 = player.current_boss_id
        source85 = player.current_boss_source
        if source85 and "2" in str(source85):
            game.boss_deck_2 = (game.boss_deck_2 or []) + [boss_id85]
        else:
            game.boss_deck_1 = (game.boss_deck_1 or []) + [boss_id85]
        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        player.current_boss_source = None
        player.combat_round = None
        cs85_new = dict(cs85)
        cs85_new["instance_refresh_used"] = True
        player.combat_state = cs85_new
        from app.models.game import TurnPhase as _TP85
        game.current_phase = _TP85.action

    # Addon 88 (Mass Update Override): once per game, deal 2 HP damage to any boss in active combat
    elif addon_number == 88:
        cs88 = player.combat_state or {}
        if cs88.get("mass_update_used"):
            await _error(game.code, user_id, "Mass Update Override already used this game")
            pa.is_tapped = False
            return "done"
        target_id88 = data.get("target_player_id", player.id)
        target88 = next((p for p in game.players if p.id == target_id88), None)
        if not target88 or not target88.is_in_combat:
            await _error(game.code, user_id, "Target not in combat")
            pa.is_tapped = False
            return "done"
        target88.current_boss_hp = max(0, (target88.current_boss_hp or 0) - 2)
        cs88_new = dict(cs88)
        cs88_new["mass_update_used"] = True
        player.combat_state = cs88_new
        # If boss is defeated, let next roll resolve it (hp is 0)

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

    # Addon 90 (Org Split): once per game, give half HP (floor) to opponent to weaken them
    elif addon_number == 90:
        cs90 = player.combat_state or {}
        if cs90.get("org_split_used"):
            await _error(game.code, user_id, "Org Split already used")
            pa.is_tapped = False
            return "done"
        target_id90 = data.get("target_player_id")
        target90 = next((p for p in game.players if p.id == target_id90), None)
        if not target90 or target90.id == player.id:
            await _error(game.code, user_id, "Invalid target for Org Split")
            pa.is_tapped = False
            return "done"
        hp_transfer90 = player.hp // 2
        if hp_transfer90 <= 0:
            await _error(game.code, user_id, "Not enough HP to split")
            pa.is_tapped = False
            return "done"
        player.hp -= hp_transfer90
        target90.hp = max(0, target90.hp - hp_transfer90)
        cs90_new = dict(cs90)
        cs90_new["org_split_used"] = True
        player.combat_state = cs90_new

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

    # Addon 99 (Retrospective): once per game, discard 2 cards from target opponent's hand
    elif addon_number == 99:
        cs99 = player.combat_state or {}
        if cs99.get("retrospective_used"):
            await _error(game.code, user_id, "Retrospective already used")
            pa.is_tapped = False
            return "done"
        target_id99 = data.get("target_player_id")
        target99 = next((p for p in game.players if p.id == target_id99), None)
        if not target99 or target99.id == player.id:
            await _error(game.code, user_id, "Invalid target")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC99
        hand99 = list(target99.hand)
        discard_count99 = min(2, len(hand99))
        if discard_count99 == 0:
            await _error(game.code, user_id, "Target has no cards")
            pa.is_tapped = False
            return "done"
        import random as _random99
        to_discard99 = _random99.sample(hand99, discard_count99)
        for hc99 in to_discard99:
            game.action_discard = (game.action_discard or []) + [hc99.action_card_id]
            db.delete(hc99)
        cs99_new = dict(cs99)
        cs99_new["retrospective_used"] = True
        player.combat_state = cs99_new

    else:
        return False

    return True
