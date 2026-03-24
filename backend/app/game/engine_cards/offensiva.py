"""Carte Offensive — danno a boss o avversari (carte 9–18, 49–54, 89–95, 126–130)."""
import random

from sqlalchemy.orm import Session

from app.models.game import GamePlayer, GameSession
from app.models.card import BossCard
from app.game import engine
from .helpers import get_target


def _card_9(player, game, db, *, target_player_id=None) -> dict:
    """Apex Hammer — Il boss subisce 2 HP di danno immediato."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 2)
    return {"applied": True, "boss_damage": 2}


def _card_10(player, game, db, *, target_player_id=None) -> dict:
    """SOQL Blast — Boss -1HP."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 1)
    return {"applied": True, "boss_damage": 1}


def _card_11(player, game, db, *, target_player_id=None) -> dict:
    """Force.com Lightning Strike — Boss -3HP immediato. Non puoi giocare altre carte questo turno."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 3)
    # Lock out further card plays this turn
    player.cards_played_this_turn = engine.MAX_CARDS_PER_TURN
    return {"applied": True, "boss_damage": 3, "no_more_cards_this_turn": True}


def _card_12(player, game, db, *, target_player_id=None) -> dict:
    """Governor Limit Exploit — Per 3 round ogni hit infligge 2HP al boss invece di 1.

    Stores double_damage_until_round in combat_state.
    combat.py applies the double damage when resolving a hit.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    cs = dict(player.combat_state or {})
    # Applies to THIS round and the next 2 (3 rounds total)
    double_until = current_round + 2
    cs["double_damage_until_round"] = double_until
    player.combat_state = cs
    return {"applied": True, "double_damage_until_round": double_until}


def _card_13(player, game, db, *, target_player_id=None) -> dict:
    """Debug Exploit — Abbassa la soglia dado del boss di 2 per il resto del combattimento.

    Accumulates boss_threshold_reduction in combat_state.
    combat.py subtracts this from the effective threshold every round.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["boss_threshold_reduction"] = cs.get("boss_threshold_reduction", 0) + 2
    player.combat_state = cs
    return {"applied": True, "boss_threshold_reduction": cs["boss_threshold_reduction"]}


def _card_14(player, game, db, *, target_player_id=None) -> dict:
    """Hotfix Deploy — Boss -1HP; giocatore +1HP."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 1)
    player.hp = min(player.max_hp, player.hp + 1)
    return {"applied": True, "boss_damage": 1, "player_healed": 1}


def _card_15(player, game, db, *, target_player_id=None) -> dict:
    """Scope Creep — Interferenza: durante il combattimento di un avversario, boss threshold +2 per 1 round.

    Stores boss_threshold_increase_until_round in TARGET player's combat_state.
    combat.py adds 2 to threshold when that player rolls, for 1 round only.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat:
        return {"applied": False, "reason": "target_not_in_combat"}
    cs = dict(target.combat_state or {})
    # Applies to the next roll of the target (their current combat_round + 1)
    cs["boss_threshold_increase_until_round"] = (target.combat_round or 0) + 1
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "threshold_increase": 2}


def _card_16(player, game, db, *, target_player_id=None) -> dict:
    """Change Request — Interferenza: durante il combattimento di un avversario, il boss recupera 1HP."""
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat or target.current_boss_id is None or target.current_boss_hp is None:
        return {"applied": False, "reason": "target_not_in_combat"}
    boss_card = db.get(BossCard, target.current_boss_id)
    if not boss_card:
        return {"applied": False, "reason": "boss_not_found"}
    target.current_boss_hp = min(boss_card.hp, target.current_boss_hp + 1)
    return {"applied": True, "target_player_id": target.id, "boss_healed": 1}


def _card_17(player, game, db, *, target_player_id=None) -> dict:
    """Technical Debt Bomb — Avversario perde 1HP; se è il suo turno, perde anche 1 carta."""
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    target.hp = max(0, target.hp - 1)
    result: dict = {"applied": True, "target_player_id": target.id, "target_hp_damage": 1}
    # Check if it's the target's turn
    current_actor_id = game.turn_order[game.current_turn_index] if game.turn_order else None
    if current_actor_id == target.id and target.hand:
        hc = random.choice(list(target.hand))
        game.action_discard = (game.action_discard or []) + [hc.action_card_id]
        db.delete(hc)
        result["target_card_discarded"] = True
    return result


def _card_18(player, game, db, *, target_player_id=None) -> dict:
    """Org Takeover — Un avversario non può acquistare AddOn nel suo prossimo turno.

    Stores addons_blocked_next_turn=True in target's combat_state.
    turn.py _handle_buy_addon checks this flag.
    turn.py _handle_end_turn clears it when the target ends their turn.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["addons_blocked_next_turn"] = True
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id}


