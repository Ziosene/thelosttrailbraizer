"""
WebSocket message router — connects client actions to game engine logic and DB.
"""
import json
from sqlalchemy.orm import Session

from app.websocket.events import ClientAction
from app.models.game import GameSession
from app.websocket.game_helpers import _error
from app.websocket.handlers.lobby import _handle_join, _handle_select_character, _handle_start_game
from app.websocket.handlers.turn import (
    _handle_draw_card, _handle_play_card, _handle_buy_addon, _handle_use_addon, _handle_end_turn,
    _handle_appexchange_pick, _handle_chatter_feed_respond,
    _handle_metadata_api_reorder, _handle_release_notes_confirm, _handle_sharing_rules_pick,
    _handle_beta_feature_reject, _handle_beta_feature_keep,
    _handle_pilot_program_pick, _handle_acceptance_criteria_choose,
    _handle_external_object_pick, _handle_batch_schedule_card, _handle_territory_set,
    _handle_fomo_buy_addon, _handle_card_choice,
)
from app.websocket.handlers.combat import (
    _handle_start_combat, _handle_roll_dice, _handle_retreat,
    _handle_declare_card, _handle_declare_card_type,
)
from app.websocket.handlers.reaction import _handle_play_reaction, _handle_pass_reaction, _handle_card115_refuse


async def handle_message(
    game_code: str,
    user_id: int,
    raw: str,
    db: Session,
):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        await _error(game_code, user_id, "Invalid JSON")
        return

    action = data.get("action")
    game = db.query(GameSession).filter(GameSession.code == game_code).first()
    if not game:
        await _error(game_code, user_id, "Game not found")
        return

    if action == ClientAction.JOIN_GAME:
        await _handle_join(game, user_id, data, db)
    elif action == ClientAction.SELECT_CHARACTER:
        await _handle_select_character(game, user_id, data, db)
    elif action == ClientAction.START_GAME:
        await _handle_start_game(game, user_id, db)
    elif action == ClientAction.DRAW_CARD:
        await _handle_draw_card(game, user_id, data, db)
    elif action == ClientAction.PLAY_CARD:
        await _handle_play_card(game, user_id, data, db)
    elif action == ClientAction.BUY_ADDON:
        await _handle_buy_addon(game, user_id, data, db)
    elif action == ClientAction.USE_ADDON:
        await _handle_use_addon(game, user_id, data, db)
    elif action == ClientAction.START_COMBAT:
        await _handle_start_combat(game, user_id, data, db)
    elif action == ClientAction.ROLL_DICE:
        await _handle_roll_dice(game, user_id, db)
    elif action == ClientAction.END_TURN:
        await _handle_end_turn(game, user_id, db)
    elif action == ClientAction.RETREAT_COMBAT:
        await _handle_retreat(game, user_id, db)
    elif action == ClientAction.DECLARE_CARD:
        await _handle_declare_card(game, user_id, data, db)
    elif action == ClientAction.DECLARE_CARD_TYPE:
        await _handle_declare_card_type(game, user_id, data, db)
    elif action == ClientAction.PLAY_REACTION:
        await _handle_play_reaction(game, user_id, data, db)
    elif action == ClientAction.PASS_REACTION:
        await _handle_pass_reaction(game, user_id, data, db)
    elif action == "card115_refuse":
        await _handle_card115_refuse(game, user_id, data, db)
    elif action == "appexchange_pick":
        await _handle_appexchange_pick(game, user_id, data, db)
    elif action == "chatter_feed_respond":
        await _handle_chatter_feed_respond(game, user_id, data, db)
    elif action == "metadata_api_reorder":
        await _handle_metadata_api_reorder(game, user_id, data, db)
    elif action == "release_notes_confirm":
        await _handle_release_notes_confirm(game, user_id, data, db)
    elif action == "sharing_rules_pick":
        await _handle_sharing_rules_pick(game, user_id, data, db)
    elif action == "beta_feature_reject":
        await _handle_beta_feature_reject(game, user_id, data, db)
    elif action == "beta_feature_keep":
        await _handle_beta_feature_keep(game, user_id, data, db)
    elif action == "pilot_program_pick":
        await _handle_pilot_program_pick(game, user_id, data, db)
    elif action == "acceptance_criteria_choose":
        await _handle_acceptance_criteria_choose(game, user_id, data, db)
    elif action == "external_object_pick":
        await _handle_external_object_pick(game, user_id, data, db)
    elif action == "batch_schedule_card":
        await _handle_batch_schedule_card(game, user_id, data, db)
    elif action == "territory_set":
        await _handle_territory_set(game, user_id, data, db)
    elif action == "fomo_buy_addon":
        await _handle_fomo_buy_addon(game, user_id, data, db)
    elif action == "card_choice":
        await _handle_card_choice(game, user_id, data, db)
    elif action == "use_borrowed_passive":
        await _handle_use_borrowed_passive(game, user_id, data, db)
    elif action == "skill_transfer_choice":
        await _handle_skill_transfer_choice(game, user_id, data, db)
    else:
        await _error(game_code, user_id, f"Unknown action: {action}")


async def _handle_use_borrowed_passive(game, user_id: int, data: dict, db):
    """Handle use_borrowed_passive: borrow the passive role of a target player for this turn.
    Data: {"action": "use_borrowed_passive", "target_player_id": X}
    Stores the borrowed role in player.combat_state["borrowed_passive_role"] for 1 turn.
    """
    from app.websocket.game_helpers import _get_player, _broadcast_state
    from app.websocket.manager import manager

    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Player not found")
        return

    target_player_id = data.get("target_player_id")
    target = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
    if not target or not target.role:
        await _error(game.code, user_id, "Invalid target or target has no role")
        return

    cs = dict(player.combat_state or {})
    cs["borrowed_passive_role"] = target.role
    cs["borrowed_passive_until_turn"] = game.turn_number
    player.combat_state = cs

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": "borrowed_passive_active",
        "player_id": player.id,
        "borrowed_role": target.role,
        "source_player_id": target.id,
    })
    await _broadcast_state(game, db)


async def _handle_skill_transfer_choice(game, user_id: int, data: dict, db):
    """Handle skill_transfer_choice: swap roles with target player for 2 turns.
    Data: {"action": "skill_transfer_choice", "target_player_id": X}
    Stores original roles in combat_state and swaps player.role for both parties.
    """
    from app.websocket.game_helpers import _get_player, _broadcast_state
    from app.websocket.manager import manager

    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Player not found")
        return

    target_player_id = data.get("target_player_id")
    target = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
    if not target:
        await _error(game.code, user_id, "Invalid target player")
        return

    # Store original roles before swapping
    original_my_role = player.role
    original_target_role = target.role

    # Swap roles
    player.role = original_target_role
    target.role = original_my_role

    # Store swap metadata in both players' combat_state for reversal after 2 turns
    cs_player = dict(player.combat_state or {})
    cs_player["skill_transfer_original_role"] = original_my_role
    cs_player["skill_transfer_revert_at_turn"] = game.turn_number + 2
    cs_player["skill_transfer_partner_id"] = target.id
    player.combat_state = cs_player

    cs_target = dict(target.combat_state or {})
    cs_target["skill_transfer_original_role"] = original_target_role
    cs_target["skill_transfer_revert_at_turn"] = game.turn_number + 2
    cs_target["skill_transfer_partner_id"] = player.id
    target.combat_state = cs_target

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": "roles_swapped",
        "player_id": player.id,
        "target_player_id": target.id,
        "player_new_role": player.role,
        "target_new_role": target.role,
        "revert_at_turn": game.turn_number + 2,
    })
    await _broadcast_state(game, db)
