"""Carte Difensive — cura, protezioni, HP (carte 19–25, 55–58)."""
from app.models.game import TurnPhase


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
    """
    return {"applied": True, "note": "reactive_card_no_in_turn_effect"}


def _card_21(player, game, db, *, target_player_id=None) -> dict:
    """Rollback — Annulla l'abilità del boss per il resto del combattimento.

    Sets boss_ability_disabled_until_round=9999 in combat_state.
    combat.py already checks this flag before applying on_round_start boss effects.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["boss_ability_disabled_until_round"] = 9999
    player.combat_state = cs
    return {"applied": True, "boss_ability_permanently_disabled": True}


def _card_22(player, game, db, *, target_player_id=None) -> dict:
    """Escape Route — Termina il combattimento senza vincitori. Boss in fondo al mazzo. Nessuna conseguenza.

    Boss goes to the bottom of the corresponding deck (based on current_boss_source).
    Player resets combat state with no HP loss or death penalty.
    """
    if not player.is_in_combat or player.current_boss_id is None:
        return {"applied": False, "reason": "not_in_combat"}

    boss_id = player.current_boss_id
    source = player.current_boss_source

    # Boss goes to the BOTTOM of the appropriate deck (unlike retreat which goes to top)
    if source in ("deck_1", "market_1"):
        game.boss_deck_1 = (game.boss_deck_1 or []) + [boss_id]
    else:
        game.boss_deck_2 = (game.boss_deck_2 or []) + [boss_id]

    # Reset combat state — no consequences
    player.is_in_combat = False
    player.current_boss_id = None
    player.current_boss_hp = None
    player.current_boss_source = None
    player.combat_round = 0
    player.combat_state = {}
    game.current_phase = TurnPhase.action
    return {"applied": True, "combat_escaped": True, "boss_sent_to_deck_bottom": True}


def _card_23(player, game, db, *, target_player_id=None) -> dict:
    """Disaster Recovery — Quando stai per morire, sopravvivi con 1 HP. Non perdi nulla.

    Sets disaster_recovery_ready=True in combat_state.
    combat.py checks this BEFORE applying death: if set, player survives with 1 HP
    instead of dying. Player should play this proactively before the fatal blow.
    """
    cs = dict(player.combat_state or {})
    cs["disaster_recovery_ready"] = True
    player.combat_state = cs
    return {"applied": True, "disaster_recovery_ready": True}


def _card_24(player, game, db, *, target_player_id=None) -> dict:
    """Patch Tuesday — Recupera 1 HP (fuori da combattimento)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "cannot_use_in_combat"}
    healed = min(1, player.max_hp - player.hp)
    player.hp = min(player.max_hp, player.hp + 1)
    return {"applied": True, "hp_restored": healed}


def _card_25(player, game, db, *, target_player_id=None) -> dict:
    """Backup & Restore — Recupera 1 carta, 1 Licenza e 1 HP dall'ultimo turno in cui sei morto.

    Approximation: +1 HP, +1 Licenza, draw 1 card from action_discard into hand.
    Exact restoration of per-death penalties is not tracked persistently; this is the
    closest mechanical equivalent without a dedicated DB field.
    """
    from app.models.game import PlayerHandCard

    result: dict = {"applied": True}

    # +1 HP
    healed = min(1, player.max_hp - player.hp)
    player.hp = min(player.max_hp, player.hp + 1)
    result["hp_restored"] = healed

    # +1 Licenza
    player.licenze += 1
    result["licenze_gained"] = 1

    # Recover 1 card from discard (most recently discarded)
    discard = list(game.action_discard or [])
    if discard:
        recovered_id = discard.pop(-1)
        game.action_discard = discard
        db.add(PlayerHandCard(player_id=player.id, action_card_id=recovered_id))
        result["card_recovered"] = recovered_id

    return result


def _card_55(player, game, db, *, target_player_id=None) -> dict:
    """Try Scope — Per il prossimo round di combattimento, se fallisci non perdi HP.

    Stores try_scope_until_round in combat_state.
    combat.py: if flag active on a miss, skips player damage (same mechanic as force_field_until_round).
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    cs = dict(player.combat_state or {})
    cs["try_scope_until_round"] = current_round
    player.combat_state = cs
    return {"applied": True, "try_scope_until_round": current_round}


def _card_56(player, game, db, *, target_player_id=None) -> dict:
    """On Error Continue — Invece di morire, sopravvivi con 1HP perdendo 3L.

    Stores on_error_continue_ready=True in combat_state.
    combat.py: if player.hp <= 0 and flag set, hp=1, licenze -= 3, clear flag.
    Unlike card 23 (Disaster Recovery), this costs 3 Licenze.
    """
    cs = dict(player.combat_state or {})
    cs["on_error_continue_ready"] = True
    player.combat_state = cs
    return {"applied": True, "on_error_continue_ready": True}


def _card_57(player, game, db, *, target_player_id=None) -> dict:
    """API Proxy — La prossima carta offensiva avversaria contro di te perde 1 punto di effetto.

    Stores api_proxy_active=True in combat_state.
    TODO: offensive card handlers targeting a player check this flag and reduce effect by 1.
    """
    cs = dict(player.combat_state or {})
    cs["api_proxy_active"] = True
    player.combat_state = cs
    return {"applied": True, "api_proxy_active": True}


def _card_58(player, game, db, *, target_player_id=None) -> dict:
    """Entitlement Process — Per 3 round, il boss non può infliggerti più di 1 danno per round.

    Stores entitlement_process_until_round in combat_state.
    combat.py: caps player HP damage from boss miss to 1 per round while flag is active.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    until_round = current_round + 2  # this round + next 2 = 3 rounds total
    cs = dict(player.combat_state or {})
    cs["entitlement_process_until_round"] = until_round
    player.combat_state = cs
    return {"applied": True, "entitlement_process_until_round": until_round}


DIFENSIVA: dict = {
    19: _card_19,
    20: _card_20,
    21: _card_21,
    22: _card_22,
    23: _card_23,
    24: _card_24,
    25: _card_25,
    55: _card_55,
    56: _card_56,
    57: _card_57,
    58: _card_58,
}