def _card_49(player, game, db, *, target_player_id=None) -> dict:
    """DataWeave Transform — Boss -2HP immediato."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 2)
    return {"applied": True, "boss_damage": 2}


def _card_50(player, game, db, *, target_player_id=None) -> dict:
    """Scatter-Gather — Boss -1HP; tira dado: se ≥6, altri -1HP.

    The bonus roll is a dedicated roll independent from the combat round roll.
    """
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 1)
    bonus_roll = engine.roll_d10()
    bonus_hit = bonus_roll >= 6
    if bonus_hit:
        player.current_boss_hp = max(0, player.current_boss_hp - 1)
    return {
        "applied": True,
        "boss_damage": 2 if bonus_hit else 1,
        "bonus_roll": bonus_roll,
        "bonus_hit": bonus_hit,
    }


def _card_51(player, game, db, *, target_player_id=None) -> dict:
    """CloudHub Worker — Boss -1HP per AddOn posseduto (max 3)."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    damage = min(len(player.addons), 3)
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage, "addon_count": len(player.addons)}


def _card_52(player, game, db, *, target_player_id=None) -> dict:
    """Product Rule — Boss -2HP se ha >3HP rimasti, altrimenti -1HP."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    damage = 2 if player.current_boss_hp > 3 else 1
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage}


def _card_53(player, game, db, *, target_player_id=None) -> dict:
    """AMPscript Block — Blocca l'abilità del boss per 2 round.

    Sets boss_ability_disabled_until_round = current_round + 2 in combat_state.
    combat.py skips apply_boss_ability calls while this flag is active.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    disabled_until = (player.combat_round or 0) + 2
    cs = dict(player.combat_state or {})
    cs["boss_ability_disabled_until_round"] = max(
        cs.get("boss_ability_disabled_until_round", 0), disabled_until
    )
    player.combat_state = cs
    return {"applied": True, "boss_ability_disabled_until_round": disabled_until}


def _card_54(player, game, db, *, target_player_id=None) -> dict:
    """On Error Propagate — Boss -1HP; la sua abilità propaga al giocatore alla tua sinistra (-1HP).

    Boss damage is immediate. Left-neighbour collateral damage is also immediate.
    """
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 1)
    result: dict = {"applied": True, "boss_damage": 1}
    turn_order = game.turn_order or []
    if player.id in turn_order:
        idx = turn_order.index(player.id)
        left_id = turn_order[(idx - 1) % len(turn_order)]
        left_player = next((p for p in game.players if p.id == left_id and p.id != player.id), None)
        if left_player:
            left_player.hp = max(0, left_player.hp - 1)
            result["collateral_player_id"] = left_player.id
            result["collateral_damage"] = 1
    return result


def _card_89(player, game, db, *, target_player_id=None) -> dict:
    """Constraint Rule — Soglia dado boss -2 permanente per il resto del combattimento (a tuo vantaggio).

    Stacks with card 13 (Debug Exploit) by incrementing boss_threshold_reduction.
    combat.py: threshold -= combat_state["boss_threshold_reduction"]
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["boss_threshold_reduction"] = cs.get("boss_threshold_reduction", 0) + 2
    player.combat_state = cs
    return {"applied": True, "boss_threshold_reduction": cs["boss_threshold_reduction"]}


def _card_90(player, game, db, *, target_player_id=None) -> dict:
    """Configuration Attribute — Boss HP massimi -1 (riduce HP correnti di 1 per il resto del combat)."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 1)
    return {"applied": True, "boss_hp_reduced_by": 1, "boss_hp_remaining": player.current_boss_hp}


