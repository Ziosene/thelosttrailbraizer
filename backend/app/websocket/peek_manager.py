"""
Peek windows for role passives that require a choice before drawing.

Used by:
- Data Architect: peek 2 boss cards before drawing from deck
- Data Cloud Consultant: peek 3 action cards before drawing

API:
  open_peek_window(game_code, player_id, choices, timeout) -> int | None
  resolve_peek(game_code, player_id, chosen_id) -> bool
  has_pending_peek(game_code, player_id) -> bool
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _PeekSlot:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    chosen_id: Optional[int] = None
    valid_ids: list = field(default_factory=list)


_pending: dict[str, _PeekSlot] = {}


def _key(game_code: str, player_id: int) -> str:
    return f"{game_code}:{player_id}"


async def open_peek_window(
    game_code: str,
    player_id: int,
    valid_ids: list,
    timeout: float = 30.0,
) -> Optional[int]:
    """Wait for the player to choose one of the valid_ids.

    Returns the chosen id, or None on timeout (caller should fall back to default).
    """
    k = _key(game_code, player_id)
    slot = _PeekSlot(valid_ids=list(valid_ids))
    _pending[k] = slot
    try:
        await asyncio.wait_for(slot.event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        _pending.pop(k, None)
    return slot.chosen_id


def resolve_peek(game_code: str, player_id: int, chosen_id: int) -> bool:
    """Signal the player's choice.

    Returns True if there was an open window and the chosen_id was valid.
    """
    slot = _pending.get(_key(game_code, player_id))
    if slot is None:
        return False
    if chosen_id not in slot.valid_ids:
        return False
    slot.chosen_id = chosen_id
    slot.event.set()
    return True


def has_pending_peek(game_code: str, player_id: int) -> bool:
    return _key(game_code, player_id) in _pending
