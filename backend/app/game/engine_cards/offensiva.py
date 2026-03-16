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
    """SOQL Blast — Boss -1HP; disabilita abilità boss per 2 round.

    Stores boss_ability_disabled_until_round in combat_state.
    combat.py checks this before applying on_round_start boss effects.
    """
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, player.current_boss_hp - 1)
    current_round = (player.combat_round or 0) + 1
    cs = dict(player.combat_state or {})
    disable_until = current_round + 2
    cs["boss_ability_disabled_until_round"] = disable_until
    player.combat_state = cs
    return {"applied": True, "boss_damage": 1, "boss_ability_disabled_until_round": disable_until}


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
    """AMPscript Block — Boss abilità si ritorce contro se stesso per 1 round.

    Stores ampscript_reflected_until_round in combat_state.
    combat.py: if flag active on miss, skip boss extra_damage and deal 1HP to boss instead.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    cs = dict(player.combat_state or {})
    cs["ampscript_reflected_until_round"] = current_round
    player.combat_state = cs
    return {"applied": True, "ampscript_reflected_until_round": current_round}


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
    """Live Message — Un avversario perde 2 Licenze.

    Simplified: steal 2L (recovery mechanic requires async client interaction — TODO).
    TODO: offer target the option to give 1 card to recover the 2L.
    """
    from .helpers import get_target
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    stolen = min(2, target.licenze)
    target.licenze -= stolen
    return {"applied": True, "target_player_id": target.id, "licenze_stolen": stolen}


def _card_94(player, game, db, *, target_player_id=None) -> dict:
    """Territory Assignment Rule — Assegna il prossimo boss al target (deve combatterlo o -2L).

    Same mechanism as card 74 (Routing Configuration) but from the Offensiva category.
    Stores routing_assigned + routing_assigned_boss_id in target's combat_state.
    TODO: turn.py _handle_draw_card: enforce by checking routing_assigned flag.
    """
    from .helpers import get_target
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
    """Case Assignment Rule — Assegna il boss a un altro giocatore; tu esci e tieni la ricompensa.

    Simplified: player escapes combat immediately and receives the boss's licenze reward.
    The boss is removed from play (discarded); target player assignment not enforced.
    TODO: actually reassign boss to target player.
    """
    if not player.is_in_combat or not player.current_boss_id:
        return {"applied": False, "reason": "not_in_combat"}
    from app.models.card import BossCard as _BC126
    boss = db.get(_BC126, player.current_boss_id)
    reward = boss.reward_licenze if boss else 0
    player.licenze += reward
    player.is_in_combat = False
    player.current_boss_id = None
    player.current_boss_hp = None
    player.current_boss_source = None
    player.combat_round = 0
    return {"applied": True, "licenze_gained": reward, "combat_escaped": True}


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
    """Boss Dossier — Studia il boss: rivela la sua abilità speciale, poi infliggi 1HP."""
    if not player.is_in_combat or player.current_boss_hp is None:
        return {"applied": False, "reason": "not_in_combat"}
    from app.models.card import BossCard as _BC129
    boss = db.get(_BC129, player.current_boss_id)
    boss_info = {}
    if boss:
        boss_info = {
            "id": boss.id,
            "name": boss.name,
            "hp": boss.hp,
            "threshold": boss.dice_threshold,
            "reward_licenze": boss.reward_licenze,
            "has_certification": boss.has_certification,
        }
    player.current_boss_hp = max(0, player.current_boss_hp - 1)
    return {"applied": True, "boss_info": boss_info, "boss_hp_damage": 1}


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
}
