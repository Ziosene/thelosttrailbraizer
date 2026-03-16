"""Carte Interferenza — giocabili durante il turno altrui (carte 38–40, 70–79)."""
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


def _card_70(player, game, db, *, target_player_id=None) -> dict:
    """Suppression List — Un avversario non può pescare carte nella sua prossima fase draw.

    Stores suppressed_draw=True in target's combat_state.
    turn.py _handle_draw_card: if flag set, skips the card draw and clears the flag.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["suppressed_draw"] = True
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "suppressed_draw": True}


def _card_71(player, game, db, *, target_player_id=None) -> dict:
    """Anypoint MQ — Metti 1 carta dalla tua mano nella coda di un avversario (la pesca per prima).

    Takes a random card from player's hand, queues it for target's next draw.
    Stores forced_queue_card_id=N in target's combat_state.
    turn.py _handle_draw_card: if flag set, gives that card first (instead of deck draw), clears flag.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    hand = list(player.hand)
    if not hand:
        return {"applied": False, "reason": "no_cards_in_hand"}
    import random as _rnd
    hc = _rnd.choice(hand)
    queued_card_id = hc.action_card_id
    db.delete(hc)
    cs = dict(target.combat_state or {})
    cs["forced_queue_card_id"] = queued_card_id
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "queued_card_id": queued_card_id}


def _card_72(player, game, db, *, target_player_id=None) -> dict:
    """Engagement Split — Forza il prossimo tiro dado di un avversario: deve ritirarlo (secondo risultato).

    Stores forced_reroll_next=True in target's combat_state.
    combat.py _handle_roll_dice: if flag set, rolls base dice twice and takes the second result.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat:
        return {"applied": False, "reason": "target_not_in_combat"}
    cs = dict(target.combat_state or {})
    cs["forced_reroll_next"] = True
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "forced_reroll_next": True}


def _card_73(player, game, db, *, target_player_id=None) -> dict:
    """Completion Action — Copia l'effetto di una carta economica avversaria (guadagni le sue Licenze).

    Simplified: +2L immediately (average economic card gain).
    TODO: reactive implementation via event="on_opponent_played_economica".
    """
    player.licenze += 2
    return {"applied": True, "licenze_gained": 2, "note": "simplified_immediate_gain"}


def _card_74(player, game, db, *, target_player_id=None) -> dict:
    """Routing Configuration — Assegna il prossimo boss del mazzo a un avversario.

    Target must fight the assigned boss at their next turn or lose 2 Licenze.
    Stores routing_assigned=True (+ routing_assigned_boss_id) in target's combat_state.
    TODO: turn.py _handle_draw_card: enforce by checking routing_assigned flag.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    boss_id = (game.boss_deck_1 or [None])[0] or (game.boss_deck_2 or [None])[0]
    cs = dict(target.combat_state or {})
    cs["routing_assigned"] = True
    if boss_id:
        cs["routing_assigned_boss_id"] = boss_id
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "routing_assigned_boss_id": boss_id}


def _card_75(player, game, db, *, target_player_id=None) -> dict:
    """Triggered Send — Ruba 2L dalla ricompensa boss di un avversario (prima che combatta).

    Simplified: steal 2L from target directly.
    TODO: reactive trigger via event="on_opponent_drew_boss".
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    stolen = min(2, target.licenze)
    target.licenze -= stolen
    player.licenze += stolen
    return {"applied": True, "target_player_id": target.id, "licenze_stolen": stolen}


def _card_76(player, game, db, *, target_player_id=None) -> dict:
    """Milestone Action — Guadagni 1L ogni round che un avversario sopravvive in combattimento (max 4).

    Stores milestone_action_remaining=4 in player's combat_state.
    combat.py _handle_roll_dice: after each non-lethal round, all watchers with this flag +1L.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = dict(player.combat_state or {})
    cs["milestone_action_remaining"] = 4
    player.combat_state = cs
    return {"applied": True, "milestone_action_remaining": 4}


def _card_77(player, game, db, *, target_player_id=None) -> dict:
    """Kafka Connector — Per 2 turni, guadagni 1L ogni volta che qualsiasi giocatore gioca una carta.

    Simplified: +3L immediately (expected value ~2 turns × 1.5 cards/turn).
    TODO: store kafka_connector_turns=2 flag; hook in turn.py play_card to award 1L per play.
    """
    player.licenze += 3
    return {"applied": True, "licenze_gained": 3, "note": "simplified_expected_value"}


def _card_78(player, game, db, *, target_player_id=None) -> dict:
    """Custom Redirect — Reindirizza una carta azione avversaria diretta a te verso un altro.

    Reaction-only card: played via play_reaction in the reaction window.
    If played normally via play_card, this handler is never reached (guard in turn.py).
    TODO: implement redirect logic in the reaction window resolution.
    """
    return {"applied": False, "reason": "reaction_only_card"}


def _card_79(player, game, db, *, target_player_id=None) -> dict:
    """SMS Studio — Un avversario perde 1 HP immediatamente."""
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    target.hp = max(0, target.hp - 1)
    return {"applied": True, "target_player_id": target.id, "target_hp_damage": 1}


INTERFERENZA: dict = {
    38: _card_38,
    39: _card_39,
    40: _card_40,
    70: _card_70,
    71: _card_71,
    72: _card_72,
    73: _card_73,
    74: _card_74,
    75: _card_75,
    76: _card_76,
    77: _card_77,
    78: _card_78,
    79: _card_79,
}
