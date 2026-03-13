"""
engine_cards — effetti delle carte azione.

Ogni categoria ha il suo modulo:
  economica.py   — carte Economiche  (guadagna/ruba Licenze, Certificazioni)
  offensiva.py   — carte Offensive   (danno a boss o avversari)
  difensiva.py   — carte Difensive   (cura, scudi, HP)
  manipolazione.py — Manipolazione dado (TODO)
  interferenza.py  — Interferenza pura (TODO)
  utilita.py       — Utilità (pesca, scarto, mazzo) (TODO)

Ogni modulo espone un dict {card_number: handler_fn}.
apply_action_card_effect è l'unico entry-point pubblico.
"""
from .economica import ECONOMICA
from .offensiva import OFFENSIVA
from .difensiva import DIFENSIVA

_HANDLERS: dict = {
    **ECONOMICA,
    **OFFENSIVA,
    **DIFENSIVA,
}


def apply_action_card_effect(card, player, game, db, *, target_player_id=None) -> dict:
    """Dispatch to the per-card effect handler by card.number.

    The card must already have been removed from the player's hand and placed
    in the discard pile before calling this. All DB mutations happen in-place;
    the caller commits.

    Returns a result dict included in the CARD_PLAYED broadcast.
    """
    fn = _HANDLERS.get(card.number)
    if fn is None:
        return {"card_number": card.number, "applied": False, "reason": "not_implemented"}
    result = fn(player, game, db, target_player_id=target_player_id)
    result["card_number"] = card.number
    return result
