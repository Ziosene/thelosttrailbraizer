"""
Active addon effects for addon numbers 101-150.
"""
from app.websocket.manager import manager
from app.websocket.game_helpers import _error, _broadcast_state
from app.game import engine
from app.game.engine_addons import has_addon as _has_addon_addon


async def handle_effects_101_150(addon_number, game, user_id, data, player, pa, db) -> bool:
    """
    Handle active addon effects for addon numbers 101-150.
    Returns True if the addon was handled, False otherwise.
    """

    # Addon 101 (Org-Wide Sharing): once per turn, a player gains +1L
    if addon_number == 101:
        target_id101 = data.get("target_player_id", player.id)
        target101 = next((p for p in game.players if p.id == target_id101), None)
        if not target101:
            await _error(game.code, user_id, "Invalid target")
            pa.is_tapped = False
            return "done"
        target101.licenze += 1

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

    # Addon 104 (User Story): once per game, draw 3 cards and gain 3L
    elif addon_number == 104:
        cs104 = player.combat_state or {}
        if cs104.get("user_story_used"):
            await _error(game.code, user_id, "User Story already used")
            pa.is_tapped = False
            return "done"
        from app.models.game import PlayerHandCard as _PHC104
        for _ in range(3):
            if game.action_deck_1:
                cid104 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                cid104 = game.action_deck_2.pop(0)
            else:
                break
            db.add(_PHC104(player_id=player.id, action_card_id=cid104))
        player.licenze += 3
        cs104_new = dict(cs104)
        cs104_new["user_story_used"] = True
        player.combat_state = cs104_new

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
            game.addon_deck_1 = (game.addon_deck_1 or []) + [pa108.addon_id]
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
            game.addon_market_1 = game.addon_deck_1.pop(0) if game.addon_deck_1 else (game.addon_deck_2.pop(0) if game.addon_deck_2 else None)
        elif game.addon_market_2 == target_addon_id119:
            game.addon_market_2 = game.addon_deck_1.pop(0) if game.addon_deck_1 else (game.addon_deck_2.pop(0) if game.addon_deck_2 else None)
        from app.models.game import PlayerAddon as _PA119
        db.add(_PA119(player_id=player.id, addon_id=target_addon_id119, is_tapped=False))
        cs119_new = dict(cs119)
        cs119_new["queueable_job_used"] = True
        player.combat_state = cs119_new

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
                if game.action_deck_1:
                    cid134 = game.action_deck_1.pop(0)
                elif game.action_deck_2:
                    cid134 = game.action_deck_2.pop(0)
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
