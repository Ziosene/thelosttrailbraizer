"""Shared helpers for engine_cards modules."""
from app.models.game import GamePlayer, GameSession


def get_target(
    game: GameSession,
    player: GamePlayer,
    target_player_id: int | None,
) -> "GamePlayer | None":
    """Return a valid opponent from game.players, or None."""
    if target_player_id is None:
        return None
    return next(
        (p for p in game.players if p.id == target_player_id and p.id != player.id),
        None,
    )
