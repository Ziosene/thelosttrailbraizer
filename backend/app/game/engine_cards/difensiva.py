"""Carte Difensive — cura, protezioni, HP (carte 19–20)."""


def _card_19(player, game, db, *, target_player_id=None) -> dict:
    """Health Cloud Restore — Recupera tutti gli HP al valore base del personaggio."""
    healed = player.max_hp - player.hp
    player.hp = player.max_hp
    return {"applied": True, "hp_restored": healed}


def _card_20(player, game, db, *, target_player_id=None) -> dict:
    """Shield Platform — Interferenza: annulla una carta azione giocata contro di te.

    Full mechanic: reactive, played out-of-turn when an opponent targets you with an
    action card. Cancels that card's effect entirely.
    Simplified: no mechanical effect when played in-turn (card is wasted if used proactively).
    TODO: out-of-turn reactive trigger (event="on_action_card_played_against_you").
    """
    return {"applied": True, "note": "reactive_card_no_in_turn_effect"}


DIFENSIVA: dict = {
    19: _card_19,
    20: _card_20,
}