def _card_91(player, game, db, *, target_player_id=None) -> dict:
    """Guided Selling — Soglia dado -1 per 2 round (su se stesso).

    Reuses consulting_hours keys in own combat_state.
    combat.py: subtracts consulting_hours_threshold_reduction while consulting_hours_until_round >= current_round.
    Stacks with card 38 (Consulting Hours from ally) by adding to existing reduction.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    until_round = current_round + 1  # applies to current round + next (2 rounds total)
    cs = dict(player.combat_state or {})
    # Stack with existing consulting_hours if already active
    existing_red = cs.get("consulting_hours_threshold_reduction", 0) if cs.get("consulting_hours_until_round", 0) >= current_round else 0
    cs["consulting_hours_until_round"] = max(cs.get("consulting_hours_until_round", 0), until_round)
    cs["consulting_hours_threshold_reduction"] = existing_red + 1
    player.combat_state = cs
    return {"applied": True, "threshold_reduction": 1, "until_round": until_round}


def _card_92(player, game, db, *, target_player_id=None) -> dict:
    """Case Escalation — Boss -1HP. Se il boss ti ha già colpito: -2HP e abilità disabilitata 1 round.

    Checks combat_boss_hits_received in combat_state (incremented in combat.py on player damage).
    combat.py: increments combat_boss_hits_received when player takes damage (miss branch).
    """
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    cs = player.combat_state or {}
    boss_has_hit = cs.get("combat_boss_hits_received", 0) > 0
    damage = 2 if boss_has_hit else 1
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    result: dict = {"applied": True, "boss_hp_damage": damage, "boss_has_hit": boss_has_hit}
    if boss_has_hit:
        # Also disable boss ability for 1 round
        current_round = (player.combat_round or 0) + 1
        new_cs = dict(cs)
        new_cs["boss_ability_disabled_until_round"] = current_round
        player.combat_state = new_cs
        result["boss_ability_disabled_until_round"] = current_round
    return result


def _card_93(player, game, db, *, target_player_id=None) -> dict:
    """Live Message — Un avversario perde 2 Licenze; può recuperarle cedendo 1 carta a te.

    Deducts 2L from target immediately. Stores live_message_pending_caster_id=player.id
    in target's combat_state to open a response window.
    ClientAction 'live_message_respond' on target: if they choose to give a card,
    the handler moves 1 random card from target's hand to caster's hand and restores 2L.
    """
    from .helpers import get_target
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if (target.combat_state or {}).get("licenze_theft_immune"):
        return {"applied": False, "reason": "target_immune"}
    stolen = min(2, target.licenze)
    target.licenze -= stolen
    if target.hand:
        cs = dict(target.combat_state or {})
        cs["live_message_pending_caster_id"] = player.id
        target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "licenze_lost": stolen,
            "recovery_available": bool(target.hand)}


def _card_94(player, game, db, *, target_player_id=None) -> dict:
    """Territory Assignment Rule — Guarda i primi 3 boss di uno dei due mazzi e scegline 1 da mettere in cima."""
    src = game.boss_deck_1 if game.boss_deck_1 else game.boss_deck_2
    if not src:
        return {"applied": False, "reason": "no_boss_deck"}
    choices = src[:3]
    return {
        "status": "pending_choice",
        "choice_type": "choose_boss_to_front",
        "card_number": 94,
        "choices": choices,
    }


def _card_95(player, game, db, *, target_player_id=None) -> dict:
    """Heroku CI — Se boss HP ≤ 2, il prossimo hit lo sconfigge istantaneamente.

    Stores heroku_ci_active=True in combat_state.
    combat.py hit branch: if flag set and current_boss_hp <= 2, sets boss hp = 0 immediately.
    """
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["heroku_ci_active"] = True
    player.combat_state = cs
    return {"applied": True, "heroku_ci_active": True, "current_boss_hp": player.current_boss_hp}


def _card_126(player, game, db, *, target_player_id=None) -> dict:
    """Case Assignment Rule — Assegna il boss a un altro giocatore; tu esci e tieni la ricompensa."""
    if not player.is_in_combat or not player.current_boss_id:
        return {"applied": False, "reason": "not_in_combat"}
    if not target_player_id or target_player_id == player.id:
        return {"applied": False, "reason": "invalid_target"}
    from app.models.card import BossCard as _BC126
    from app.models.game import GamePlayer as _GP126
    target126 = db.get(_GP126, target_player_id)
    if not target126 or target126.game_id != player.game_id:
        return {"applied": False, "reason": "invalid_target"}
    if target126.is_in_combat:
        return {"applied": False, "reason": "target_already_in_combat"}
    boss = db.get(_BC126, player.current_boss_id)
    reward = boss.reward_licenze if boss else 0
    # Assign boss to target player at its current HP
    target126.is_in_combat = True
    target126.current_boss_id = player.current_boss_id
    target126.current_boss_hp = player.current_boss_hp
    target126.current_boss_source = player.current_boss_source
    target126.combat_round = 0
    # Caster exits combat and collects reward
    player.licenze += reward
    player.is_in_combat = False
    player.current_boss_id = None
    player.current_boss_hp = None
    player.current_boss_source = None
    player.combat_round = 0
    return {"applied": True, "licenze_gained": reward, "boss_reassigned_to": target_player_id}


def _card_127(player, game, db, *, target_player_id=None) -> dict:
    """Omni-Channel — Per questo round, ogni hit infligge 1HP aggiuntivo al boss.

    Stores omni_channel_next_hit_bonus=1 in combat_state.
    combat.py hit branch: if flag set, _hit_damage += 1, clear flag.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["omni_channel_next_hit_bonus"] = 1
    player.combat_state = cs
    return {"applied": True, "omni_channel_next_hit_bonus": 1}


