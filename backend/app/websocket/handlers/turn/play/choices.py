"""
Card choice and resolve handlers.
"""
from app.websocket.game_helpers import (
    _get_player, _error, _broadcast_state, _send_hand_state,
)
from app.models.game import GameSession
from app.game import engine


# ── Card choice handlers ──────────────────────────────────────────────────────

async def _handle_card_choice(game: GameSession, user_id: int, data: dict, db):
    """Process player's response to a pending card choice."""
    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Player not found")
        return

    pending = (player.combat_state or {}).get("pending_card_choice")
    if not pending:
        await _error(game.code, user_id, "No pending card choice")
        return

    choice_type = pending.get("choice_type")

    # Clear the pending state
    cs_clear = dict(player.combat_state)
    del cs_clear["pending_card_choice"]
    player.combat_state = cs_clear

    if choice_type == "discard_specific_cards":
        await _resolve_discard_specific_cards(game, player, user_id, data, db, pending)
    elif choice_type == "reorder_boss_deck":
        await _resolve_reorder_boss_deck(game, player, user_id, data, db, pending)
    elif choice_type == "reorder_action_deck":
        await _resolve_reorder_action_deck(game, player, user_id, data, db, pending)
    elif choice_type == "keep_one_from_drawn":
        await _resolve_keep_one_from_drawn(game, player, user_id, data, db, pending)
    elif choice_type == "recover_from_discard":
        await _resolve_recover_from_discard(game, player, user_id, data, db, pending)
    elif choice_type == "return_card_to_deck_top":
        await _resolve_return_card_to_deck_top(game, player, user_id, data, db, pending)
    elif choice_type == "choose_cards_to_keep":
        await _resolve_choose_cards_to_keep(game, player, user_id, data, db, pending)
    elif choice_type == "choose_addon_to_return":
        await _resolve_choose_addon_to_return(game, player, user_id, data, db, pending)
    else:
        await _error(game.code, user_id, f"Unknown choice_type: {choice_type}")
        return

    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)


async def _resolve_discard_specific_cards(game, player, user_id, data, db, pending):
    """Resolver for choice_type=discard_specific_cards (card 68).
    Client sends: {"hand_card_ids": [id1, id2, ...]}
    """
    chosen_ids = data.get("hand_card_ids", [])
    count = pending.get("count", 2)
    if len(chosen_ids) != count:
        await _error(game.code, user_id, f"Must choose exactly {count} cards")
        return
    from app.models.game import PlayerHandCard as _PHC
    for hcid in chosen_ids:
        hc = db.get(_PHC, hcid)
        if not hc or hc.player_id != player.id:
            await _error(game.code, user_id, f"Invalid card id: {hcid}")
            return
        game.action_discard = (game.action_discard or []) + [hc.action_card_id]
        db.delete(hc)


async def _resolve_reorder_boss_deck(game, player, user_id, data, db, pending):
    """Resolver for choice_type=reorder_boss_deck (card 67).
    Client sends: {"boss_card_ids": [id1, id2, id3]} in preferred order.
    """
    ordered_ids = data.get("boss_card_ids", [])
    original = pending.get("boss_card_ids", [])
    if sorted(ordered_ids) != sorted(original):
        await _error(game.code, user_id, "Invalid reorder — must use same boss cards")
        return
    game.boss_deck_1 = ordered_ids + (game.boss_deck_1 or [])[len(ordered_ids):]


async def _resolve_reorder_action_deck(game, player, user_id, data, db, pending):
    """Resolver for choice_type=reorder_action_deck (cards 32, 107).
    Client sends: {"action_card_ids": [id1, id2, id3]} in preferred order.
    """
    ordered_ids = data.get("action_card_ids", [])
    original = pending.get("action_card_ids", [])
    if sorted(ordered_ids) != sorted(original):
        await _error(game.code, user_id, "Invalid reorder — must use same action cards")
        return
    game.action_deck_1 = ordered_ids + (game.action_deck_1 or [])[len(ordered_ids):]


async def _resolve_keep_one_from_drawn(game, player, user_id, data, db, pending):
    """Resolver for choice_type=keep_one_from_drawn (card 137).
    Client sends: {"action_card_id": id_to_keep}
    The rest are returned to the top of action_deck_1 in original order.
    """
    keep_id = data.get("action_card_id")
    drawn = pending.get("drawn_card_ids", [])
    if keep_id not in drawn:
        await _error(game.code, user_id, "Chosen card was not among the drawn cards")
        return
    from app.models.game import PlayerHandCard as _PHC
    # Return all drawn cards except the chosen one to the top of the deck (in original order)
    to_return = [cid for cid in drawn if cid != keep_id]
    for cid in to_return:
        hc_remove = db.query(_PHC).filter(_PHC.player_id == player.id, _PHC.action_card_id == cid).first()
        if hc_remove:
            db.delete(hc_remove)
    db.flush()
    game.action_deck_1 = to_return + (game.action_deck_1 or [])


