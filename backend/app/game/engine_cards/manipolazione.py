"""Carte Manipolazione Dado — modificano i tiri di dado (carte 26–30).

Tutte le carte di questa categoria lavorano tramite flag in combat_state.
combat.py (_handle_roll_dice) legge e consuma i flag prima/durante il tiro.
"""
from .helpers import get_target


def _card_26(player, game, db, *, target_player_id=None) -> dict:
    """Dice Optimizer — Il prossimo tiro di dado vale automaticamente 8.

    Stores next_roll_forced=8 in combat_state.
    combat.py reads the flag, sets roll=8, then clears it.
    Takes priority over Chaos Mode and Lucky Roll.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["next_roll_forced"] = 8
    player.combat_state = cs
    return {"applied": True, "next_roll_forced": 8}


def _card_27(player, game, db, *, target_player_id=None) -> dict:
    """Lucky Roll — Reazione post-roll: dopo aver visto il risultato del dado, ritiralo.

    Questa carta è di tipo REAZIONE e va giocata SOLO tramite la finestra di reazione
    aperta automaticamente da _handle_roll_dice dopo ogni tiro in combattimento.
    Se giocata normalmente via play_card, viene bloccata prima del consumo dal guard
    in _handle_play_card — questo handler non dovrebbe mai essere raggiunto.
    """
    return {"applied": False, "reason": "reaction_only_card"}


def _card_28(player, game, db, *, target_player_id=None) -> dict:
    """Critical System — Per 2 round, ogni tiro da 10 infligge 3 HP al boss invece di 1.

    Stores critical_system_until_round in combat_state.
    combat.py: if roll==10 and flag active, _hit_damage = 3 (overrides Governor Limit Exploit).
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    until_round = current_round + 1  # applies to current round and next (2 rounds total)
    cs = dict(player.combat_state or {})
    cs["critical_system_until_round"] = until_round
    player.combat_state = cs
    return {"applied": True, "critical_system_until_round": until_round}


def _card_29(player, game, db, *, target_player_id=None) -> dict:
    """Chaos Mode — Interferenza: il prossimo tiro del combattente vale il risultato opposto (11 − roll).

    Stores chaos_mode_next_roll=True in TARGET player's combat_state.
    combat.py: if flag set on this player, roll = 11 - roll, then clears flag.
    e.g. a 7 becomes 4 (with threshold 5+: 7 hits but 4 misses).
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat:
        return {"applied": False, "reason": "target_not_in_combat"}
    cs = dict(target.combat_state or {})
    cs["chaos_mode_next_roll"] = True
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "chaos_mode_applied": True}


def _card_30(player, game, db, *, target_player_id=None) -> dict:
    """Force Field — Per 1 round, il tiro di dado del boss non ti può danneggiare (round neutro se fallisce).

    Stores force_field_until_round=current_round in combat_state.
    combat.py: if flag active on a miss, skips player damage entirely (neutral round).
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    cs = dict(player.combat_state or {})
    cs["force_field_until_round"] = current_round
    player.combat_state = cs
    return {"applied": True, "force_field_until_round": current_round}


MANIPOLAZIONE: dict = {
    26: _card_26,
    27: _card_27,
    28: _card_28,
    29: _card_29,
    30: _card_30,
}
