"""Carte Economiche — guadagna/ruba Licenze o Certificazioni (carte 1–8, 41–48)."""
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


def _card_41(player, game, db, *, target_player_id=None) -> dict:
    """Journey Builder — +1L per ogni boss sconfitto in questa partita (max 6)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    amount = min(player.bosses_defeated, 6)
    player.licenze += amount
    return {"applied": True, "licenze_gained": amount, "bosses_defeated": player.bosses_defeated}


def _card_42(player, game, db, *, target_player_id=None) -> dict:
    """Engagement Studio — +3L se non hai combattuto in questo turno.

    Checks fought_this_turn flag set by _handle_start_combat.
    draw_card (FASE INIZIALE) clears the flag each new turn.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    if (player.combat_state or {}).get("fought_this_turn"):
        return {"applied": False, "reason": "already_fought_this_turn"}
    player.licenze += 3
    return {"applied": True, "licenze_gained": 3}


def _card_43(player, game, db, *, target_player_id=None) -> dict:
    """Drip Program — +1L ora, +1L inizio prossimo turno, +1L in quello successivo.

    Stores drip_program_remaining=2 in combat_state.
    draw_card (FASE INIZIALE) checks this flag: +1L per turno, decrementa, rimuove a 0.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.licenze += 1
    cs = dict(player.combat_state or {})
    cs["drip_program_remaining"] = 2
    player.combat_state = cs
    return {"applied": True, "licenze_gained": 1, "drip_program_remaining": 2}


def _card_44(player, game, db, *, target_player_id=None) -> dict:
    """Object Store — Deposita fino a 3L in storage protetto (non rubabili).

    Moves min(3, player.licenze) from licenze into combat_state["object_store_licenze"].
    draw_card (FASE INIZIALE) auto-restituisce le licenze stored all'inizio del turno successivo.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    amount = min(3, player.licenze)
    if amount == 0:
        return {"applied": False, "reason": "no_licenze_to_store"}
    player.licenze -= amount
    cs = dict(player.combat_state or {})
    cs["object_store_licenze"] = cs.get("object_store_licenze", 0) + amount
    player.combat_state = cs
    return {"applied": True, "licenze_stored": amount, "total_stored": cs["object_store_licenze"]}


def _card_45(player, game, db, *, target_player_id=None) -> dict:
    """Prospect Score — Guadagna Licenze pari ai boss sconfitti in questa partita (max 5)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    amount = min(player.bosses_defeated, 5)
    player.licenze += amount
    return {"applied": True, "licenze_gained": amount, "bosses_defeated": player.bosses_defeated}


def _card_46(player, game, db, *, target_player_id=None) -> dict:
    """Bundle Option — +2L per ogni AddOn che possiedi (max 6)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    amount = min(len(player.addons) * 2, 6)
    player.licenze += amount
    return {"applied": True, "licenze_gained": amount, "addon_count": len(player.addons)}


def _card_47(player, game, db, *, target_player_id=None) -> dict:
    """Contracted Price — Il prossimo AddOn che acquisti costa esattamente 5L.

    Stores next_addon_price_fixed=5 in combat_state.
    turn.py _handle_buy_addon checks and consumes this flag.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = dict(player.combat_state or {})
    cs["next_addon_price_fixed"] = 5
    player.combat_state = cs
    return {"applied": True, "next_addon_price_fixed": 5}


def _card_48(player, game, db, *, target_player_id=None) -> dict:
    """Price Rule — Il prossimo AddOn che acquisti costa 3L in meno.

    Stores next_addon_price_discount=3 in combat_state.
    turn.py _handle_buy_addon checks and consumes this flag.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = dict(player.combat_state or {})
    cs["next_addon_price_discount"] = cs.get("next_addon_price_discount", 0) + 3
    player.combat_state = cs
    return {"applied": True, "next_addon_price_discount": 3}


ECONOMICA: dict = {
    1: _card_1,
    2: _card_2,
    3: _card_3,
    4: _card_4,
    5: _card_5,
    6: _card_6,
    7: _card_7,
    8: _card_8,
    41: _card_41,
    42: _card_42,
    43: _card_43,
    44: _card_44,
    45: _card_45,
    46: _card_46,
    47: _card_47,
    48: _card_48,
}