async def _resolve_recover_from_discard(game, player, user_id, data, db, pending):
    """Resolver for choice_type=recover_from_discard (cards 34, 69).
    Client sends: {"action_card_ids": [id1, ...]} — list of card IDs to recover from discard.
    """
    chosen_ids = data.get("action_card_ids", [])
    count = pending.get("count", 1)
    if len(chosen_ids) != count:
        await _error(game.code, user_id, f"Must choose exactly {count} cards")
        return
    discard = list(game.action_discard or [])
    from app.models.game import PlayerHandCard as _PHC
    for cid in chosen_ids:
        if cid not in discard:
            await _error(game.code, user_id, f"Card {cid} not in discard pile")
            return
        if len(list(player.hand)) >= engine.MAX_HAND_SIZE:
            break
        discard.remove(cid)
        db.add(_PHC(player_id=player.id, action_card_id=cid))
    game.action_discard = discard


async def _resolve_return_card_to_deck_top(game, player, user_id, data, db, pending):
    """Resolver for choice_type=return_card_to_deck_top (card 106).
    Client sends: {"hand_card_id": id} — the PlayerHandCard.id of the card to return to deck top.
    """
    chosen_hc_id = data.get("hand_card_id")
    count = pending.get("count", 1)
    from app.models.game import PlayerHandCard as _PHC
    hc = db.get(_PHC, chosen_hc_id)
    if not hc or hc.player_id != player.id:
        await _error(game.code, user_id, "Invalid card")
        return
    card_id = hc.action_card_id
    db.delete(hc)
    db.flush()
    game.action_deck_1 = [card_id] + (game.action_deck_1 or [])


async def _resolve_choose_cards_to_keep(game, player, user_id, data, db, pending):
    """Resolver for choice_type=choose_cards_to_keep (card 108).
    Client sends: {"hand_card_ids": [id1, id2]} — PlayerHandCard IDs to keep.
    All drawn cards not in keep list are shuffled back into the deck.
    """
    keep_hc_ids = data.get("hand_card_ids", [])
    drawn = pending.get("drawn_card_ids", [])
    max_keep = pending.get("max_keep", 2)
    if len(keep_hc_ids) > max_keep:
        await _error(game.code, user_id, f"Can keep at most {max_keep} cards")
        return
    from app.models.game import PlayerHandCard as _PHC
    # Verify chosen hand_card_ids are valid and belong to this player
    keep_action_ids = []
    for hcid in keep_hc_ids:
        hc = db.get(_PHC, hcid)
        if not hc or hc.player_id != player.id:
            await _error(game.code, user_id, f"Invalid card id: {hcid}")
            return
        keep_action_ids.append(hc.action_card_id)
    # Discard drawn cards not kept — remove from hand and shuffle into deck
    discard_ids = [cid for cid in drawn if cid not in keep_action_ids]
    for cid in discard_ids:
        hc_remove = db.query(_PHC).filter(_PHC.player_id == player.id, _PHC.action_card_id == cid).first()
        if hc_remove:
            db.delete(hc_remove)
    db.flush()
    if discard_ids:
        shuffled = engine.shuffle_deck(discard_ids)
        game.action_deck_1 = (game.action_deck_1 or []) + shuffled


async def _resolve_choose_addon_to_return(game, player, user_id, data, db, pending):
    """Resolver for choice_type=choose_addon_to_return (card 110).
    Client sends: {"player_addon_id": id} — the PlayerAddon.id of the addon to return.
    """
    chosen_pa_id = data.get("player_addon_id")
    licenze_gained = pending.get("licenze_gained", 8)
    from app.models.game import PlayerAddon as _PA
    from app.models.card import AddonCard as _ADC
    pa = db.get(_PA, chosen_pa_id)
    if not pa or pa.player_id != player.id:
        await _error(game.code, user_id, "Invalid addon")
        return
    addon = db.get(_ADC, pa.addon_id)
    game.addon_deck_1 = [pa.addon_id] + (game.addon_deck_1 or [])
    db.delete(pa)
    player.licenze += licenze_gained
