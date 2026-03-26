"""
Active addon effects — role and seniority category.
Addons: 66, 102, 164, 165, 170, 199
"""
from app.websocket.manager import manager
from app.websocket.game_helpers import _error, _broadcast_state


async def handle_role_effects(addon_number, game, user_id, data, player, pa, db) -> bool | str:
    """
    Handle active addon effects for the role/seniority category.
    Returns 'done' if it already did commit+broadcast, True if state was modified, False if not handled.
    """

    # Addon 66 (Trust Layer): once per game, protect from opponent cards for 1 turn
    if addon_number == 66:
        _cs66 = player.combat_state or {}
        if _cs66.get("trust_layer_used"):
            await _error(game.code, user_id, "Trust Layer already used this game")
            pa.is_tapped = False
            return "done"
        _cs66_new = dict(_cs66)
        _cs66_new["trust_layer_used"] = True
        _cs66_new["trust_layer_active"] = True
        player.combat_state = _cs66_new

    # Addon 102 (Custom Permission): once per turn, use passive ability of a player with lower seniority
    elif addon_number == 102:
        from app.models.game import Seniority as _Sen102
        _SENIORITY_RANK102 = {_Sen102.junior: 1, _Sen102.experienced: 2, _Sen102.senior: 3, _Sen102.evangelist: 4}
        _my_rank102 = _SENIORITY_RANK102.get(player.seniority, 0)
        # Find players with lower seniority
        _lower_players102 = [
            p for p in game.players
            if p.id != player.id and _SENIORITY_RANK102.get(p.seniority, 0) < _my_rank102
            and p.role  # must have a role
        ]
        if not _lower_players102:
            await _error(game.code, user_id, "No players with lower seniority available")
            pa.is_tapped = False
            return "done"
        cs102 = player.combat_state or {}
        if cs102.get("custom_permission_used_turn") == game.turn_number:
            await _error(game.code, user_id, "Custom Permission already used this turn")
            pa.is_tapped = False
            return "done"
        # Player must choose which lower-seniority player's passive to borrow
        _options102 = [{"player_id": p.id, "name": p.user.username if p.user else str(p.id), "role": p.role} for p in _lower_players102]
        _cs102_new = dict(cs102)
        _cs102_new["custom_permission_used_turn"] = game.turn_number
        player.combat_state = _cs102_new
        db.flush()
        await manager.broadcast(game.code, {
            "type": "passive_choice_required",
            "choice_type": "borrow_passive",
            "player_id": user_id,
            "options": _options102
        })
        return "done"  # client responds with "use_borrowed_passive" action

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
            if game.action_deck:
                _cid199 = game.action_deck.pop(0)
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
