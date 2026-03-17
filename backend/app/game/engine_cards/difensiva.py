"""Carte Difensive — cura, protezioni, HP (carte 19–25, 55–58, 96–100, 131–135)."""
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
    """Backup & Restore — Recupera 1 HP e pesca 1 carta."""
    from app.models.game import PlayerHandCard

    player.hp = min(player.max_hp, player.hp + 1)

    drew = 0
    src = game.action_deck_1 if game.action_deck_1 else game.action_deck_2
    if src:
        db.add(PlayerHandCard(player_id=player.id, action_card_id=src.pop(0)))
        drew = 1

    return {"applied": True, "hp_restored": 1, "drew": drew}


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


def _card_96(player, game, db, *, target_player_id=None) -> dict:
    """Review App — Primo round: soglia dado boss -2.

    Stores review_app_active=True in combat_state.
    combat.py: if flag set and current_round == 1, threshold -= 2, then clears flag.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["review_app_active"] = True
    player.combat_state = cs
    return {"applied": True, "review_app_active": True}


def _card_97(player, game, db, *, target_player_id=None) -> dict:
    """Fault Path — Sui prossimi 3 tiri falliti, guadagni 1L invece di perdere HP.

    Stores fault_path_remaining=3 in combat_state.
    combat.py miss branch: if fault_path_remaining > 0, +1L, skip HP damage, decrement counter.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["fault_path_remaining"] = cs.get("fault_path_remaining", 0) + 3
    player.combat_state = cs
    return {"applied": True, "fault_path_remaining": cs["fault_path_remaining"]}



def _card_99(player, game, db, *, target_player_id=None) -> dict:
    """Web-to-Case — La prossima azione offensiva contro di te viene annullata (bloccata prima di colpirti).

    Stores web_to_case_active=True in combat_state.
    turn.py _handle_play_card: if target has this flag and card is Offensiva, blocks the effect.
    """
    cs = dict(player.combat_state or {})
    cs["web_to_case_active"] = True
    player.combat_state = cs
    return {"applied": True, "web_to_case_active": True}


def _card_100(player, game, db, *, target_player_id=None) -> dict:
    """Preference Center — Immunità a 1 tipo di carta (Offensiva/Economica/Manipolazione dado) per questo turno.

    Client signals type choice via target_player_id:
      1 → immune to "Offensiva"
      2 → immune to "Economica"
      3 → immune to "Manipolazione dado"
    Stores preference_immunity_type=<card_type> in combat_state.
    turn.py _handle_play_card: if card type == immune type and player is the target, blocks effect.
    """
    type_map = {1: "Offensiva", 2: "Economica", 3: "Manipolazione dado"}
    immune_type = type_map.get(target_player_id)
    if not immune_type:
        return {"applied": False, "reason": "send 1=Offensiva, 2=Economica, 3=Manipolazione dado as target_player_id"}
    cs = dict(player.combat_state or {})
    cs["preference_immunity_type"] = immune_type
    player.combat_state = cs
    return {"applied": True, "preference_immunity_type": immune_type}


def _card_131(player, game, db, *, target_player_id=None) -> dict:
    """SLA Policy — Per 3 round il boss non può infliggerti >1HP per round.

    Reuses entitlement_process_until_round (same as card 58) — cap player damage to 1.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    until_round = current_round + 2  # this round + next 2 = 3 rounds total
    cs = dict(player.combat_state or {})
    cs["entitlement_process_until_round"] = max(cs.get("entitlement_process_until_round", 0), until_round)
    player.combat_state = cs
    return {"applied": True, "entitlement_process_until_round": until_round}


def _card_132(player, game, db, *, target_player_id=None) -> dict:
    """Escalation Rule — Quando subisci ≥2HP in un round, la metà viene assorbita.

    Stores escalation_rule_active=True in combat_state.
    combat.py: before applying multi-HP damage (e.g. queue_routing_double), absorb half (floor).
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["escalation_rule_active"] = True
    player.combat_state = cs
    return {"applied": True, "escalation_rule_active": True}


