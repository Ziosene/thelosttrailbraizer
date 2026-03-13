"""Carte Interferenza — giocabili durante il turno altrui (carte 38–40)."""
from app.models.card import BossCard
from .helpers import get_target


def _card_38(player, game, db, *, target_player_id=None) -> dict:
    """Consulting Hours — Durante il combattimento di un alleato, abbassa la soglia dado del boss di 2 per 2 round.

    Stores consulting_hours_until_round and consulting_hours_threshold_reduction in
    TARGET ally's combat_state. combat.py subtracts the reduction from effective threshold.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat:
        return {"applied": False, "reason": "target_not_in_combat"}

    cs = dict(target.combat_state or {})
    until_round = (target.combat_round or 0) + 2
    cs["consulting_hours_until_round"] = until_round
    cs["consulting_hours_threshold_reduction"] = 2
    target.combat_state = cs
    return {
        "applied": True,
        "target_player_id": target.id,
        "threshold_reduction": 2,
        "until_round": until_round,
    }


def _card_39(player, game, db, *, target_player_id=None) -> dict:
    """War Room — Durante il combattimento di un avversario, il boss recupera 1 HP (può superare il massimo).

    Intentionally no cap — the card text says "può superare il massimo originale".
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat or target.current_boss_hp is None:
        return {"applied": False, "reason": "target_not_in_combat"}

    target.current_boss_hp += 1
    return {"applied": True, "target_player_id": target.id, "boss_healed": 1}


def _card_40(player, game, db, *, target_player_id=None) -> dict:
    """Dreamforce Keynote — Tutti i giocatori guadagnano 3L (o 5L se hai 4+ cert). Pesca 1 carta.

    Legendary. Base: all players +3 Licenze; if caster has 4+ certificazioni, caster gets
    5 instead of 3 (i.e. +2 extra). Player also draws 1 card from the action deck.
    """
    from app.models.game import PlayerHandCard

    # All players +3 Licenze
    for p in game.players:
        p.licenze += 3

    # Caster bonus if 4+ cert (already got +3 above, add the extra 2)
    caster_bonus = 5 if player.certificazioni >= 4 else 3
    if caster_bonus > 3:
        player.licenze += (caster_bonus - 3)

    # Caster draws 1 card
    drawn = 0
    if game.action_deck_1:
        db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
        drawn = 1
    elif game.action_deck_2:
        db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
        drawn = 1

    return {
        "applied": True,
        "licenze_to_all": 3,
        "caster_total_licenze_gained": caster_bonus,
        "cards_drawn": drawn,
    }


INTERFERENZA: dict = {
    38: _card_38,
    39: _card_39,
    40: _card_40,
}
