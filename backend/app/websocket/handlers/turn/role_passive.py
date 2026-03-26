"""
Role passive ability handlers.

Actions handled here:
- role_discard_draw       : Administrator (1/turn) & Advanced Administrator (up to 2/turn)
- role_recover_from_discard : Integration Architect (1/turn)
- role_skip_draw          : Marketing Cloud Administrator (1/turn, draw phase only)
- role_predict_roll       : Einstein Analytics Consultant (set prediction before rolling)
- boss_peek_choice        : Data Architect (resolve which boss to fight after peek)
- draw_peek_choice        : Data Cloud Consultant (resolve which action card to draw after peek)
"""
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state, _send_hand_state,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.game import engine
from app.game.engine_role import (
    ROLE_ADMINISTRATOR,
    ROLE_ADVANCED_ADMINISTRATOR,
    ROLE_INTEGRATION_ARCH,
    ROLE_MARKETING_CLOUD_ADMIN,
    ROLE_EINSTEIN_ANALYTICS_CONSULTANT,
    ROLE_DATA_ARCH,
    ROLE_DATA_CLOUD_CONSULTANT,
)
from app.websocket.peek_manager import resolve_peek


# ---------------------------------------------------------------------------
# role_discard_draw
# ---------------------------------------------------------------------------

async def _handle_role_discard_draw(game: GameSession, user_id: int, data: dict, db: Session):
    """Administrator: discard 1 card, draw 1 new one (once per turn).
    Advanced Administrator: up to 2 per turn.
    Data: {"action": "role_discard_draw", "hand_card_id": <id>}
    """
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Game not in progress")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if game.current_phase not in (TurnPhase.action, TurnPhase.draw):
        await _error(game.code, user_id, "Cannot use role passive now")
        return

    role = player.role or ""
    if role not in (ROLE_ADMINISTRATOR, ROLE_ADVANCED_ADMINISTRATOR):
        await _error(game.code, user_id, "Role passive not available for your role")
        return

    cs = dict(player.combat_state or {})

    if role == ROLE_ADMINISTRATOR:
        if cs.get("role_passive_used_this_turn"):
            await _error(game.code, user_id, "Role passive already used this turn")
            return
    else:  # Advanced Administrator
        used_count = cs.get("role_passive_count_this_turn", 0)
        if used_count >= 2:
            await _error(game.code, user_id, "Role passive already used 2 times this turn")
            return

    hand_card_id = data.get("hand_card_id")
    if not hand_card_id:
        await _error(game.code, user_id, "Missing hand_card_id")
        return

    from app.models.game import PlayerHandCard
    hc = db.get(PlayerHandCard, hand_card_id)
    if not hc or hc.player_id != player.id:
        await _error(game.code, user_id, "Card not in your hand")
        return

    # Discard the card
    game.action_discard = (game.action_discard or []) + [hc.action_card_id]
    db.delete(hc)

    # Reshuffle discard into deck if needed
    if not game.action_deck and game.action_discard:
        game.action_deck = engine.shuffle_deck(game.action_discard)
        game.action_discard = []

    if not game.action_deck:
        db.commit()
        await _error(game.code, user_id, "No cards left in the action deck")
        return

    new_card_id = game.action_deck.pop(0)
    db.add(PlayerHandCard(player_id=player.id, action_card_id=new_card_id))

    # Track usage
    if role == ROLE_ADMINISTRATOR:
        cs["role_passive_used_this_turn"] = True
    else:
        cs["role_passive_count_this_turn"] = cs.get("role_passive_count_this_turn", 0) + 1
    player.combat_state = cs

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": "role_discard_draw",
        "player_id": player.id,
        "role": role,
    })
    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)


# ---------------------------------------------------------------------------
# role_recover_from_discard
# ---------------------------------------------------------------------------

async def _handle_role_recover_from_discard(game: GameSession, user_id: int, data: dict, db: Session):
    """Integration Architect: recover top card from action_discard pile (once per turn).
    Data: {"action": "role_recover_from_discard"}
    """
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Game not in progress")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if game.current_phase not in (TurnPhase.action, TurnPhase.draw):
        await _error(game.code, user_id, "Cannot use role passive now")
        return

    if (player.role or "") != ROLE_INTEGRATION_ARCH:
        await _error(game.code, user_id, "Role passive not available for your role")
        return

    cs = dict(player.combat_state or {})
    if cs.get("role_passive_used_this_turn"):
        await _error(game.code, user_id, "Role passive already used this turn")
        return

    if not game.action_discard:
        await _error(game.code, user_id, "Action discard pile is empty")
        return

    # Pop last (top) card from the discard pile
    discard_list = list(game.action_discard)
    card_id = discard_list.pop()
    game.action_discard = discard_list

    from app.models.game import PlayerHandCard
    db.add(PlayerHandCard(player_id=player.id, action_card_id=card_id))

    cs["role_passive_used_this_turn"] = True
    player.combat_state = cs

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": "role_recover_from_discard",
        "player_id": player.id,
    })
    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)


