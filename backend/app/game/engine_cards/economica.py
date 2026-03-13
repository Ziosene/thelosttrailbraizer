"""Carte Economiche — guadagna/ruba Licenze o Certificazioni (carte 1–8)."""
from .helpers import get_target


def _card_1(player, game, db, *, target_player_id=None) -> dict:
    """Quick Win — Guadagna 2 Licenze (fuori combattimento)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.licenze += 2
    return {"applied": True, "licenze_gained": 2}


def _card_2(player, game, db, *, target_player_id=None) -> dict:
    """Pipeline Closed Won — Guadagna 4 Licenze (fuori combattimento)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.licenze += 4
    return {"applied": True, "licenze_gained": 4}


def _card_3(player, game, db, *, target_player_id=None) -> dict:
    """Forecasting Boost — +3L; +5L se è il primo turno (turn_number ≤ 1)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    amount = 5 if game.turn_number <= 1 else 3
    player.licenze += amount
    return {"applied": True, "licenze_gained": amount}


def _card_4(player, game, db, *, target_player_id=None) -> dict:
    """License Audit — Ruba 2 Licenze a un avversario a tua scelta."""
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    stolen = min(2, target.licenze)
    target.licenze -= stolen
    player.licenze += stolen
    return {"applied": True, "licenze_stolen": stolen, "from_player_id": target.id}


def _card_5(player, game, db, *, target_player_id=None) -> dict:
    """Contract Renewal — Interferenza: ruba 3 Licenze dalla ricompensa boss di un avversario.

    Full mechanic: played out-of-turn when an opponent defeats a boss, intercepting 3
    of their reward licenze.
    Simplified (in-turn version): steal 3L from chosen target.
    TODO: out-of-turn reactive trigger (event="on_opponent_boss_defeated").
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    stolen = min(3, target.licenze)
    target.licenze -= stolen
    player.licenze += stolen
    return {"applied": True, "licenze_stolen": stolen, "from_player_id": target.id}


def _card_6(player, game, db, *, target_player_id=None) -> dict:
    """Certification Heist — Ruba 1 Certificazione; l'avversario riceve 3 Licenze."""
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.trophies:
        return {"applied": False, "reason": "target_has_no_trophies"}
    trophy_id = target.trophies[0]
    # SQLAlchemy JSON: full reassignment required to detect mutation
    target.trophies = target.trophies[1:]
    target.certificazioni = max(0, target.certificazioni - 1)
    player.trophies = (player.trophies or []) + [trophy_id]
    player.certificazioni = (player.certificazioni or 0) + 1
    target.licenze += 3
    return {
        "applied": True,
        "trophy_stolen_boss_id": trophy_id,
        "from_player_id": target.id,
        "target_compensation_licenze": 3,
    }


def _card_7(player, game, db, *, target_player_id=None) -> dict:
    """Chargeback — Interferenza: recupera le Licenze rubate + 1 extra.

    Full mechanic: reactive, played when an opponent steals your licenze.
    Simplified (in-turn version): gain 2 Licenze (1 recovered + 1 bonus).
    TODO: out-of-turn reactive trigger (event="on_licenze_stolen_from_you").
    """
    player.licenze += 2
    return {"applied": True, "licenze_gained": 2}


def _card_8(player, game, db, *, target_player_id=None) -> dict:
    """Revenue Cloud — Guadagna 1 Licenza per ogni AddOn posseduto (max 5)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    amount = min(len(player.addons), 5)
    player.licenze += amount
    return {"applied": True, "licenze_gained": amount, "addon_count": len(player.addons)}


ECONOMICA: dict = {
    1: _card_1,
    2: _card_2,
    3: _card_3,
    4: _card_4,
    5: _card_5,
    6: _card_6,
    7: _card_7,
    8: _card_8,
}
