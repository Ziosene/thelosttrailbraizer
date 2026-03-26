"""
Gestisce La Pila — finestra di reazione multi-giocatore dopo ogni tiro di dado.

La Pila è una struttura LIFO aperta dopo ogni roll_dice. Ogni giocatore ottiene
8 secondi per passare la priorità o giocare una carta. Quando tutti passano
consecutivamente, la pila si risolve.

API pubblica:
  open_stack(game_code, player_order, initial_roll, initial_result, threshold, db, timeout=8.0) -> tuple[int, str]
  push_card_to_stack(game_code, item) -> bool
  pass_priority(game_code, player_id) -> bool
  has_priority(game_code, player_id) -> bool
  get_session(game_code) -> StackSession | None
"""
import asyncio
from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class StackItem:
    kind: Literal["dice_result", "card"]
    roll: Optional[int] = None
    result: Optional[str] = None       # "hit" | "miss"
    threshold: Optional[int] = None
    player_id: Optional[int] = None
    card_id: Optional[int] = None
    card_name: Optional[str] = None
    played_by: Optional[int] = None
    roll_modifier: int = 0
    force_reroll: bool = False


@dataclass
class StackSession:
    game_code: str
    player_order: list            # GamePlayer.id, clockwise from active player
    active_player_id: int
    stack: list = field(default_factory=list)     # list[StackItem], index 0 = bottom
    priority_player_id: int = 0
    consecutive_passes: int = 0
    final_roll: int = 0
    final_result: str = "miss"
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    _last_action: str = "none"    # "card" | "pass" | "none"


_sessions: dict = {}   # game_code -> StackSession


def get_session(game_code: str) -> Optional[StackSession]:
    return _sessions.get(game_code)


def has_priority(game_code: str, player_id: int) -> bool:
    s = _sessions.get(game_code)
    return s is not None and s.priority_player_id == player_id


def _next_player(session: StackSession) -> int:
    """Return the next player ID in the priority order."""
    order = session.player_order
    if not order:
        return session.active_player_id
    try:
        idx = order.index(session.priority_player_id)
    except ValueError:
        return order[0]
    return order[(idx + 1) % len(order)]


def push_card_to_stack(game_code: str, item: StackItem) -> bool:
    """
    Push a card item to the stack. The item should already be validated.
    Resets consecutive_passes to 0 and sets priority back to active player.
    Returns True if the push was accepted.
    """
    s = _sessions.get(game_code)
    if s is None or s.priority_player_id != item.played_by:
        return False
    s.stack.append(item)
    s.consecutive_passes = 0
    s.priority_player_id = s.active_player_id
    s._last_action = "card"
    s._event.set()
    return True


def pass_priority(game_code: str, player_id: int) -> bool:
    """
    Advance priority to the next player.
    Returns True if accepted, False if not this player's priority.
    """
    s = _sessions.get(game_code)
    if s is None or s.priority_player_id != player_id:
        return False
    s.consecutive_passes += 1
    s.priority_player_id = _next_player(s)
    s._last_action = "pass"
    s._event.set()
    return True


def _compute_final(session: StackSession) -> tuple:
    """Compute final roll and result by resolving the stack LIFO."""
    # Bottom item is the dice result
    base = session.stack[0]
    roll = base.roll or 0
    threshold = base.threshold or 5

    # Apply card modifiers top-down (LIFO = last card first)
    for item in reversed(session.stack[1:]):
        if item.force_reroll:
            import random
            roll = random.randint(1, 10)
        else:
            roll = max(1, min(10, roll + item.roll_modifier))

    result = "hit" if roll >= threshold else "miss"
    return roll, result


async def open_stack(
    game_code: str,
    player_order: list,
    initial_roll: int,
    initial_result: str,
    threshold: int,
    timeout: float = 8.0,
) -> tuple:
    """
    Open La Pila for a game. Blocks until all players have passed consecutively
    or all per-player timeouts expire. Returns (final_roll, final_result).

    player_order: list of GamePlayer.id starting from the active player going clockwise.
    """
    from app.websocket.manager import manager

    if not player_order:
        return initial_roll, initial_result

    dice_item = StackItem(
        kind="dice_result",
        roll=initial_roll,
        result=initial_result,
        threshold=threshold,
        player_id=player_order[0],
    )

    session = StackSession(
        game_code=game_code,
        player_order=player_order,
        active_player_id=player_order[0],
        priority_player_id=player_order[0],
    )
    session.stack.append(dice_item)
    _sessions[game_code] = session

    # Broadcast stack opened to all
    await manager.broadcast(game_code, {
        "type": "stack_opened",
        "stack": _serialize_stack(session),
        "player_order": player_order,
        "priority_player_id": session.priority_player_id,
        "timeout_ms": int(timeout * 1000),
    })

    # Main priority loop
    n_players = len(player_order)
    while session.consecutive_passes < n_players:
        session._event.clear()
        # Notify current priority player
        await manager.broadcast(game_code, {
            "type": "stack_priority",
            "priority_player_id": session.priority_player_id,
            "consecutive_passes": session.consecutive_passes,
            "timeout_ms": int(timeout * 1000),
        })
        try:
            await asyncio.wait_for(session._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            # Treat as auto-pass
            timed_out = session.priority_player_id
            session.consecutive_passes += 1
            session.priority_player_id = _next_player(session)
            session._last_action = "pass"
            await manager.broadcast(game_code, {
                "type": "stack_passed",
                "player_id": timed_out,
                "auto": True,
                "consecutive_passes": session.consecutive_passes,
                "priority_player_id": session.priority_player_id,
            })
            continue

        # Event was set — check what happened
        if session._last_action == "card":
            await manager.broadcast(game_code, {
                "type": "stack_updated",
                "stack": _serialize_stack(session),
                "priority_player_id": session.priority_player_id,
                "consecutive_passes": session.consecutive_passes,
                "timeout_ms": int(timeout * 1000),
            })
        elif session._last_action == "pass":
            await manager.broadcast(game_code, {
                "type": "stack_passed",
                "player_id": _get_prev_player(session),
                "auto": False,
                "consecutive_passes": session.consecutive_passes,
                "priority_player_id": session.priority_player_id,
            })

    # Resolve
    final_roll, final_result = _compute_final(session)
    session.final_roll = final_roll
    session.final_result = final_result

    await manager.broadcast(game_code, {
        "type": "stack_resolved",
        "stack": _serialize_stack(session),
        "final_roll": final_roll,
        "final_result": final_result,
    })

    _sessions.pop(game_code, None)
    return final_roll, final_result


def _get_prev_player(session: StackSession) -> int:
    """Return the player who just passed (before priority advanced)."""
    order = session.player_order
    try:
        idx = order.index(session.priority_player_id)
    except ValueError:
        return session.active_player_id
    return order[(idx - 1) % len(order)]


def _serialize_stack(session: StackSession) -> list:
    return [
        {
            "kind": item.kind,
            "roll": item.roll,
            "result": item.result,
            "threshold": item.threshold,
            "player_id": item.player_id,
            "card_id": item.card_id,
            "card_name": item.card_name,
            "played_by": item.played_by,
            "roll_modifier": item.roll_modifier,
            "force_reroll": item.force_reroll,
        }
        for item in session.stack
    ]