def _card_128(player, game, db, *, target_player_id=None) -> dict:
    """Einstein Case Classification — Boss classificato "critico": soglia dado -2 per 3 round.

    Reuses consulting_hours keys (same as card 38/91) but for 3 rounds.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    until_round = current_round + 2  # this round + next 2 = 3 rounds total
    cs = dict(player.combat_state or {})
    existing_red = cs.get("consulting_hours_threshold_reduction", 0) if cs.get("consulting_hours_until_round", 0) >= current_round else 0
    cs["consulting_hours_until_round"] = max(cs.get("consulting_hours_until_round", 0), until_round)
    cs["consulting_hours_threshold_reduction"] = existing_red + 2
    player.combat_state = cs
    return {"applied": True, "threshold_reduction": 2, "until_round": until_round}


def _card_129(player, game, db, *, target_player_id=None) -> dict:
    """Boss Dossier — Boss -2HP, ma perdi 1L."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 2)
    player.licenze = max(0, player.licenze - 1)
    return {"applied": True, "boss_hp_damage": 2, "licenze_lost": 1}


def _card_130(player, game, db, *, target_player_id=None) -> dict:
    """Queue-Based Routing — Salta l'attacco boss questo round; doppio danno nel prossimo.

    Sets force_field_until_round=current_round (same as card 30: no player damage this round).
    Sets queue_routing_double_damage_round=current_round+1 for next round.
    combat.py miss branch: if queue_routing_double_damage_round == current_round, player.hp -= 2.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    cs = dict(player.combat_state or {})
    cs["force_field_until_round"] = current_round
    cs["queue_routing_double_damage_round"] = current_round + 1
    player.combat_state = cs
    return {"applied": True, "protected_this_round": current_round, "double_damage_next_round": current_round + 1}


def _card_141(player, game, db, *, target_player_id=None) -> dict:
    """Manufacturing Cloud — 1HP al boss per ogni AddOn Passivo posseduto (max 4)."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    from app.models.card import AddonCard as _ADC141
    passive_count = sum(
        1 for pa in player.addons
        if (a := db.get(_ADC141, pa.addon_id)) and a.addon_type.value == "Passivo"
    )
    damage = min(4, passive_count)
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage, "passive_addons_counted": passive_count}


