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
    _handle_fomo_buy_addon,
)
from app.websocket.handlers.combat import (
    _handle_start_combat, _handle_roll_dice, _handle_retreat,
    _handle_declare_card, _handle_declare_card_type,
)
from app.websocket.handlers.reaction import _handle_play_reaction, _handle_pass_reaction


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
    else:
        await _error(game_code, user_id, f"Unknown action: {action}")