def _card_133(player, game, db, *, target_player_id=None) -> dict:
    """Contact Center Integration — Per 2 round, ogni HP perso → pesca 1 carta.

    Stores contact_center_until_round=current_round+2 in combat_state.
    combat.py miss branch (actual HP damage): if flag active, draw 1 action card.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    until_round = current_round + 1  # this round + next = 2 rounds total
    cs = dict(player.combat_state or {})
    cs["contact_center_until_round"] = max(cs.get("contact_center_until_round", 0), until_round)
    player.combat_state = cs
    return {"applied": True, "contact_center_until_round": until_round}


def _card_134(player, game, db, *, target_player_id=None) -> dict:
    """Macro Builder — Il prossimo tiro dado si esegue automaticamente (ottimizza timing = +1 al dado).

    Reuses einstein_sto_next_roll_bonus (same as card 60): +1 to next roll.
    The "automatic execution" is a client-side UX signal only — server-side: +1 bonus.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["einstein_sto_next_roll_bonus"] = cs.get("einstein_sto_next_roll_bonus", 0) + 1
    player.combat_state = cs
    return {"applied": True, "einstein_sto_next_roll_bonus": cs["einstein_sto_next_roll_bonus"]}


def _card_135(player, game, db, *, target_player_id=None) -> dict:
    """Omni Supervisor — Boss non può usare la propria abilità speciale per 2 round.

    Reuses boss_ability_disabled_until_round (same as cards 10/21/102).
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    until_round = current_round + 1  # this round + next = 2 rounds
    cs = dict(player.combat_state or {})
    cs["boss_ability_disabled_until_round"] = max(cs.get("boss_ability_disabled_until_round", 0), until_round)
    player.combat_state = cs
    return {"applied": True, "boss_ability_disabled_until_round": until_round}


def _card_151(player, game, db, *, target_player_id=None) -> dict:
    """Hyperforce Migration — Per 1 round: boss non può alzare la soglia dado né usare la sua abilità.

    Stores hyperforce_until_round=current_round+1.
    combat.py: if active, clear threshold_bonus from boss and treat boss ability as disabled.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    until_round = current_round + 1
    cs = dict(player.combat_state or {})
    cs["hyperforce_until_round"] = max(cs.get("hyperforce_until_round", 0), until_round)
    player.combat_state = cs
    return {"applied": True, "hyperforce_until_round": until_round}


def _card_152(player, game, db, *, target_player_id=None) -> dict:
    """Net Zero Commitment — Ogni HP perso questo turno → +1 Licenza.

    Stores net_zero_commitment_active=True.
    combat.py miss branch: on actual HP loss, award +1L per HP taken, while flag is set.
    """
    cs = dict(player.combat_state or {})
    cs["net_zero_commitment_active"] = True
    player.combat_state = cs
    return {"applied": True, "net_zero_commitment_active": True}


def _card_153(player, game, db, *, target_player_id=None) -> dict:
    """Environment Branch — Il prossimo danno che subisci viene reindirizzato al giocatore a sinistra e a destra (1HP ciascuno).

    Stores environment_branch_active=True.
    combat.py miss branch: if flag set, skip own HP damage, find left/right neighbours by
    player order index and deal 1HP to each, then clear flag.
    """
    cs = dict(player.combat_state or {})
    cs["environment_branch_active"] = True
    player.combat_state = cs
    return {"applied": True, "environment_branch_active": True}


def _card_154(player, game, db, *, target_player_id=None) -> dict:
    """Sustainability Cloud — Ogni HP perso questo turno riduce di 1 il costo del prossimo AddOn (max -3).

    Stores sustainability_discount_pending=True + sustainability_hp_lost=0.
    combat.py miss branch: if flag active, sustainability_hp_lost += _player_hp_damage (capped at 3).
    turn.py buy_addon: apply min(3, sustainability_hp_lost) as extra discount, clear both flags.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "cannot_use_in_combat"}
    cs = dict(player.combat_state or {})
    cs["sustainability_discount_pending"] = True
    cs.setdefault("sustainability_hp_lost", 0)
    player.combat_state = cs
    return {"applied": True, "sustainability_discount_pending": True}


def _card_155(player, game, db, *, target_player_id=None) -> dict:
    """Public Sector Solutions — Per questo turno nessuna carta avversaria può ridurre i tuoi HP.

    Stores public_sector_hp_immune=True.
    turn.py play_card immunity block: if target has this flag and card is Offensiva, block HP damage.
    Flag is cleared in end_turn (single-turn effect).
    """
    cs = dict(player.combat_state or {})
    cs["public_sector_hp_immune"] = True
    player.combat_state = cs
    return {"applied": True, "public_sector_hp_immune": True}


def _card_156(player, game, db, *, target_player_id=None) -> dict:
    """Travel Time Calc — Se manchi per 1 punto dalla soglia (roll == threshold-1), eviti il danno.

    Stores travel_time_calc_active=True.
    combat.py miss branch: before HP damage, if roll == threshold - 1, skip damage, clear flag.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["travel_time_calc_active"] = True
    player.combat_state = cs
    return {"applied": True, "travel_time_calc_active": True}