def _card_142(player, game, db, *, target_player_id=None) -> dict:
    """Automotive Cloud — Per 2 round, tira il dado 2 volte e prendi il risultato più alto.

    Stores best_of_2_until_round in combat_state.
    combat.py: after base roll, if flag active, roll again and keep the higher result.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    until_round = current_round + 1  # this round + next = 2 rounds total
    cs = dict(player.combat_state or {})
    cs["best_of_2_until_round"] = max(cs.get("best_of_2_until_round", 0), until_round)
    player.combat_state = cs
    return {"applied": True, "best_of_2_until_round": until_round}


def _card_143(player, game, db, *, target_player_id=None) -> dict:
    """Industries Cloud — Il boss subisce 1HP per ogni Certificazione posseduta."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    damage = max(0, player.certificazioni)
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage, "certificazioni": player.certificazioni}


def _card_144(player, game, db, *, target_player_id=None) -> dict:
    """Appointment Bundle — 1HP al boss per ogni carta giocata questo turno (inclusa questa)."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    # cards_played_this_turn already incremented before handler is called
    damage = max(1, player.cards_played_this_turn)
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage, "cards_played_this_turn": player.cards_played_this_turn}


def _card_145(player, game, db, *, target_player_id=None) -> dict:
    """Service Territory — 1HP al boss; 2HP se il boss ha già colpito un altro giocatore in partita.

    Simplified proxy: 2HP if any player has bosses_defeated > 0 (fights have happened → boss hit players).
    """
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    any_fight = any(p.bosses_defeated > 0 for p in game.players)
    damage = 2 if any_fight else 1
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage, "double_damage": any_fight}


def _card_146(player, game, db, *, target_player_id=None) -> dict:
    """Digital HQ — 1HP al boss per ogni tipo di carta diverso già giocato questo turno (max 4).

    Reads card_types_played_this_turn list from combat_state (populated by turn.py after each play).
    Fallback: uses cards_played_this_turn count when tracking data is unavailable.
    """
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    types_played = (player.combat_state or {}).get("card_types_played_this_turn", [])
    if types_played:
        damage = min(4, len(set(types_played)))
    else:
        damage = min(4, max(1, player.cards_played_this_turn))
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage, "distinct_types": len(set(types_played))}


def _card_147(player, game, db, *, target_player_id=None) -> dict:
    """Agentforce Action — 2HP al boss; 3HP se possiedi almeno 1 AddOn Leggendario."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    from app.models.card import AddonCard as _ADC147
    has_legendary = any(
        (a := db.get(_ADC147, pa.addon_id)) and a.addon_type.value == "Leggendario"
        for pa in player.addons
    )
    damage = 3 if has_legendary else 2
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage, "legendary_bonus": has_legendary}


def _card_148(player, game, db, *, target_player_id=None) -> dict:
    """Loop Element — 1HP aggiuntivo per ogni round vinto (hit) finora in questo combat (max 3).

    Reads combat_hits_dealt from combat_state (updated in combat.py hit branch).
    """
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    hits_dealt = (player.combat_state or {}).get("combat_hits_dealt", 0)
    damage = min(3, hits_dealt)
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage, "hits_dealt_so_far": hits_dealt}


def _card_149(player, game, db, *, target_player_id=None) -> dict:
    """Activation Target — Boss designato: abilità speciale disabilitata per tutto il combat.

    Sets boss_ability_disabled_until_round=9999 (same mechanism as cards 21/135).
    Intended for use at combat start.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["boss_ability_disabled_until_round"] = 9999
    player.combat_state = cs
    return {"applied": True, "boss_ability_permanently_disabled": True}


def _card_150(player, game, db, *, target_player_id=None) -> dict:
    """Orchestration Flow — Leggendaria. Tutti gli AddOn si attivano simultaneamente (anche tappati).

    Untaps all addons so the player can re-use them this turn.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    count = sum(1 for pa in player.addons if pa.is_tapped)
    for pa in player.addons:
        pa.is_tapped = False
    return {"applied": True, "addons_untapped": count}


def _card_191(player, game, db, *, target_player_id=None) -> dict:
    """Autolaunched Flow — Boss -2HP, ma il giocatore va a 1 HP."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 2)
    player.hp = 1
    return {"applied": True, "boss_damage": 2, "player_hp_set_to": 1}


def _card_192(player, game, db, *, target_player_id=None) -> dict:
    """Screen Flow — Per 1 round puoi sostituire il tiro del dado con valore fisso 7.

    Sets screen_flow_active=True. combat.py: after roll, if flag set and roll < 7, use 7 instead.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["screen_flow_active"] = True
    player.combat_state = cs
    return {"applied": True, "screen_flow_active": True}


