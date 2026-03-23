"""
Active addon effects — combat category.
Addons: 3, 9, 24, 33, 81, 82, 85, 88, 115, 141, 142, 143 (comment only), 146, 175, 178, 194
"""
from app.websocket.manager import manager
from app.websocket.game_helpers import _error, _broadcast_state
from app.models.card import BossCard
from app.game import engine


async def handle_combat_effects(addon_number, game, user_id, data, player, pa, db) -> bool | str:
    """
    Handle active addon effects for the combat category.
    Returns 'done' if it already did commit+broadcast, True if state was modified, False if not handled.
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

    # Addon 9 (Debug Mode): once per turn — peek top boss from deck, decide to fight or send to bottom
    elif addon_number == 9:
        if player.is_in_combat:
            await _error(game.code, user_id, "Debug Mode cannot be used while in combat")
            pa.is_tapped = False
            return "done"
        from app.models.game import TurnPhase as _TP9
        if game.current_phase != _TP9.action:
            await _error(game.code, user_id, "Debug Mode can only be used during the action phase")
            pa.is_tapped = False
            return "done"
        # Pop top boss from deck 1, fallback deck 2
        _deck1_9 = list(game.boss_deck_1 or [])
        _deck2_9 = list(game.boss_deck_2 or [])
        if _deck1_9:
            _boss_id_9 = _deck1_9[0]
            _source_9 = "deck_1"
            game.boss_deck_1 = _deck1_9[1:]
        elif _deck2_9:
            _boss_id_9 = _deck2_9[0]
            _source_9 = "deck_2"
            game.boss_deck_2 = _deck2_9[1:]
        else:
            await _error(game.code, user_id, "No boss available in any deck")
            pa.is_tapped = False
            return "done"
        _boss9 = db.get(BossCard, _boss_id_9)
        _cs9_new = dict(player.combat_state or {})
        _cs9_new["debug_mode_peek_boss_id"] = _boss_id_9
        _cs9_new["debug_mode_peek_source"] = _source_9
        player.combat_state = _cs9_new
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "debug_mode_peek",
            "boss_id": _boss_id_9,
            "boss_name": _boss9.name if _boss9 else "?",
            "boss_hp": _boss9.hp if _boss9 else 0,
            "boss_threshold": _boss9.dice_threshold if _boss9 else 0,
            "boss_ability": _boss9.ability if _boss9 else "",
            "boss_difficulty": _boss9.difficulty if _boss9 else "",
            "source": _source_9,
        })
        await _broadcast_state(game, db)
        return "done"

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

    # Addon 115 (Future Method): next dice roll is doubled (capped at 10)
    elif addon_number == 115:
        if not player.is_in_combat:
            await _error(game.code, user_id, "Must be in combat to use Future Method")
            pa.is_tapped = False
            return "done"
        cs115 = dict(player.combat_state or {})
        if cs115.get("future_method_active"):
            await _error(game.code, user_id, "Future Method already active")
            pa.is_tapped = False
            return "done"
        cs115["future_method_active"] = True
        player.combat_state = cs115

    # Addon 141 (Calculated Risk): before rolling, declare a bet; ≥8 → +5L; ≤3 → -2L
    elif addon_number == 141:
        if not player.is_in_combat:
            await _error(game.code, user_id, "Must be in combat to use Calculated Risk")
            pa.is_tapped = False
            return "done"
        cs141 = dict(player.combat_state or {})
        if cs141.get("calculated_risk_active"):
            await _error(game.code, user_id, "Calculated Risk already active this combat")
            pa.is_tapped = False
            return "done"
        cs141["calculated_risk_active"] = True
        player.combat_state = cs141

    # Addon 142 (All or Nothing): skip this dice round, gain +4 to next roll
    elif addon_number == 142:
        if not player.is_in_combat:
            await _error(game.code, user_id, "Must be in combat to use All or Nothing")
            pa.is_tapped = False
            return "done"
        cs142 = dict(player.combat_state or {})
        if cs142.get("all_or_nothing_pending"):
            await _error(game.code, user_id, "All or Nothing already charging")
            pa.is_tapped = False
            return "done"
        cs142["all_or_nothing_pending"] = True
        player.combat_state = cs142
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {"type": "all_or_nothing_charging", "player_id": player.id})
        await _broadcast_state(game, db)
        return "done"

    # Addon 143 (Double or Nothing): handled in _boss_defeat_sequence — passive trigger
    # (no manual use effect needed here; the addon is Attivo but triggers on boss defeat)

    # Addon 146 (Bet the Farm): once per game, dice duel with opponent — higher steals 3L
    elif addon_number == 146:
        cs146 = player.combat_state or {}
        if cs146.get("bet_farm_used"):
            await _error(game.code, user_id, "Bet the Farm already used this game")
            pa.is_tapped = False
            return "done"
        target_id146 = data.get("target_player_id")
        target146 = next((p for p in game.players if p.id == target_id146), None)
        if not target146 or target146.id == player.id:
            await _error(game.code, user_id, "Invalid target for Bet the Farm")
            pa.is_tapped = False
            return "done"
        roll_p146 = engine.roll_d10()
        roll_t146 = engine.roll_d10()
        if roll_p146 > roll_t146:
            stolen146 = min(3, target146.licenze)
            target146.licenze -= stolen146
            player.licenze += stolen146
            winner_id146 = player.id
        elif roll_t146 > roll_p146:
            stolen146 = min(3, player.licenze)
            player.licenze -= stolen146
            target146.licenze += stolen146
            winner_id146 = target146.id
        else:
            stolen146 = 0
            winner_id146 = None  # tie
        cs146_new = dict(cs146)
        cs146_new["bet_farm_used"] = True
        player.combat_state = cs146_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "bet_farm_result",
            "player_id": player.id,
            "target_id": target146.id,
            "player_roll": roll_p146,
            "target_roll": roll_t146,
            "winner_id": winner_id146,
            "licenze_stolen": stolen146,
        })
        await _broadcast_state(game, db)
        return "done"

    # Addon 175 (Boss Reshuffle): reshuffle the boss deck completely
    elif addon_number == 175:
        cs175 = player.combat_state or {}
        if cs175.get("boss_reshuffle_used"):
            await _error(game.code, user_id, "Boss Reshuffle already used this game")
            pa.is_tapped = False
            return "done"
        import random as _r175
        if game.boss_deck_1:
            _deck175_1 = list(game.boss_deck_1)
            _r175.shuffle(_deck175_1)
            game.boss_deck_1 = _deck175_1
        if game.boss_deck_2:
            _deck175_2 = list(game.boss_deck_2)
            _r175.shuffle(_deck175_2)
            game.boss_deck_2 = _deck175_2
        cs175_new = dict(cs175)
        cs175_new["boss_reshuffle_used"] = True
        player.combat_state = cs175_new

    # Addon 178 (Cold Cache): current boss loses 3HP
    elif addon_number == 178:
        cs178 = player.combat_state or {}
        if cs178.get("cold_cache_used"):
            await _error(game.code, user_id, "Cold Cache already used this game")
            pa.is_tapped = False
            return "done"
        if not player.is_in_combat or player.current_boss_hp is None:
            await _error(game.code, user_id, "Not in combat")
            pa.is_tapped = False
            return "done"
        player.current_boss_hp = max(0, player.current_boss_hp - 3)
        cs178_new = dict(cs178)
        cs178_new["cold_cache_used"] = True
        player.combat_state = cs178_new
        if player.current_boss_hp <= 0:
            from app.models.card import BossCard as _BC178
            boss178 = db.get(_BC178, player.current_boss_id)
            if boss178:
                from app.websocket.handlers.combat.roll import _boss_defeat_sequence as _bds178
                db.commit()
                db.refresh(game)
                await _bds178(player, game, db, boss178)
                return "done"

    # Addon 194 (Lorem Ipsum Boss): auto-win placeholder boss, gain 2L (once per game)
    elif addon_number == 194:
        cs194 = player.combat_state or {}
        if cs194.get('lorem_ipsum_used'):
            await _error(game.code, user_id, "Lorem Ipsum Boss already used this game")
            pa.is_tapped = False
            return "done"
        if player.is_in_combat:
            await _error(game.code, user_id, "Already in combat")
            pa.is_tapped = False
            return "done"
        player.licenze += 2
        cs194_new = dict(cs194)
        cs194_new['lorem_ipsum_used'] = True
        player.combat_state = cs194_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "lorem_ipsum_boss_defeated",
            "player_id": player.id,
            "licenze_gained": 2,
        })
        await _broadcast_state(game, db)
        return "done"

    else:
        return False

    return True
