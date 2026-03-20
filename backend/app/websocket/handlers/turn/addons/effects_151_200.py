"""
Active addon effects for addon numbers 151-200.
"""
from app.websocket.manager import manager
from app.websocket.game_helpers import _error, _broadcast_state
from app.game import engine
from app.game.engine_addons import has_addon as _has_addon_addon


async def handle_effects_151_200(addon_number, game, user_id, data, player, pa, db) -> bool:
    """
    Handle active addon effects for addon numbers 151-200.
    Returns True if the addon was handled, False otherwise.
    """

    # Addon 153 (Certification Theft Ring): steal 1 cert from opponent; roll ≤3 → fail and lose 3L
    if addon_number == 153:
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

    # Addon 164 (Cross-Training): once per game, use passive ability of any other player for 1 full turn
    elif addon_number == 164:
        cs164 = player.combat_state or {}
        if cs164.get("cross_training_used"):
            await _error(game.code, user_id, "Cross-Training already used this game")
            pa.is_tapped = False
            return "done"
        _other_players164 = [p for p in game.players if p.id != player.id and p.role]
        if not _other_players164:
            await _error(game.code, user_id, "No other players with roles available")
            pa.is_tapped = False
            return "done"
        _options164 = [{"player_id": p.id, "name": p.user.username if p.user else str(p.id), "role": p.role} for p in _other_players164]
        _cs164_new = dict(cs164)
        _cs164_new["cross_training_used"] = True
        player.combat_state = _cs164_new
        db.flush()
        await manager.broadcast(game.code, {
            "type": "passive_choice_required",
            "choice_type": "borrow_passive_full_turn",
            "player_id": user_id,
            "options": _options164
        })
        return "done"  # client responds with "use_borrowed_passive" action

    # Addon 165 (Skill Transfer): once per game, swap roles with an opponent for 2 turns
    elif addon_number == 165:
        cs165 = player.combat_state or {}
        if cs165.get("skill_transfer_used"):
            await _error(game.code, user_id, "Skill Transfer already used this game")
            pa.is_tapped = False
            return "done"
        _other_players165 = [p for p in game.players if p.id != player.id]
        if not _other_players165:
            await _error(game.code, user_id, "No other players available")
            pa.is_tapped = False
            return "done"
        _options165 = [{"player_id": p.id, "name": p.user.username if p.user else str(p.id), "role": p.role or "(no role)"} for p in _other_players165]
        # Return pending choice — player picks who to swap with
        _cs165_new = dict(cs165)
        _cs165_new["skill_transfer_used"] = True
        player.combat_state = _cs165_new
        db.flush()
        await manager.broadcast(game.code, {
            "type": "passive_choice_required",
            "choice_type": "skill_transfer_target",
            "player_id": user_id,
            "options": _options165
        })
        return "done"  # client responds with "skill_transfer_choice" action

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

    # Addon 170 (Promotion): increase seniority by 1 level for 5 turns
    elif addon_number == 170:
        cs170 = player.combat_state or {}
        if cs170.get("promotion_used"):
            await _error(game.code, user_id, "Promotion already used this game")
            pa.is_tapped = False
            return "done"
        from app.models.game import Seniority as _Sen170, SENIORITY_HP as _HP170
        _SENIORITY_LIST170 = [
            _Sen170.junior, _Sen170.experienced, _Sen170.senior, _Sen170.evangelist,
        ]
        cs170_new = dict(cs170)
        cs170_new["promotion_used"] = True
        cs170_new["promotion_turns_remaining"] = 5
        cs170_new["promotion_original_seniority"] = player.seniority.value if player.seniority else None
        # Temporarily increase seniority
        try:
            _cur_idx170 = _SENIORITY_LIST170.index(player.seniority)
            if _cur_idx170 < len(_SENIORITY_LIST170) - 1:
                _new_seniority170 = _SENIORITY_LIST170[_cur_idx170 + 1]
                player.seniority = _new_seniority170
                player.max_hp = _HP170[_new_seniority170]
                player.hp = min(player.hp + 1, player.max_hp)
        except (ValueError, TypeError):
            pass
        player.combat_state = cs170_new

    # Addon 171 (Mazzo Corrotto): each opponent loses 1L per card in hand (max 5L per opponent)
    elif addon_number == 171:
        cs171 = player.combat_state or {}
        if cs171.get("mazzo_corrotto_used"):
            await _error(game.code, user_id, "Mazzo Corrotto already used this game")
            pa.is_tapped = False
            return "done"
        for _p171 in game.players:
            if _p171.id == player.id:
                continue
            _hand_count171 = len(list(_p171.hand))
            _loss171 = min(_hand_count171, 5)
            _p171.licenze = max(0, _p171.licenze - _loss171)
        cs171_new = dict(cs171)
        cs171_new["mazzo_corrotto_used"] = True
        player.combat_state = cs171_new

    # Addon 172 (Deck Shuffle): shuffle the shared action deck (once per turn)
    elif addon_number == 172:
        import random as _r172
        if game.action_deck_1:
            _deck172_1 = list(game.action_deck_1)
            _r172.shuffle(_deck172_1)
            game.action_deck_1 = _deck172_1
        if game.action_deck_2:
            _deck172_2 = list(game.action_deck_2)
            _r172.shuffle(_deck172_2)
            game.action_deck_2 = _deck172_2

    # Addon 173 (Card Graveyard): passive — allow manual peek at action discard pile
    elif addon_number == 173:
        # This is a passive — no activation needed; allow manual "peek" action
        discard173 = list(game.action_discard or [])
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "card_graveyard_view",
            "discard_pile": discard173,
        })
        pa.is_tapped = False  # passive, don't tap
        return "done"

    # Addon 174 (Recycle Bin): put up to 2 cards from discard back to bottom of main deck
    elif addon_number == 174:
        card_ids174 = data.get("card_ids", [])
        if not card_ids174 or len(card_ids174) > 2:
            await _error(game.code, user_id, "Provide 1-2 card IDs from discard")
            pa.is_tapped = False
            return "done"
        discard174 = list(game.action_discard or [])
        for cid174 in card_ids174:
            if cid174 not in discard174:
                await _error(game.code, user_id, f"Card {cid174} not in discard")
                pa.is_tapped = False
                return "done"
            discard174.remove(cid174)
            if game.action_deck_1 is not None:
                game.action_deck_1 = game.action_deck_1 + [cid174]
            else:
                game.action_deck_2 = (game.action_deck_2 or []) + [cid174]
        game.action_discard = discard174

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

    # Addon 176 (Mazzo Infetto): target opponent discards entire hand and draws the same number
    elif addon_number == 176:
        cs176 = player.combat_state or {}
        if cs176.get("mazzo_infetto_used"):
            await _error(game.code, user_id, "Mazzo Infetto already used this game")
            pa.is_tapped = False
            return "done"
        target_id176 = data.get("target_player_id")
        target176 = next((p for p in game.players if p.id == target_id176), None)
        if not target176 or target176.id == player.id:
            await _error(game.code, user_id, "Invalid target for Mazzo Infetto")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC176
        _hand176 = list(target176.hand)
        _count176 = len(_hand176)
        for hc176 in _hand176:
            game.action_discard = (game.action_discard or []) + [hc176.action_card_id]
            db.delete(hc176)
        for _ in range(_count176):
            if game.action_deck_1:
                _cid176 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _cid176 = game.action_deck_2.pop(0)
            else:
                break
            db.add(_PHC176(player_id=target176.id, action_card_id=_cid176))
        cs176_new = dict(cs176)
        cs176_new["mazzo_infetto_used"] = True
        player.combat_state = cs176_new

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

    # Addon 179 (Hot Reload): discard entire hand, draw same number of cards
    elif addon_number == 179:
        from app.models.game import PlayerHandCard as _PHC179
        _hand179 = list(player.hand)
        _count179 = len(_hand179)
        if _count179 == 0:
            await _error(game.code, user_id, "Hand is empty")
            pa.is_tapped = False
            return "done"
        for hc179 in _hand179:
            game.action_discard = (game.action_discard or []) + [hc179.action_card_id]
            db.delete(hc179)
        for _ in range(_count179):
            if game.action_deck_1:
                _cid179 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _cid179 = game.action_deck_2.pop(0)
            else:
                break
            db.add(_PHC179(player_id=player.id, action_card_id=_cid179))

    # Addon 186 (Marc Benioff Mode): all players gain 3L and draw 1 card (once per game)
    elif addon_number == 186:
        cs186 = player.combat_state or {}
        if cs186.get('benioff_used'):
            await _error(game.code, user_id, "Marc Benioff Mode already used this game")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC186
        for _p186 in game.players:
            _p186.licenze += 3
            _cid186 = None
            if game.action_deck_1:
                _cid186 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _cid186 = game.action_deck_2.pop(0)
            if _cid186:
                db.add(_PHC186(player_id=_p186.id, action_card_id=_cid186))
        cs186_new = dict(cs186)
        cs186_new['benioff_used'] = True
        player.combat_state = cs186_new

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

    # Addon 191 (404 Not Found): for 1 turn opponents can't target you and you can't start combat (once per game)
    elif addon_number == 191:
        cs191 = player.combat_state or {}
        if cs191.get('not_found_used'):
            await _error(game.code, user_id, "404 Not Found already used this game")
            pa.is_tapped = False
            return "done"
        cs191_new = dict(cs191)
        cs191_new['not_found_used'] = True
        cs191_new['not_found_active'] = True
        player.combat_state = cs191_new

    # Addon 193 (Stack Trace): draw 4 cards (once per game)
    elif addon_number == 193:
        cs193 = player.combat_state or {}
        if cs193.get('stack_trace_used'):
            await _error(game.code, user_id, "Stack Trace already used this game")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC193
        for _ in range(4):
            _cid193 = None
            if game.action_deck_1:
                _cid193 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _cid193 = game.action_deck_2.pop(0)
            if _cid193:
                db.add(_PHC193(player_id=player.id, action_card_id=_cid193))
            else:
                break
        cs193_new = dict(cs193)
        cs193_new['stack_trace_used'] = True
        player.combat_state = cs193_new

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

    # Addon 195 (Copy/Paste): play 1 card without counting it in the turn limit (once per turn)
    elif addon_number == 195:
        cs195 = dict(player.combat_state or {})
        if cs195.get('copy_paste_active'):
            await _error(game.code, user_id, "Copy/Paste already active this turn")
            pa.is_tapped = False
            return "done"
        cs195['copy_paste_active'] = True
        player.combat_state = cs195

    # Addon 196 (Ctrl+Z): target opponent loses 4L and discards 1 random card (once per game)
    elif addon_number == 196:
        cs196 = player.combat_state or {}
        if cs196.get('ctrlz_used'):
            await _error(game.code, user_id, "Ctrl+Z already used this game")
            pa.is_tapped = False
            return "done"
        target_id196 = data.get("target_player_id")
        target196 = next((p for p in game.players if p.id == target_id196), None)
        if not target196 or target196.id == player.id:
            await _error(game.code, user_id, "Invalid target for Ctrl+Z")
            pa.is_tapped = False
            return "done"
        target196.licenze = max(0, target196.licenze - 4)
        import random as _r196
        _hand196 = list(target196.hand)
        if _hand196:
            _discard196 = _r196.choice(_hand196)
            game.action_discard = (game.action_discard or []) + [_discard196.action_card_id]
            db.delete(_discard196)
        cs196_new = dict(cs196)
        cs196_new['ctrlz_used'] = True
        player.combat_state = cs196_new

    # Addon 199 (Admin Appreciation Day): Administrator/Advanced Administrator gains 5L and draws 2 cards (once per game)
    elif addon_number == 199:
        cs199 = player.combat_state or {}
        if cs199.get('admin_day_used'):
            await _error(game.code, user_id, "Admin Appreciation Day already used this game")
            pa.is_tapped = False
            return "done"
        _role199 = str(getattr(player, 'role', '') or '').lower()
        if 'admin' not in _role199:
            await _error(game.code, user_id, "Only Administrator/Advanced Administrator roles can use this")
            pa.is_tapped = False
            return "done"
        player.licenze += 5
        from app.models.game import PlayerHandCard as _PHC199
        for _ in range(2):
            _cid199 = None
            if game.action_deck_1:
                _cid199 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _cid199 = game.action_deck_2.pop(0)
            if _cid199:
                db.add(_PHC199(player_id=player.id, action_card_id=_cid199))
            else:
                break
        cs199_new = dict(cs199)
        cs199_new['admin_day_used'] = True
        player.combat_state = cs199_new

    else:
        return False

    return True