def _card_193(player, game, db, *, target_player_id=None) -> dict:
    """Decision Element — Un avversario perde 2L e 1HP."""
    from app.game.engine_cards.helpers import get_target
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    target.licenze = max(0, target.licenze - 2)
    target.hp = max(0, target.hp - 1)
    return {"applied": True, "target_id": target.id, "licenze_lost": 2, "hp_lost": 1}


def _card_194(player, game, db, *, target_player_id=None) -> dict:
    """Assignment Element — Ridistribuisci le Licenze tra te e 1 avversario; tu prendi la metà superiore.

    Requires target_player_id.
    """
    if not target_player_id:
        return {"applied": False, "reason": "target_required"}
    from app.game.engine_cards.helpers import get_target
    import math
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "target_not_found"}
    total = player.licenze + target.licenze
    player.licenze = math.ceil(total / 2)
    target.licenze = total - player.licenze
    return {"applied": True, "total_licenze": total, "player_gets": player.licenze, "target_gets": target.licenze}


def _card_195(player, game, db, *, target_player_id=None) -> dict:
    """Subflow — Recupera 1HP e infliggi 1HP al boss."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.hp = min(player.max_hp, player.hp + 1)
    player.current_boss_hp = max(0, player.current_boss_hp - 1)
    return {"applied": True, "hp_restored": 1, "boss_damage": 1}


def _card_228(player, game, db, *, target_player_id=None) -> dict:
    """Runtime Fabric — Deploy ovunque: boss -1HP; se HP > 2 → -2HP invece.

    Adaptive damage based on remaining boss HP.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_hp = player.current_boss_hp or 0
    damage = 2 if current_hp > 2 else 1
    player.current_boss_hp = max(0, current_hp - damage)
    return {"applied": True, "boss_damage": damage, "boss_hp_before": current_hp}


