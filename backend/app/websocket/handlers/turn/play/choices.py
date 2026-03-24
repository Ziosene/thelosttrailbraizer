"""
Card choice WS handlers.

Business logic lives in app.game.engine_cards.choices_logic (pure, testable).
This module handles: payload extraction, error propagation, DB commit, broadcast.
"""
from app.websocket.game_helpers import (
    _get_player, _error, _broadcast_state, _send_hand_state,
)
from app.models.game import GameSession
from app.game.engine_cards.choices_logic import (
    resolve_discard_specific_cards,
    resolve_reorder_boss_deck,
    resolve_reorder_action_deck,
    resolve_keep_one_from_drawn,
    resolve_recover_from_discard,
    resolve_return_card_to_deck_top,
    resolve_choose_cards_to_keep,
    resolve_choose_addon_to_return,
    resolve_delete_target_addon,
)


# ── Card choice dispatcher ────────────────────────────────────────────────────

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

    # Clear the pending state before resolving
    cs_clear = dict(player.combat_state)
    del cs_clear["pending_card_choice"]
    player.combat_state = cs_clear

    error = None

    if choice_type == "discard_specific_cards":
        result = resolve_discard_specific_cards(
            game, player, db,
            chosen_ids=data.get("hand_card_ids", []),
            count=pending.get("count", 2),
        )
        error = result.get("error")

    elif choice_type == "reorder_boss_deck":
        result = resolve_reorder_boss_deck(
            game, player, db,
            ordered_ids=data.get("boss_card_ids", []),
            original=pending.get("boss_card_ids", []),
        )
        error = result.get("error")

    elif choice_type == "reorder_action_deck":
        result = resolve_reorder_action_deck(
            game, player, db,
            ordered_ids=data.get("action_card_ids", []),
            original=pending.get("action_card_ids", []),
        )
        error = result.get("error")

    elif choice_type == "keep_one_from_drawn":
        result = resolve_keep_one_from_drawn(
            game, player, db,
            keep_id=data.get("action_card_id"),
            drawn=pending.get("drawn_card_ids", []),
        )
        error = result.get("error")

    elif choice_type == "recover_from_discard":
        result = resolve_recover_from_discard(
            game, player, db,
            chosen_ids=data.get("action_card_ids", []),
            count=pending.get("count", 1),
        )
        error = result.get("error")

    elif choice_type == "return_card_to_deck_top":
        result = resolve_return_card_to_deck_top(
            game, player, db,
            chosen_hc_id=data.get("hand_card_id"),
        )
        error = result.get("error")

    elif choice_type == "choose_cards_to_keep":
        result = resolve_choose_cards_to_keep(
            game, player, db,
            keep_hc_ids=data.get("hand_card_ids", []),
            drawn=pending.get("drawn_card_ids", []),
            max_keep=pending.get("max_keep", 2),
        )
        error = result.get("error")

    elif choice_type == "choose_addon_to_return":
        result = resolve_choose_addon_to_return(
            game, player, db,
            chosen_pa_id=data.get("player_addon_id"),
            licenze_gained=pending.get("licenze_gained", 8),
        )
        error = result.get("error")

    elif choice_type == "delete_target_addon":
        result = resolve_delete_target_addon(
            game, player, db,
            chosen_pa_id=data.get("player_addon_id"),
            target_player_id=pending.get("target_player_id"),
        )
        error = result.get("error")

    else:
        await _error(game.code, user_id, f"Unknown choice_type: {choice_type}")
        return

    if error:
        await _error(game.code, user_id, error)
        return

    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)
