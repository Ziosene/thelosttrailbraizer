"""
Active addon effects — economy category (licenze and certifications).
Addons: 29, 101, 120, 134, 140, 153, 158, 159, 166, 169, 187
"""
from app.websocket.manager import manager
from app.websocket.game_helpers import _error, _broadcast_state
from app.game import engine
from app.game.engine_addons import has_addon as _has_addon_addon


async def handle_economy_effects(addon_number, game, user_id, data, player, pa, db) -> bool | str:
    """
    Handle active addon effects for the economy category.
    Returns 'done' if it already did commit+broadcast, True if state was modified, False if not handled.
    """

    # Addon 29 (Einstein Copilot): once per game, roll 3 dice — for each ≥8, gain 1 cert (max 2)
    if addon_number == 29:
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

    # Addon 101 (Org-Wide Sharing): once per turn, a player gains +1L
    elif addon_number == 101:
        target_id101 = data.get("target_player_id", player.id)
        target101 = next((p for p in game.players if p.id == target_id101), None)
        if not target101:
            await _error(game.code, user_id, "Invalid target")
            pa.is_tapped = False
            return "done"
        target101.licenze += 1

    # Addon 120 (Scheduled Flow): declare 2-4 turns; when they expire, gain that many L
    elif addon_number == 120:
        declared120 = data.get("turns_declared")
        if declared120 not in (2, 3, 4):
            await _error(game.code, user_id, "Declare 2, 3 or 4 turns")
            pa.is_tapped = False
            return "done"
        cs120 = dict(player.combat_state or {})
        if cs120.get("scheduled_flow_countdown") is not None:
            await _error(game.code, user_id, "Scheduled Flow already running")
            pa.is_tapped = False
            return "done"
        cs120["scheduled_flow_countdown"] = declared120
        cs120["scheduled_flow_reward"] = declared120
        player.combat_state = cs120

    # Addon 134 (Major Release): once per game, roll dice: ≥6 → +3L; ≤5 → draw 2 cards
    elif addon_number == 134:
        cs134 = player.combat_state or {}
        if cs134.get("major_release_used"):
            await _error(game.code, user_id, "Major Release already used this game")
            pa.is_tapped = False
            return "done"
        roll134 = engine.roll_d10()
        cs134_new = dict(cs134)
        cs134_new["major_release_used"] = True
        player.combat_state = cs134_new
        if roll134 >= 6:
            player.licenze += 3
        else:
            from app.models.game import PlayerHandCard as _PHC134
            for _ in range(2):
                if game.action_deck:
                    cid134 = game.action_deck.pop(0)
                else:
                    break
                db.add(_PHC134(player_id=player.id, action_card_id=cid134))
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "major_release_roll",
            "player_id": player.id,
            "roll": roll134,
        })
        await _broadcast_state(game, db)
        return "done"

    # Addon 140 (OmniScript): once per game, roll 2 dice, gain L equal to sum (max 20)
    elif addon_number == 140:
        cs140 = player.combat_state or {}
        if cs140.get("omniscript_used"):
            await _error(game.code, user_id, "OmniScript already used this game")
            pa.is_tapped = False
            return "done"
        r1_140 = engine.roll_d10()
        r2_140 = engine.roll_d10()
        gain140 = min(r1_140 + r2_140, 20)
        player.licenze += gain140
        cs140_new = dict(cs140)
        cs140_new["omniscript_used"] = True
        player.combat_state = cs140_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "omniscript_roll",
            "player_id": player.id,
            "roll_1": r1_140,
            "roll_2": r2_140,
            "gain": gain140,
        })
        await _broadcast_state(game, db)
        return "done"

    # Addon 153 (Certification Theft Ring): steal 1 cert from opponent; roll ≤3 → fail and lose 3L
    elif addon_number == 153:
        cs153 = player.combat_state or {}
        if cs153.get("cert_theft_used"):
            await _error(game.code, user_id, "Certification Theft Ring already used this game")
            pa.is_tapped = False
            return "done"
        target_id153 = data.get("target_player_id")
        target153 = next((p for p in game.players if p.id == target_id153), None)
        if not target153 or target153.id == player.id:
            await _error(game.code, user_id, "Invalid target for Certification Theft Ring")
            pa.is_tapped = False
            return "done"
        # Addon 200 (The Lost Trailbraizer): cert theft immunity
        if _has_addon_addon(target153, 200):
            await _error(game.code, user_id, "Target is protected by The Lost Trailbraizer")
            pa.is_tapped = False
            return "done"
        # Addon 157 (Portfolio Defense): immune to cert theft during own turn
        if _has_addon_addon(target153, 157):
            _is_target_turn153 = (
                bool(game.turn_order) and
                game.turn_order[game.current_turn_index] == target153.id
            )
            if _is_target_turn153:
                await _error(game.code, user_id, "Target is protected by Portfolio Defense during their turn")
                pa.is_tapped = False
                return "done"
        roll153 = engine.roll_d10()
        cs153_new = dict(cs153)
        cs153_new["cert_theft_used"] = True
        player.combat_state = cs153_new
        if roll153 <= 3:
            player.licenze = max(0, player.licenze - 3)
            success153 = False
        else:
            if target153.certificazioni > 0:
                # Addon 154 (Recertification): target gains 5L when losing a cert
                if _has_addon_addon(target153, 154):
                    target153.licenze += 5
                target153.certificazioni -= 1
                player.certificazioni += 1
            success153 = True
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "cert_theft_result",
            "player_id": player.id,
            "target_id": target153.id,
            "roll": roll153,
            "success": success153,
        })
        await _broadcast_state(game, db)
        return "done"

    # Addon 158 (Credential Vault): roll dice; if 10, gain 1 cert
    elif addon_number == 158:
        cs158 = player.combat_state or {}
        if cs158.get("cred_vault_used"):
            await _error(game.code, user_id, "Credential Vault already used this game")
            pa.is_tapped = False
            return "done"
        roll158 = engine.roll_d10()
        cs158_new = dict(cs158)
        cs158_new["cred_vault_used"] = True
        player.combat_state = cs158_new
        if roll158 == 10:
            player.certificazioni += 1
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "credential_vault_roll",
            "player_id": player.id,
            "roll": roll158,
            "success": roll158 == 10,
        })
        await _broadcast_state(game, db)
        return "done"

    # Addon 159 (Final Exam): dice duel with opponent; winner steals 1 cert from loser
    elif addon_number == 159:
        cs159 = player.combat_state or {}
        if cs159.get("final_exam_used"):
            await _error(game.code, user_id, "Final Exam already used this game")
            pa.is_tapped = False
            return "done"
        target_id159 = data.get("target_player_id")
        target159 = next((p for p in game.players if p.id == target_id159), None)
        if not target159 or target159.id == player.id:
            await _error(game.code, user_id, "Invalid target for Final Exam")
            pa.is_tapped = False
            return "done"
        # Addon 200 (The Lost Trailbraizer): cert theft immunity
        if _has_addon_addon(target159, 200):
            await _error(game.code, user_id, "Target is protected by The Lost Trailbraizer")
            pa.is_tapped = False
            return "done"
        roll_p159 = engine.roll_d10()
        roll_t159 = engine.roll_d10()
        cs159_new = dict(cs159)
        cs159_new["final_exam_used"] = True
        player.combat_state = cs159_new
        if roll_p159 > roll_t159:
            if target159.certificazioni > 0:
                if _has_addon_addon(target159, 154):  # Recertification
                    target159.licenze += 5
                target159.certificazioni -= 1
                player.certificazioni += 1
        elif roll_t159 > roll_p159:
            if player.certificazioni > 0:
                if _has_addon_addon(player, 154):  # Recertification
                    player.licenze += 5
                player.certificazioni -= 1
                target159.certificazioni += 1
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "final_exam_result",
            "player_id": player.id,
            "target_id": target159.id,
            "player_roll": roll_p159,
            "target_roll": roll_t159,
        })
        await _broadcast_state(game, db)
        return "done"

    # Addon 166 (Parallel Career): gain certifications × 3 Licenze
    elif addon_number == 166:
        cs166 = player.combat_state or {}
        if cs166.get("parallel_career_used"):
            await _error(game.code, user_id, "Parallel Career already used this game")
            pa.is_tapped = False
            return "done"
        gain166 = player.certificazioni * 3
        player.licenze += gain166
        cs166_new = dict(cs166)
        cs166_new["parallel_career_used"] = True
        player.combat_state = cs166_new

    # Addon 169 (Performance Review): compare boss defeats with target
    elif addon_number == 169:
        cs169 = player.combat_state or {}
        if cs169.get("perf_review_used"):
            await _error(game.code, user_id, "Performance Review already used this game")
            pa.is_tapped = False
            return "done"
        target_id169 = data.get("target_player_id")
        target169 = next((p for p in game.players if p.id == target_id169), None)
        if not target169 or target169.id == player.id:
            await _error(game.code, user_id, "Invalid target for Performance Review")
            pa.is_tapped = False
            return "done"
        _my_defeats169 = player.bosses_defeated or (player.combat_state or {}).get("boss_defeats_count", 0)
        _their_defeats169 = target169.bosses_defeated or (target169.combat_state or {}).get("boss_defeats_count", 0)
        cs169_new = dict(cs169)
        cs169_new["perf_review_used"] = True
        player.combat_state = cs169_new
        if _their_defeats169 > _my_defeats169:
            player.licenze += 3
            outcome169 = "licenze"
        elif _my_defeats169 > _their_defeats169:
            cs169_new["perf_review_cert_bonus"] = True  # score bonus, not actual cert
            player.combat_state = cs169_new
            outcome169 = "cert_bonus"
        else:
            outcome169 = "tie"
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "perf_review_result",
            "player_id": player.id,
            "target_id": target169.id,
            "outcome": outcome169,
        })
        await _broadcast_state(game, db)
        return "done"

    # Addon 187 (Dreamforce Keynote): gain 1L per addon owned (once per game)
    elif addon_number == 187:
        cs187 = player.combat_state or {}
        if cs187.get('keynote_used'):
            await _error(game.code, user_id, "Dreamforce Keynote already used this game")
            pa.is_tapped = False
            return "done"
        player.licenze += len(list(player.addons))
        cs187_new = dict(cs187)
        cs187_new['keynote_used'] = True
        player.combat_state = cs187_new

    else:
        return False

    return True
