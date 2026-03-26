"""
Gestori WS per le azioni de La Pila:
  - stack_pass: il giocatore passa la priorità
  - stack_play_card: il giocatore gioca una carta nella pila (solo Lucky Roll per ora)
"""
from sqlalchemy.orm import Session

from app.websocket.game_helpers import _get_player, _error
from app.websocket.stack_manager import pass_priority, push_card_to_stack, get_session, StackItem


async def _handle_stack_pass(game, user_id: int, data: dict, db: Session):
    """Player passes their priority in La Pila."""
    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Player not found")
        return

    accepted = pass_priority(game.code, player.id)
    if not accepted:
        await _error(game.code, user_id, "Non è il tuo turno nella Pila")


async def _handle_stack_play_card(game, user_id: int, data: dict, db: Session):
    """Player plays a card into La Pila.

    Data: {"action": "stack_play_card", "hand_card_id": int}

    For V1, the only supported card effect is Lucky Roll (card 27) which causes a reroll.
    Other difensiva cards just add to the stack cosmetically (future: apply their effects).
    """
    from app.models.game import PlayerHandCard
    from app.models.card import ActionCard

    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Player not found")
        return

    session = get_session(game.code)
    if session is None:
        await _error(game.code, user_id, "Nessuna Pila aperta")
        return

    if session.priority_player_id != player.id:
        await _error(game.code, user_id, "Non è il tuo turno nella Pila")
        return

    hand_card_id = data.get("hand_card_id")
    if not hand_card_id:
        await _error(game.code, user_id, "Manca hand_card_id")
        return

    hc = db.get(PlayerHandCard, hand_card_id)
    if not hc or hc.player_id != player.id:
        await _error(game.code, user_id, "Carta non trovata in mano")
        return

    card = db.get(ActionCard, hc.action_card_id)
    if not card:
        await _error(game.code, user_id, "Carta non valida")
        return

    # Build StackItem based on card number
    force_reroll = card.number == 27  # Lucky Roll: causes a reroll
    roll_modifier = 0

    # Consume card from hand
    game.action_discard = (game.action_discard or []) + [hc.action_card_id]
    db.delete(hc)
    player.cards_played_this_turn = (player.cards_played_this_turn or 0) + 1
    db.commit()
    db.refresh(game)

    item = StackItem(
        kind="card",
        card_id=card.id,
        card_name=card.name,
        played_by=player.id,
        roll_modifier=roll_modifier,
        force_reroll=force_reroll,
    )

    accepted = push_card_to_stack(game.code, item)
    if not accepted:
        await _error(game.code, user_id, "Impossibile aggiungere alla Pila")