def _card_231(player, game, db, *, target_player_id=None) -> dict:
    """Mule Event — In combattimento: boss -1HP e pesca 1 carta azione."""
    from app.models.game import PlayerHandCard as _PHC231
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 1)
    drew = False
    if game.action_deck_1:
        db.add(_PHC231(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
        drew = True
    elif game.action_deck_2:
        db.add(_PHC231(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
        drew = True
    return {"applied": True, "boss_damage": 1, "drew_card": drew}


def _card_233(player, game, db, *, target_player_id=None) -> dict:
    """Mule Flow — Flusso dati: boss -1HP per carta in mano (max 3HP)."""
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    damage = min(3, len(list(player.hand)))
    if damage == 0:
        return {"applied": False, "reason": "empty_hand"}
    player.current_boss_hp = max(0, player.current_boss_hp - damage)
    return {"applied": True, "boss_damage": damage, "hand_size": len(list(player.hand))}


def _card_240(player, game, db, *, target_player_id=None) -> dict:
    """Batch Scope — Boss -2HP, tu +1HP."""
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 2)
    player.hp = min(player.hp + 1, player.max_hp)
    return {"applied": True, "boss_damage": 2, "player_healed": 1}


def _card_261(player, game, db, *, target_player_id=None) -> dict:
    """CTA Board — Boss con HP ≤ 3 → sconfitto immediatamente (esame fallito)."""
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_hp = player.current_boss_hp or 0
    if current_hp <= 3:
        player.current_boss_hp = 0
        return {"applied": True, "boss_defeated": True, "boss_hp_was": current_hp}
    return {"applied": False, "reason": "boss_hp_too_high", "boss_hp": current_hp}


def _card_262(player, game, db, *, target_player_id=None) -> dict:
    """World Tour Event — Tutte le ricompense boss +2L per 1 turno; chi combatte primo +1L extra.

    Stores world_tour_event_turns=1 + world_tour_event_first_bonus=True in player's combat_state.
    combat.py boss defeat: if world_tour_event_active in any player's state, add +2L to reward.
    Simplified: set flag for all players; combat.py bonus at boss defeat checks it.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    for gp in game.players:
        cs = dict(gp.combat_state or {})
        cs["world_tour_event_active"] = True
        gp.combat_state = cs
    # First combat bonus stored on the caster
    cs_caster = dict(player.combat_state)
    cs_caster["world_tour_event_first_bonus"] = True
    player.combat_state = cs_caster
    return {"applied": True, "players_affected": len(list(game.players))}


def _card_281(player, game, db, *, target_player_id=None) -> dict:
    """World's Most Innovative (Leggendaria) — Disabilita l'abilità del boss e riduci la soglia a 1; boss -1HP."""
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["boss_ability_disabled_until_round"] = 9999
    cs["boss_threshold_override_1"] = True
    player.combat_state = cs
    if hasattr(game, "current_boss") and game.current_boss:
        game.current_boss.hp = max(0, game.current_boss.hp - 1)
        return {"applied": True, "boss_hp_reduced": 1}
    return {"applied": True, "boss_hp_reduced": 0}


def _card_290(player, game, db, *, target_player_id=None) -> dict:
    """Lorem Ipsum Boss (Offensiva/Utilità) — Guadagna +2L e conta un boss sconfitto extra."""
    player.licenze += 2
    player.bosses_defeated = (player.bosses_defeated or 0) + 1
    return {"applied": True, "licenze_gained": 2, "bosses_defeated_bonus": 1}


def _card_300(player, game, db, *, target_player_id=None) -> dict:
    """IdeaExchange Champion (Leggendaria, usa una volta) — A: boss hp=0; B: ruba 1cert; C: +10L."""
    cs = dict(player.combat_state or {})
    if cs.get("ideaexchange_champion_used"):
        return {"applied": False, "reason": "already_used"}
    cs["ideaexchange_champion_used"] = True
    player.combat_state = cs
    # State-based choice: in combat → A (boss hp=0); else if target → B (steal cert); else → C (+10L)
    if player.is_in_combat and hasattr(game, "current_boss") and game.current_boss:
        game.current_boss.hp = 0
        return {"applied": True, "choice": "A", "effect": "boss_hp_zeroed"}
    if target_player_id:
        from app.game.engine_cards.helpers import get_target
        target = get_target(game, player, target_player_id)
        if target and target.certificazioni > 0:
            # Addon 28 (Shield Platform Encryption): immunity to certification theft
            from app.game.engine_addons import has_addon as _ha28_oe
            if _ha28_oe(target, 28):
                return {"applied": False, "reason": "shield_platform_encryption", "target_id": target.id}
            target.certificazioni -= 1
            player.certificazioni += 1
            return {"applied": True, "choice": "B", "stolen_cert": 1}
    player.licenze += 10
    return {"applied": True, "choice": "C", "licenze_gained": 10}


OFFENSIVA: dict = {
    9:   _card_9,
    10:  _card_10,
    11:  _card_11,
    12:  _card_12,
    13:  _card_13,
    14:  _card_14,
    15:  _card_15,
    16:  _card_16,
    17:  _card_17,
    18:  _card_18,
    49:  _card_49,
    50:  _card_50,
    51:  _card_51,
    52:  _card_52,
    53:  _card_53,
    54:  _card_54,
    89:  _card_89,
    90:  _card_90,
    91:  _card_91,
    92:  _card_92,
    93:  _card_93,
    94:  _card_94,
    95:  _card_95,
    126: _card_126,
    127: _card_127,
    128: _card_128,
    129: _card_129,
    130: _card_130,
    141: _card_141,
    142: _card_142,
    143: _card_143,
    144: _card_144,
    145: _card_145,
    146: _card_146,
    147: _card_147,
    148: _card_148,
    149: _card_149,
    150: _card_150,
    191: _card_191,
    192: _card_192,
    193: _card_193,
    194: _card_194,
    195: _card_195,
    228: _card_228,
    231: _card_231,
    233: _card_233,
    240: _card_240,
    261: _card_261,
    262: _card_262,
    281: _card_281,
    290: _card_290,
    300: _card_300,
}
