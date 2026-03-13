"""Carte Offensive — danno a boss o avversari (carte 9–18)."""
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


OFFENSIVA: dict = {
    9:  _card_9,
    10: _card_10,
    11: _card_11,
    12: _card_12,
    13: _card_13,
    14: _card_14,
    15: _card_15,
    16: _card_16,
    17: _card_17,
    18: _card_18,
}
