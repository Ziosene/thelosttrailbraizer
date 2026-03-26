"""
Secondary addon callback handlers (responses to pending addon actions).
"""
from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import _get_player, _error, _broadcast_state


async def _handle_fomo_buy_addon(game, user_id: int, data: dict, db):
    """Handle out-of-turn addon purchase triggered by Addon 147 (FOMO Trigger)."""
    from app.websocket.handlers.turn.addons.buy import _handle_buy_addon
    player = _get_player(game, user_id)
    if not player:
        return
    cs_fomo = player.combat_state or {}
    if not cs_fomo.get("fomo_trigger_pending"):
        await _error(game.code, user_id, "No FOMO trigger active")
        return
    # Clear FOMO pending flag and set bypass flag to skip turn ownership check
    cs_fomo_new = dict(cs_fomo)
    del cs_fomo_new["fomo_trigger_pending"]
    cs_fomo_new["fomo_bypass_turn"] = True
    player.combat_state = cs_fomo_new
    db.commit()
    # Delegate to normal buy logic with bypass flag set
    await _handle_buy_addon(game, user_id, data, db)
    # Clean up bypass flag
    cs_after = dict(player.combat_state or {})
    cs_after.pop("fomo_bypass_turn", None)
    player.combat_state = cs_after
    db.commit()


async def _handle_appexchange_pick(game, user_id: int, data: dict, db):
    """Handle the player picking one addon from AppExchange Marketplace choices."""
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    pending = list(cs.get("appexchange_pending") or [])
    if not pending:
        await _error(game.code, user_id, "No AppExchange choice pending")
        return
    chosen_id = data.get("addon_id")
    if chosen_id not in pending:
        await _error(game.code, user_id, "Invalid addon choice")
        return
    from app.models.game import PlayerAddon as _PAex
    db.add(_PAex(player_id=player.id, addon_id=chosen_id))
    # Return unchosen addons to front of deck
    for aid in pending:
        if aid != chosen_id:
            game.addon_deck = [aid] + (game.addon_deck or [])
    cs_new = dict(cs)
    cs_new.pop("appexchange_pending", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_BOUGHT,
        "player_id": player.id,
        "addon": {"id": chosen_id},
        "source": "appexchange",
    })
    await _broadcast_state(game, db)


