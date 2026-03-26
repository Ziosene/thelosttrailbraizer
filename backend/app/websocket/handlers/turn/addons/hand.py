"""
Active addon effects — hand and deck category.
Addons: 18, 26, 37, 49, 50, 51, 53, 55, 74, 104, 109, 172, 173, 174, 179, 193, 195
"""
from app.websocket.manager import manager
from app.websocket.game_helpers import _error, _broadcast_state


async def handle_hand_effects(addon_number, game, user_id, data, player, pa, db) -> bool | str:
    """
    Handle active addon effects for the hand/deck category.
    Returns 'done' if it already did commit+broadcast, True if state was modified, False if not handled.
    """

    # Addon 18 (Field History Tracking): recover last discarded card to hand
    if addon_number == 18:
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

    # Addon 37 (Deployment Pipeline): once per turn, allow 1 extra action card play
    elif addon_number == 37:
        cs37 = dict(player.combat_state or {})
        cs37["deployment_pipeline_extra_card"] = True
        player.combat_state = cs37

    # Addon 49 (Metadata API): look at top 3 cards of action deck and reorder them
    elif addon_number == 49:
        _deck49 = game.action_deck or game.action_deck
        _choices49 = (game.action_deck or [])[:3]
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

    # Addon 51 (Change Set): discard up to 3 cards from hand and draw the same number
    elif addon_number == 51:
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
            if game.action_deck:
                _new_card51 = game.action_deck.pop(0)
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
            if game.action_deck:
                _cid55 = game.action_deck.pop(0)
            else:
                break
            db.add(_PHC55(player_id=player.id, action_card_id=_cid55))
            _drawn55 += 1
        _cs55_new = dict(_cs55)
        _cs55_new["data_loader_used"] = True
        player.combat_state = _cs55_new

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
        if game.action_deck:
            _new74 = game.action_deck.pop(0)
        if _new74 is not None:
            db.add(_PHC74(player_id=player.id, action_card_id=_new74))

    # Addon 104 (User Story): once per game, draw 3 cards and gain 3L
    elif addon_number == 104:
        cs104 = player.combat_state or {}
        if cs104.get("user_story_used"):
            await _error(game.code, user_id, "User Story already used")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC104
        for _ in range(3):
            if game.action_deck:
                cid104 = game.action_deck.pop(0)
            else:
                break
            db.add(_PHC104(player_id=player.id, action_card_id=cid104))
        player.licenze += 3
        cs104_new = dict(cs104)
        cs104_new["user_story_used"] = True
        player.combat_state = cs104_new

    # Addon 109 (Proof of Concept): once per turn, play 1 card without using a slot
    elif addon_number == 109:
        cs109 = dict(player.combat_state or {})
        if cs109.get("proof_of_concept_used_this_turn"):
            await _error(game.code, user_id, "Proof of Concept already used this turn")
            pa.is_tapped = False
            return "done"
        cs109["proof_of_concept_active"] = True
        cs109["proof_of_concept_used_this_turn"] = True
        player.combat_state = cs109

    # Addon 172 (Deck Shuffle): shuffle the shared action deck (once per turn)
    elif addon_number == 172:
        import random as _r172
        if game.action_deck:
            _deck172_1 = list(game.action_deck)
            _r172.shuffle(_deck172_1)
            game.action_deck = _deck172_1
        if game.action_deck:
            _deck172_2 = list(game.action_deck)
            _r172.shuffle(_deck172_2)
            game.action_deck = _deck172_2

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
            if game.action_deck is not None:
                game.action_deck = game.action_deck + [cid174]
            else:
                game.action_deck = (game.action_deck or []) + [cid174]
        game.action_discard = discard174

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
            if game.action_deck:
                _cid179 = game.action_deck.pop(0)
            else:
                break
            db.add(_PHC179(player_id=player.id, action_card_id=_cid179))

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
            if game.action_deck:
                _cid193 = game.action_deck.pop(0)
            if _cid193:
                db.add(_PHC193(player_id=player.id, action_card_id=_cid193))
            else:
                break
        cs193_new = dict(cs193)
        cs193_new['stack_trace_used'] = True
        player.combat_state = cs193_new

    # Addon 195 (Copy/Paste): play 1 card without counting it in the turn limit (once per turn)
    elif addon_number == 195:
        cs195 = dict(player.combat_state or {})
        if cs195.get('copy_paste_active'):
            await _error(game.code, user_id, "Copy/Paste already active this turn")
            pa.is_tapped = False
            return "done"
        cs195['copy_paste_active'] = True
        player.combat_state = cs195

    else:
        return False

    return True
