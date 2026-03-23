"""Shared helpers for engine_cards modules."""
from app.models.game import GamePlayer, GameSession


def get_target(
    game: GameSession,
    player: GamePlayer,
    target_player_id: int | None,
) -> "GamePlayer | None":
    """Return a valid opponent from game.players, or None."""
    if target_player_id is None:
        # Auto-select in 2-player games (single opponent)
        others = [p for p in game.players if p.id != player.id]
        return others[0] if len(others) == 1 else None
    return next(
        (p for p in game.players if p.id == target_player_id and p.id != player.id),
        None,
    )
