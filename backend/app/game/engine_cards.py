"""
Pure functions for action card effects.

apply_action_card_effect(card, player, game, db, *, target_player_id=None) -> dict

Called after the card has already been removed from the player's hand and placed in
the discard pile. All DB mutations happen in-place; the caller is responsible for
committing.  Returns a result dict that the handler can include in the broadcast.
"""
from sqlalchemy.orm import Session

from app.models.game import GamePlayer, GameSession
from app.models.card import ActionCard


def apply_action_card_effect(
    card: ActionCard,
    player: GamePlayer,
    game: GameSession,
    db: Session,
    *,
    target_player_id: int | None = None,
) -> dict:
    """Dispatch to per-card effect by card.number. Returns a result dict."""
    n = card.number
    handlers = {
        1:  _card_1_quick_win,
        2:  _card_2_pipeline_closed_won,
        3:  _card_3_forecasting_boost,
        4:  _card_4_license_audit,
        5:  _card_5_contract_renewal,
        6:  _card_6_certification_heist,
        7:  _card_7_chargeback,
        8:  _card_8_revenue_cloud,
        9:  _card_9_apex_hammer,
        10: _card_10_soql_blast,
    }
    fn = handlers.get(n)
    if fn is None:
        return {"card_number": n, "applied": False, "reason": "not_implemented"}

    result = fn(player, game, db, target_player_id=target_player_id)
    result["card_number"] = n
    return result


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_target(
    game: GameSession,
    player: GamePlayer,
    target_player_id: int | None,
) -> "GamePlayer | None":
    """Return a valid opponent from game.players, or None."""
    if target_player_id is None:
        return None
    return next(
        (p for p in game.players if p.id == target_player_id and p.id != player.id),
        None,
    )


# ── Card implementations ──────────────────────────────────────────────────────

def _card_1_quick_win(player, game, db, *, target_player_id=None) -> dict:
    """Quick Win — Guadagna 2 Licenze (fuori combattimento)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.licenze += 2
    return {"applied": True, "licenze_gained": 2}


def _card_2_pipeline_closed_won(player, game, db, *, target_player_id=None) -> dict:
    """Pipeline Closed Won — Guadagna 4 Licenze (fuori combattimento)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.licenze += 4
    return {"applied": True, "licenze_gained": 4}


def _card_3_forecasting_boost(player, game, db, *, target_player_id=None) -> dict:
    """Forecasting Boost — +3L; +5 se è il primo turno (turn_number == 1)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    amount = 5 if game.turn_number <= 1 else 3
    player.licenze += amount
    return {"applied": True, "licenze_gained": amount}


def _card_4_license_audit(player, game, db, *, target_player_id=None) -> dict:
    """License Audit — Ruba 2 Licenze a un avversario a tua scelta."""
    target = _get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    stolen = min(2, target.licenze)
    target.licenze -= stolen
    player.licenze += stolen
    return {"applied": True, "licenze_stolen": stolen, "from_player_id": target.id}


def _card_5_contract_renewal(player, game, db, *, target_player_id=None) -> dict:
    """Contract Renewal — Interferenza: ruba 3 Licenze della ricompensa boss a un avversario.

    Full mechanic: played out-of-turn when an opponent defeats a boss to intercept
    3 of their reward licenze.  Simplified (in-turn version): steal 3L from target.
    TODO: implement out-of-turn reactive trigger (event="on_opponent_boss_defeated").
    """
    target = _get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    stolen = min(3, target.licenze)
    target.licenze -= stolen
    player.licenze += stolen
    return {"applied": True, "licenze_stolen": stolen, "from_player_id": target.id}


def _card_6_certification_heist(player, game, db, *, target_player_id=None) -> dict:
    """Certification Heist — Ruba 1 Certificazione; l'avversario riceve 3 Licenze."""
    target = _get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.trophies:
        return {"applied": False, "reason": "target_has_no_trophies"}
    trophy_id = target.trophies[0]
    # SQLAlchemy JSON mutation: full reassignment required
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


def _card_7_chargeback(player, game, db, *, target_player_id=None) -> dict:
    """Chargeback — Interferenza: recupera le Licenze rubate e guadagnane 1 in più.

    Full mechanic: reactive, played when an opponent steals your licenze, so you
    recover the exact amount stolen plus 1 bonus.
    Simplified (in-turn version): gain 2 Licenze (1 recovered + 1 bonus).
    TODO: implement out-of-turn reactive trigger (event="on_licenze_stolen_from_you").
    """
    player.licenze += 2
    return {"applied": True, "licenze_gained": 2}


def _card_8_revenue_cloud(player, game, db, *, target_player_id=None) -> dict:
    """Revenue Cloud — Guadagna 1 Licenza per ogni AddOn posseduto (max 5)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    amount = min(len(player.addons), 5)
    player.licenze += amount
    return {"applied": True, "licenze_gained": amount, "addon_count": len(player.addons)}


def _card_9_apex_hammer(player, game, db, *, target_player_id=None) -> dict:
    """Apex Hammer — Il boss subisce 2 HP di danno immediato (solo in combattimento)."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    damage = 2
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage}


def _card_10_soql_blast(player, game, db, *, target_player_id=None) -> dict:
    """SOQL Blast — Boss -1 HP; se abilità attiva: disabilita per 2 round.

    The disable is stored in player.combat_state["boss_ability_disabled_until_round"].
    combat.py must check this key before applying boss ability effects each round.
    """
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 1)
    current_round = (player.combat_round or 0) + 1
    cs = dict(player.combat_state or {})
    disable_until = current_round + 2  # disabled for THIS round + 2 more
    cs["boss_ability_disabled_until_round"] = disable_until
    player.combat_state = cs
    return {
        "applied": True,
        "boss_damage": 1,
        "boss_ability_disabled_until_round": disable_until,
    }
