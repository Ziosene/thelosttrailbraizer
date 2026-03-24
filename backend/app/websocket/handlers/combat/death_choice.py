"""
Handle choose_death_penalty — the dying player picks which card and addon to lose.
"""
from sqlalchemy.orm import Session

from app.websocket.game_helpers import (
    _get_player, _error, _broadcast_state, _send_hand_state,
)
from app.models.game import GameSession, GameStatus


async def _handle_choose_death_penalty(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Game not in progress")
        return

    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Player not found")
        return

    if not (player.combat_state or {}).get("death_penalty_pending"):
        await _error(game.code, user_id, "No death penalty pending")
        return

    # ── Remove chosen card from hand → discard ─────────────────────────────
    hand_card_id = data.get("hand_card_id")  # PlayerHandCard.id or null
    if hand_card_id:
        from app.models.game import PlayerHandCard as _PHC
        hc = db.get(_PHC, hand_card_id)
        if hc and hc.player_id == player.id:
            game.action_discard = (game.action_discard or []) + [hc.action_card_id]
            db.delete(hc)

    # ── Remove chosen addon from collection → graveyard ─────────────────────
    player_addon_id = data.get("player_addon_id")  # PlayerAddon.id or null
    if player_addon_id:
        from app.models.game import PlayerAddon as _PA
        pa = db.get(_PA, player_addon_id)
        if pa and pa.player_id == player.id:
            game.addon_graveyard = (game.addon_graveyard or []) + [pa.addon_id]
            db.delete(pa)

    # ── Clear pending flag ─────────────────────────────────────────────────
    cs = dict(player.combat_state or {})
    cs.pop("death_penalty_pending", None)
    player.combat_state = cs

    db.commit()
    db.refresh(game)

    await _send_hand_state(game.code, player, db)
    await _broadcast_state(game, db)
