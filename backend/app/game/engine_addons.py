"""
Addon helper functions: check ownership and apply common effects.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.game import GamePlayer


def has_addon(player: "GamePlayer", number: int) -> bool:
    """Return True if player owns at least one copy of the addon with the given number."""
    return any(pa.card.number == number for pa in player.addons)


def get_addon_pa(player: "GamePlayer", number: int):
    """Return the first PlayerAddon with the given number, or None."""
    return next((pa for pa in player.addons if pa.card.number == number), None)


def has_untapped_addon(player: "GamePlayer", number: int) -> bool:
    """Return True if player owns addon and it is not tapped."""
    pa = get_addon_pa(player, number)
    return pa is not None and not pa.is_tapped