def _card_157(player, game, db, *, target_player_id=None) -> dict:
    """Resource Leveling — Il giocatore con più Licenze dà 2L al giocatore con meno.

    If the caster is the poorest, they receive. No-op if all tied or single player.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "cannot_use_in_combat"}
    all_players = list(game.players)
    if len(all_players) < 2:
        return {"applied": True, "note": "only_one_player"}
    richest = max(all_players, key=lambda p: p.licenze)
    poorest = min(all_players, key=lambda p: p.licenze)
    if richest.id == poorest.id:
        return {"applied": True, "note": "all_equal_licenze"}
    transfer = min(2, richest.licenze)
    richest.licenze -= transfer
    poorest.licenze += transfer
    return {
        "applied": True,
        "from_player_id": richest.id,
        "to_player_id": poorest.id,
        "licenze_transferred": transfer,
    }


def _card_158(player, game, db, *, target_player_id=None) -> dict:
    """Runtime Manager — Nel prossimo combattimento, se muori sopravvivi con 1HP (una volta).

    Stores runtime_manager_ready=True in combat_state (cross-turn flag, persists across turns).
    combat.py death check: if player.hp <= 0 and flag set, hp=1, clear flag.
    Similar to card 23 (Disaster Recovery) but activated outside combat.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "cannot_use_in_combat"}
    cs = dict(player.combat_state or {})
    cs["runtime_manager_ready"] = True
    player.combat_state = cs
    return {"applied": True, "runtime_manager_ready": True}


def _card_201(player, game, db, *, target_player_id=None) -> dict:
    """Web Studio — Carte offensive avversarie fanno 1 danno in meno per questo turno (min 0).

    Stores web_studio_active=True in combat_state.
    turn.py play_card: if targeting this player with Offensiva card and flag set, -1 to damage effect.
    """
    cs = dict(player.combat_state or {})
    cs["web_studio_active"] = True
    player.combat_state = cs
    return {"applied": True, "web_studio_active": True}


def _card_202(player, game, db, *, target_player_id=None) -> dict:
    """Prospect Grade — +L in base alla posizione in classifica per Licenze.

    1° = 5L, 2° = 3L, 3° = 2L, 4°+ = 1L.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    all_players = sorted(game.players, key=lambda p: p.licenze, reverse=True)
    rank = next((i + 1 for i, p in enumerate(all_players) if p.id == player.id), len(all_players))
    reward = {1: 5, 2: 3, 3: 2}.get(rank, 1)
    player.licenze += reward
    return {"applied": True, "rank": rank, "licenze_gained": reward}


def _card_203(player, game, db, *, target_player_id=None) -> dict:
    """Sender Profile — Per 1 round la soglia dado conta come 2 punti più bassa.

    Stores sender_profile_threshold_reduction=2 in combat_state.
    combat.py: effective_threshold = max(1, threshold - sender_profile_threshold_reduction); consume flag.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["sender_profile_threshold_reduction"] = 2
    player.combat_state = cs
    return {"applied": True, "threshold_reduction": 2}


def _card_204(player, game, db, *, target_player_id=None) -> dict:
    """Delivery Profile — Il danno del prossimo round di combattimento non arriva (bloccato in transito).

    Stores delivery_profile_block_active=True in combat_state.
    combat.py miss branch: if flag set, skip HP damage once and clear flag.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["delivery_profile_block_active"] = True
    player.combat_state = cs
    return {"applied": True, "delivery_profile_block_active": True}


def _card_205(player, game, db, *, target_player_id=None) -> dict:
    """MicroSite — +1L per ogni turno passato senza essere attaccato in questa partita (max 4).

    Uses turns_not_attacked counter in combat_state (incremented by combat.py when player takes no damage).
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = dict(player.combat_state or {})
    turns_safe = cs.get("turns_not_attacked", 0)
    reward = min(4, turns_safe)
    player.licenze += reward
    return {"applied": True, "turns_not_attacked": turns_safe, "licenze_gained": reward}


