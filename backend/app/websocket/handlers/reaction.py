"""
Handler per le azioni di reazione out-of-turn.

_handle_play_reaction  — il giocatore vuole giocare una carta come reazione
_handle_pass_reaction  — il giocatore passa la finestra di reazione

Questi handler NON toccano il DB: segnalano solo l'asyncio.Event in
reaction_manager. Tutta la logica di risoluzione (consumo carta, effetti, commit)
rimane in _handle_play_card che attende il risultato.
"""
from sqlalchemy.orm import Session

from app.models.game import GameSession
from app.websocket.game_helpers import _get_player, _error
from app.websocket.reaction_manager import resolve_reaction, has_pending_reaction


async def _handle_play_reaction(game: GameSession, user_id: int, data: dict, db: Session):
    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Player not found")
        return

    if not has_pending_reaction(game.code, player.id):
        await _error(game.code, user_id, "No reaction window open for you")
        return

    hand_card_id = data.get("hand_card_id")
    if not hand_card_id:
        await _error(game.code, user_id, "hand_card_id required")
        return

    resolve_reaction(game.code, player.id, {"action": "play", "hand_card_id": hand_card_id})


async def _handle_pass_reaction(game: GameSession, user_id: int, data: dict, db: Session):
    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Player not found")
        return

    if not has_pending_reaction(game.code, player.id):
        await _error(game.code, user_id, "No reaction window open for you")
        return

    resolve_reaction(game.code, player.id, {"action": "pass"})