# ---------------------------------------------------------------------------
# role_skip_draw
# ---------------------------------------------------------------------------

async def _handle_role_skip_draw(game: GameSession, user_id: int, data: dict, db: Session):
    """Marketing Cloud Administrator: skip drawing a card this turn.
    Must be sent during the draw phase. Advances phase to action directly.
    Data: {"action": "role_skip_draw"}
    """
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Game not in progress")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if game.current_phase != TurnPhase.draw:
        await _error(game.code, user_id, "Can only skip draw during the draw phase")
        return

    if (player.role or "") != ROLE_MARKETING_CLOUD_ADMIN:
        await _error(game.code, user_id, "Role passive not available for your role")
        return

    cs = dict(player.combat_state or {})
    if cs.get("role_skip_draw_used"):
        await _error(game.code, user_id, "Role skip draw already used this turn")
        return

    cs["role_skip_draw_used"] = True
    player.combat_state = cs

    game.current_phase = TurnPhase.action

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": "role_skip_draw",
        "player_id": player.id,
    })
    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)


# ---------------------------------------------------------------------------
# role_predict_roll
# ---------------------------------------------------------------------------

async def _handle_role_predict_roll(game: GameSession, user_id: int, data: dict, db: Session):
    """Einstein Analytics Consultant: predict the dice roll result before rolling.
    If correct, damage dealt is doubled.
    Data: {"action": "role_predict_roll", "prediction": <1-10>}
    Must be sent during combat phase, before roll_dice.
    """
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Game not in progress")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if game.current_phase != TurnPhase.combat:
        await _error(game.code, user_id, "Can only predict during combat phase")
        return

    if not player.is_in_combat:
        await _error(game.code, user_id, "Not in combat")
        return

    if (player.role or "") != ROLE_EINSTEIN_ANALYTICS_CONSULTANT:
        await _error(game.code, user_id, "Role passive not available for your role")
        return

    prediction = data.get("prediction")
    if not isinstance(prediction, int) or prediction < 1 or prediction > 10:
        await _error(game.code, user_id, "Prediction must be an integer between 1 and 10")
        return

    cs = dict(player.combat_state or {})
    if cs.get("einstein_prediction") is not None:
        await _error(game.code, user_id, "Prediction already set for this round")
        return

    cs["einstein_prediction"] = prediction
    player.combat_state = cs

    db.commit()
    db.refresh(game)

    await manager.send_to_player(game.code, player.user_id, {
        "type": "role_predict_roll_set",
        "player_id": player.id,
        "prediction": prediction,
    })
    await manager.broadcast(game.code, {
        "type": "role_predict_roll_announced",
        "player_id": player.id,
    })
    await _broadcast_state(game, db)


# ---------------------------------------------------------------------------
# boss_peek_choice  (Data Architect)
# ---------------------------------------------------------------------------

async def _handle_boss_peek_choice(game: GameSession, user_id: int, data: dict, db: Session):
    """Data Architect: choose which boss card to draw after peeking.
    Data: {"action": "boss_peek_choice", "boss_card_id": <id>}
    """
    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Player not found")
        return

    boss_card_id = data.get("boss_card_id")
    if not isinstance(boss_card_id, int):
        await _error(game.code, user_id, "Missing or invalid boss_card_id")
        return

    if not resolve_peek(game.code, player.id, boss_card_id):
        await _error(game.code, user_id, "No pending boss peek or invalid choice")
        return

    # The open_peek_window in start.py will receive the chosen id and continue.


# ---------------------------------------------------------------------------
# draw_peek_choice  (Data Cloud Consultant)
# ---------------------------------------------------------------------------

async def _handle_draw_peek_choice(game: GameSession, user_id: int, data: dict, db: Session):
    """Data Cloud Consultant: choose which action card to draw after peeking.
    Data: {"action": "draw_peek_choice", "card_id": <id>}
    """
    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Player not found")
        return

    card_id = data.get("card_id")
    if not isinstance(card_id, int):
        await _error(game.code, user_id, "Missing or invalid card_id")
        return

    if not resolve_peek(game.code, player.id, card_id):
        await _error(game.code, user_id, "No pending draw peek or invalid choice")
        return

    # The open_peek_window in draw.py will receive the chosen id and continue.
