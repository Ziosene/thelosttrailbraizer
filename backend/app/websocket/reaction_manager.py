"""
Gestisce le finestre di reazione out-of-turn tra giocatori.

Quando un giocatore gioca una carta che colpisce un avversario, il server apre
una finestra di reazione: l'avversario ha N secondi per rispondere con una carta
"Fuori dal proprio turno" o passare. L'intera sincronizzazione è in-memory tramite
asyncio.Event — nessun dato transitorio finisce nel DB.

API pubblica:
  open_reaction_window(game_code, target_player_id, timeout) -> dict | None
  resolve_reaction(game_code, player_id, response) -> bool
  has_pending_reaction(game_code, player_id) -> bool
"""
import asyncio
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _Slot:
    event: asyncio.Event = field(default_factory=asyncio.Event)
    response: Optional[dict] = None


_pending: dict[str, _Slot] = {}


def _key(game_code: str, player_id: int) -> str:
    return f"{game_code}:{player_id}"


async def open_reaction_window(
    game_code: str,
    target_player_id: int,
    timeout: float = 8.0,
) -> Optional[dict]:
    """Apre una finestra di reazione per target_player_id e attende la risposta.

    Restituisce il dict di risposta ({"action": "play", "hand_card_id": N}
    oppure {"action": "pass"}), o None se il timeout scade.
    """
    k = _key(game_code, target_player_id)
    slot = _Slot()
    _pending[k] = slot
    try:
        await asyncio.wait_for(slot.event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        _pending.pop(k, None)
    return slot.response


def resolve_reaction(game_code: str, player_id: int, response: dict) -> bool:
    """Segnala la risposta del giocatore (play o pass).

    Restituisce True se c'era una finestra aperta per questo giocatore,
    False altrimenti (messaggio ignorato).
    """
    slot = _pending.get(_key(game_code, player_id))
    if slot is None:
        return False
    slot.response = response
    slot.event.set()
    return True


def has_pending_reaction(game_code: str, player_id: int) -> bool:
    return _key(game_code, player_id) in _pending