async def _handle_chatter_feed_respond(game, user_id: int, data: dict, db):
    """Handle the target responding to a Chatter Feed card request."""
    responder = _get_player(game, user_id)
    if not responder:
        return
    cs_resp = responder.combat_state or {}
    requester_id = cs_resp.get("chatter_feed_pending_requester_id")
    if not requester_id:
        await _error(game.code, user_id, "No Chatter Feed request pending")
        return
    requester19 = next((p for p in game.players if p.id == requester_id), None)
    if not requester19:
        return
    hand_card_id19 = data.get("hand_card_id")
    from app.models.game import PlayerHandCard as _PHC19r
    hc19r = db.get(_PHC19r, hand_card_id19)
    if not hc19r or hc19r.player_id != responder.id:
        await _error(game.code, user_id, "Card not in your hand")
        return
    # Transfer card to requester
    hc19r.player_id = requester19.id
    # Clear flags
    cs_resp_new = dict(cs_resp)
    cs_resp_new.pop("chatter_feed_pending_requester_id", None)
    responder.combat_state = cs_resp_new
    cs_req19 = dict(requester19.combat_state or {})
    cs_req19.pop("chatter_feed_pending_from_id", None)
    requester19.combat_state = cs_req19
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_metadata_api_reorder(game, user_id: int, data: dict, db):
    """Handle Addon 49 (Metadata API): client sends reordered card_ids for top of deck."""
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    pending49 = list(cs.get("metadata_api_pending") or [])
    if not pending49:
        await _error(game.code, user_id, "No Metadata API reorder pending")
        return
    reordered = data.get("card_ids", [])
    if sorted(reordered) != sorted(pending49):
        await _error(game.code, user_id, "card_ids must be a permutation of the peeked cards")
        return
    n49 = len(reordered)
    # Replace first N cards in action_deck with reordered list
    if game.action_deck and len(game.action_deck) >= n49:
        game.action_deck = list(reordered) + game.action_deck[n49:]
    cs_new = dict(cs)
    cs_new.pop("metadata_api_pending", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_debug_mode_choice(game, user_id: int, data: dict, db):
    """Handle Addon 9 (Debug Mode): player decides to fight or send peeked boss to bottom of deck."""
    from app.websocket.handlers.combat.start import _handle_start_combat
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    _peek_boss = cs.get("debug_mode_peek_boss_id")
    _peek_source = cs.get("debug_mode_peek_source")
    if not _peek_boss or not _peek_source:
        await _error(game.code, user_id, "No Debug Mode peek active")
        return
    decision = data.get("decision")  # "fight" or "send_back"
    cs_new = dict(cs)
    cs_new.pop("debug_mode_peek_boss_id", None)
    cs_new.pop("debug_mode_peek_source", None)
    player.combat_state = cs_new
    if decision == "fight":
        # Boss is NOT in deck anymore (we popped it) — put it back at top then let start_combat pop it
        game.boss_deck = [_peek_boss] + list(game.boss_deck or [])
        db.commit()
        db.refresh(game)
        await _handle_start_combat(game, user_id, {"source": "deck"}, db)
    else:
        # send_back: push boss to BOTTOM of the deck
        game.boss_deck = list(game.boss_deck or []) + [_peek_boss]
        db.commit()
        db.refresh(game)
        await _broadcast_state(game, db)


async def _handle_release_notes_confirm(game, user_id: int, data: dict, db):
    """Handle Addon 60 (Release Notes): player decides to fight or skip the peeked boss."""
    from app.websocket.handlers.combat.start import _handle_start_combat
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    _pending_boss60 = cs.get("release_notes_pending_boss_id")
    _pending_source60 = cs.get("release_notes_pending_source")
    if not _pending_boss60 or not _pending_source60:
        await _error(game.code, user_id, "No Release Notes decision pending")
        return
    decision = data.get("decision")  # "fight" or "skip"
    cs_new = dict(cs)
    cs_new.pop("release_notes_pending_boss_id", None)
    cs_new.pop("release_notes_pending_source", None)
    player.combat_state = cs_new
    if decision == "fight":
        # Re-delegate to start_combat with the same source; boss is still at top of deck
        db.commit()
        db.refresh(game)
        await _handle_start_combat(game, user_id, {"source": _pending_source60}, db)
    else:
        # skip: leave boss at top of deck, do nothing
        db.commit()
        db.refresh(game)
        await _broadcast_state(game, db)


async def _handle_sharing_rules_pick(game, user_id: int, data: dict, db):
    """Handle Addon 63 (Sharing Rules): player picks a card to copy from target's hand."""
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    _pending_target63 = cs.get("sharing_rules_pending_target_id")
    if not _pending_target63:
        await _error(game.code, user_id, "No Sharing Rules pick pending")
        return
    action_card_id63 = data.get("action_card_id")
    # Verify target still has this card
    target63 = next((p for p in game.players if p.id == _pending_target63), None)
    if not target63:
        await _error(game.code, user_id, "Target player not found")
        return
    _has_card = any(hc.action_card_id == action_card_id63 for hc in target63.hand)
    if not _has_card:
        await _error(game.code, user_id, "Target no longer has that card")
        return
    from app.models.game import PlayerHandCard as _PHC63
    db.add(_PHC63(player_id=player.id, action_card_id=action_card_id63))
    cs_new = dict(cs)
    cs_new.pop("sharing_rules_pending_target_id", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_beta_feature_reject(game, user_id: int, data: dict, db):
    """Handle Addon 92 (Beta Feature): reject just-bought addon and draw another from deck."""
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    pending_pa_id = cs.get("beta_feature_pending_pa_id")
    pending_addon_id = cs.get("beta_feature_pending_addon_id")
    if not pending_pa_id:
        await _error(game.code, user_id, "No Beta Feature rejection pending")
        return
    from app.models.game import PlayerAddon as _PA92r
    pa92 = db.get(_PA92r, pending_pa_id)
    if pa92 and pa92.player_id == player.id:
        # Return rejected addon to top of deck
        game.addon_deck = [pending_addon_id] + (game.addon_deck or [])
        db.delete(pa92)
    # Draw next addon from deck as replacement
    next_addon_id = None
    if game.addon_deck:
        addon_deck92 = list(game.addon_deck)
        next_addon_id = addon_deck92.pop(0)
        game.addon_deck = addon_deck92
    if next_addon_id:
        from app.models.game import PlayerAddon as _PA92n
        db.add(_PA92n(player_id=player.id, addon_id=next_addon_id, is_tapped=False))
    cs_new = dict(cs)
    cs_new.pop("beta_feature_pending_pa_id", None)
    cs_new.pop("beta_feature_pending_addon_id", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_beta_feature_keep(game, user_id: int, data: dict, db):
    """Handle Addon 92 (Beta Feature): keep the just-bought addon."""
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    if not cs.get("beta_feature_pending_pa_id"):
        await _error(game.code, user_id, "No Beta Feature choice pending")
        return
    cs_new = dict(cs)
    cs_new.pop("beta_feature_pending_pa_id", None)
    cs_new.pop("beta_feature_pending_addon_id", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_pilot_program_pick(game, user_id: int, data: dict, db):
    """Handle Addon 93 (Pilot Program): player picks an addon from the graveyard."""
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    if not cs.get("pilot_program_pending"):
        await _error(game.code, user_id, "No Pilot Program pick pending")
        return
    addon_card_id93 = data.get("addon_card_id")
    graveyard93 = list(game.addon_graveyard or [])
    if addon_card_id93 not in graveyard93:
        await _error(game.code, user_id, "Addon not in graveyard")
        return
    graveyard93.remove(addon_card_id93)
    game.addon_graveyard = graveyard93
    from app.models.game import PlayerAddon as _PA93p
    db.add(_PA93p(player_id=player.id, addon_id=addon_card_id93, is_tapped=False))
    cs_new = dict(cs)
    cs_new.pop("pilot_program_pending", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_acceptance_criteria_choose(game, user_id: int, data: dict, db):
    """Handle Addon 98 (Acceptance Criteria): choose licenze or 2 cards after boss defeat.
    NOTE: This is only called if the non-simplified flow is used.
    The simplified flow (see roll.py) always gives 2 cards and skips licenze.
    """
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    pending_reward = cs.get("acceptance_criteria_pending_reward")
    if pending_reward is None:
        await _error(game.code, user_id, "No Acceptance Criteria choice pending")
        return
    choice = data.get("choice")
    cs_new = dict(cs)
    cs_new.pop("acceptance_criteria_pending_reward", None)
    if choice == "licenze":
        player.licenze += pending_reward
    else:
        # Draw 2 action cards
        from app.models.game import PlayerHandCard as _PHC98
        for _ in range(2):
            if game.action_deck:
                db.add(_PHC98(player_id=player.id, action_card_id=game.action_deck.pop(0)))
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_external_object_pick(game, user_id: int, data: dict, db):
    """Handle Addon 130 (External Object): pick addon from graveyard paying its normal cost."""
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    if not cs.get("external_object_pending"):
        await _error(game.code, user_id, "No External Object pick pending")
        return
    addon_card_id130 = data.get("addon_card_id")
    graveyard130 = list(game.addon_graveyard or [])
    if addon_card_id130 not in graveyard130:
        await _error(game.code, user_id, "Addon not in graveyard")
        return
    from app.models.card import AddonCard as _AC130
    ac130 = db.get(_AC130, addon_card_id130)
    if not ac130:
        await _error(game.code, user_id, "Addon card not found")
        return
    cost130 = ac130.cost
    if player.licenze < cost130:
        await _error(game.code, user_id, f"Need {cost130}L to acquire this addon (have {player.licenze}L)")
        return
    player.licenze -= cost130
    graveyard130.remove(addon_card_id130)
    game.addon_graveyard = graveyard130
    from app.models.game import PlayerAddon as _PA130
    db.add(_PA130(player_id=player.id, addon_id=addon_card_id130, is_tapped=False))
    cs_new130 = dict(cs)
    cs_new130.pop("external_object_pending", None)
    player.combat_state = cs_new130
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_batch_schedule_card(game, user_id: int, data: dict, db):
    """Handle Addon 113 (Batch Apex Scheduler): schedule a card for next turn."""
    from app.game.engine_addons import has_addon as _has_addon_bs
    player = _get_player(game, user_id)
    if not player:
        return
    if not _has_addon_bs(player, 113):
        await _error(game.code, user_id, "You don't have Batch Apex Scheduler")
        return
    hand_card_id113 = data.get("hand_card_id")
    from app.models.game import PlayerHandCard as _PHC113
    hc113 = db.get(_PHC113, hand_card_id113)
    if not hc113 or hc113.player_id != player.id:
        await _error(game.code, user_id, "Card not in hand")
        return
    cs113 = dict(player.combat_state or {})
    if cs113.get("batch_scheduled_card_id"):
        await _error(game.code, user_id, "Already have a scheduled card")
        return
    cs113["batch_scheduled_card_id"] = hc113.action_card_id
    player.combat_state = cs113
    db.delete(hc113)
    db.commit()
    db.refresh(game)
    await manager.send_to_player(game.code, player.user_id, {
        "type": "batch_schedule_confirmed",
        "scheduled_card_id": cs113["batch_scheduled_card_id"],
    })
    await _broadcast_state(game, db)


async def _handle_territory_set(game, user_id: int, data: dict, db):
    """Handle Addon 126 (Territory Management): set territory target player."""
    from app.game.engine_addons import has_addon as _has_addon_ts
    player = _get_player(game, user_id)
    if not player:
        return
    if not _has_addon_ts(player, 126):
        await _error(game.code, user_id, "You don't have Territory Management")
        return
    target_id126 = data.get("target_player_id")
    target126 = next((p for p in game.players if p.id == target_id126), None)
    if not target126 or target126.id == player.id:
        await _error(game.code, user_id, "Invalid target")
        return
    cs126 = dict(player.combat_state or {})
    cs126["territory_player_id"] = target_id126
    player.combat_state = cs126
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)