def _card_206(player, game, db, *, target_player_id=None) -> dict:
    """Landing Page — Il prossimo avversario che ti attacca ti dà 2 Licenze invece di danno.

    Stores landing_page_active=True. turn.py play_card: if Offensiva targeting this player and flag, +2L instead.
    """
    cs = dict(player.combat_state or {})
    cs["landing_page_active"] = True
    player.combat_state = cs
    return {"applied": True, "landing_page_active": True}


def _card_207(player, game, db, *, target_player_id=None) -> dict:
    """Feedback Management — Ogni carta giocata contro di te questo turno genera 1L (max 3).

    Stores feedback_management_remaining=3. turn.py play_card: if targeting this player, +1L to them, decrement.
    """
    cs = dict(player.combat_state or {})
    cs["feedback_management_remaining"] = 3
    player.combat_state = cs
    return {"applied": True, "feedback_management_remaining": 3}


def _card_258(player, game, db, *, target_player_id=None) -> dict:
    """Salesforce Tower — Per 1 turno l'HP non può scendere sotto 1 (bastione).

    Stores salesforce_tower_active=True. combat.py miss branch: player.hp = max(1, new_hp).
    Cleared in end_turn.
    """
    cs = dict(player.combat_state or {})
    cs["salesforce_tower_active"] = True
    player.combat_state = cs
    return {"applied": True, "salesforce_tower_active": True}


def _card_259(player, game, db, *, target_player_id=None) -> dict:
    """Nonprofit Success Pack — +2HP; il giocatore con meno HP recupera anche 1HP."""
    player.hp = min(player.max_hp, player.hp + 2)
    # Also heal the most injured player (excluding self if not worst)
    weakest = min(game.players, key=lambda p: p.hp)
    if weakest.id != player.id:
        weakest.hp = min(weakest.max_hp, weakest.hp + 1)
        return {"applied": True, "self_healed": 2, "weakest_healed": weakest.id}
    return {"applied": True, "self_healed": 2}


def _card_260(player, game, db, *, target_player_id=None) -> dict:
    """Admin Hero — +2HP e draw 1 se Ruolo è Administrator; altrimenti +1HP.

    Checks player.role (Mapped[str | None]). Admin roles: 'Administrator', 'Advanced Administrator'.
    """
    from app.models.game import PlayerHandCard as _PHC260
    admin_roles = {"Administrator", "Advanced Administrator", "administrator", "advanced_administrator"}
    is_admin = (player.role or "") in admin_roles
    if is_admin:
        player.hp = min(player.max_hp, player.hp + 2)
        drew = False
        if game.action_deck_1:
            db.add(_PHC260(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            drew = True
        elif game.action_deck_2:
            db.add(_PHC260(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
            drew = True
        return {"applied": True, "healed": 2, "drew_card": drew, "admin": True}
    player.hp = min(player.max_hp, player.hp + 1)
    return {"applied": True, "healed": 1, "admin": False}


def _card_288(player, game, db, *, target_player_id=None) -> dict:
    """NullPointerException — Se il prossimo tiro combattimento è 1, il round è annullato."""
    cs = dict(player.combat_state or {})
    cs["null_pointer_active"] = True
    player.combat_state = cs
    return {"applied": True, "effect": "next_roll_1_nullifies_round"}


def _card_295(player, game, db, *, target_player_id=None) -> dict:
    """Trust First — Annulla la prima carta Offensiva diretta contro di te (per sempre)."""
    cs = dict(player.combat_state or {})
    cs["trust_first_active"] = True
    player.combat_state = cs
    return {"applied": True, "effect": "cancel_first_offensiva_targeting_me"}


DIFENSIVA: dict = {
    19:  _card_19,
    20:  _card_20,
    21:  _card_21,
    22:  _card_22,
    23:  _card_23,
    24:  _card_24,
    25:  _card_25,
    55:  _card_55,
    56:  _card_56,
    57:  _card_57,
    58:  _card_58,
    96:  _card_96,
    97:  _card_97,
    99:  _card_99,
    100: _card_100,
    131: _card_131,
    132: _card_132,
    133: _card_133,
    134: _card_134,
    135: _card_135,
    151: _card_151,
    152: _card_152,
    153: _card_153,
    154: _card_154,
    155: _card_155,
    156: _card_156,
    157: _card_157,
    158: _card_158,
    201: _card_201,
    202: _card_202,
    203: _card_203,
    204: _card_204,
    205: _card_205,
    206: _card_206,
    207: _card_207,
    258: _card_258,
    259: _card_259,
    260: _card_260,
    288: _card_288,
    295: _card_295,
}
