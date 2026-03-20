"""
Active addon effects — social category (interaction with other players).
Addons: 19, 62, 63, 90, 99, 121, 122, 123, 127, 171, 176, 186, 191, 196
"""
from app.websocket.manager import manager
from app.websocket.game_helpers import _error, _broadcast_state


async def handle_social_effects(addon_number, game, user_id, data, player, pa, db) -> bool | str:
    """
    Handle active addon effects for the social category.
    Returns 'done' if it already did commit+broadcast, True if state was modified, False if not handled.
    """

    # Addon 19 (Chatter Feed): show your hand to a target and request a card
    if addon_number == 19:
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

    # Addon 121 (Mass Email): play 1 economic card — effect applies to you AND 1 other player
    elif addon_number == 121:
        target_id121 = data.get("target_player_id")
        hand_card_id121 = data.get("hand_card_id")
        target121 = next((p for p in game.players if p.id == target_id121), None)
        if not target121 or target121.id == player.id:
            await _error(game.code, user_id, "Invalid target for Mass Email")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC121
        hc121 = db.get(_PHC121, hand_card_id121)
        if not hc121 or hc121.player_id != player.id:
            await _error(game.code, user_id, "Card not in hand")
            pa.is_tapped = False
            return "done"
        from app.models.card import ActionCard as _AC121
        card121 = db.get(_AC121, hc121.action_card_id)
        if not card121 or card121.card_type != "Economica":
            await _error(game.code, user_id, "Must be an economic card")
            pa.is_tapped = False
            return "done"
        from app.game.engine_cards import apply_action_card_effect as _apply121
        _apply121(card121, player, game, db)
        _apply121(card121, target121, game, db)
        game.action_discard = (game.action_discard or []) + [hc121.action_card_id]
        db.delete(hc121)

    # Addon 122 (Broadcast Message): once per game, all opponents discard 1 card
    elif addon_number == 122:
        cs122 = player.combat_state or {}
        if cs122.get("broadcast_used"):
            await _error(game.code, user_id, "Broadcast Message already used this game")
            pa.is_tapped = False
            return "done"
        import random as _r122
        from app.models.game import PlayerHandCard as _PHC122
        for _p122 in game.players:
            if _p122.id == player.id:
                continue
            _hand122 = list(_p122.hand)
            if _hand122:
                _discard122 = _r122.choice(_hand122)
                game.action_discard = (game.action_discard or []) + [_discard122.action_card_id]
                db.delete(_discard122)
        cs122_new = dict(cs122)
        cs122_new["broadcast_used"] = True
        player.combat_state = cs122_new

    # Addon 123 (Global Action): once per game, all opponents lose 2L
    elif addon_number == 123:
        cs123 = player.combat_state or {}
        if cs123.get("global_action_used"):
            await _error(game.code, user_id, "Global Action already used this game")
            pa.is_tapped = False
            return "done"
        for _p123 in game.players:
            if _p123.id != player.id:
                _p123.licenze = max(0, _p123.licenze - 2)
        cs123_new = dict(cs123)
        cs123_new["global_action_used"] = True
        player.combat_state = cs123_new

    # Addon 127 (Sharing Set): once per game, redistribute all players' L equally (floor)
    elif addon_number == 127:
        cs127 = player.combat_state or {}
        if cs127.get("sharing_set_used"):
            await _error(game.code, user_id, "Sharing Set already used this game")
            pa.is_tapped = False
            return "done"
        total127 = sum(p.licenze for p in game.players)
        per_player127 = total127 // len(game.players)
        for _p127 in game.players:
            _p127.licenze = per_player127
        cs127_new = dict(cs127)
        cs127_new["sharing_set_used"] = True
        player.combat_state = cs127_new

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

    else:
        return False

    return True
