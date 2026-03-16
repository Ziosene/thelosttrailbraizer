"""Carte Manipolazione Dado — modificano i tiri di dado (carte 26–30, 59–62, 101–105).

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


def _card_59(player, game, db, *, target_player_id=None) -> dict:
    """Dynamic Content — Dopo aver visto il dado, puoi ritirarlo (prendi il secondo risultato).

    Stores dynamic_content_reroll=True in combat_state.
    combat.py: after a miss result, if flag set, automatically rerolls once and clears flag.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["dynamic_content_reroll"] = True
    player.combat_state = cs
    return {"applied": True, "dynamic_content_reroll": True}


def _card_60(player, game, db, *, target_player_id=None) -> dict:
    """Einstein STO — Ottimizza il timing del tiro: +1 al prossimo tiro di dado.

    Stores einstein_sto_next_roll_bonus=1 in combat_state.
    combat.py: adds 1 to the roll after base roll (before other modifiers), capped at 10.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["einstein_sto_next_roll_bonus"] = 1
    player.combat_state = cs
    return {"applied": True, "einstein_sto_next_roll_bonus": 1}


def _card_61(player, game, db, *, target_player_id=None) -> dict:
    """Predictive Model — Dichiara il risultato (1–10) prima di tirare. Esatto → boss -2HP su hit.

    target_player_id is repurposed as the predicted roll value (1–10).
    Stores predictive_model_prediction=N in combat_state.
    combat.py: if roll == prediction and result == "hit", _hit_damage raised to 2.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    prediction = target_player_id
    if not isinstance(prediction, int) or not (1 <= prediction <= 10):
        return {"applied": False, "reason": "invalid_prediction: send 1-10 as target_player_id"}
    cs = dict(player.combat_state or {})
    cs["predictive_model_prediction"] = prediction
    player.combat_state = cs
    return {"applied": True, "predictive_model_prediction": prediction}


def _card_62(player, game, db, *, target_player_id=None) -> dict:
    """DataWeave Script — Converti qualsiasi risultato dado in 7 (fisso, non modificabile questo round).

    Sets next_roll_forced=7 — same mechanism as card 26 (Dice Optimizer) but fixed to 7.
    Takes priority over Chaos Mode, Lucky Roll, and Engagement Split.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["next_roll_forced"] = 7
    player.combat_state = cs
    return {"applied": True, "next_roll_forced": 7}


def _card_101(player, game, db, *, target_player_id=None) -> dict:
    """Next Best Offer — Pesca 3 carte (tieni 1, le altre 2 tornano in cima) + +1 al prossimo tiro.

    Draws 3 from action deck: keeps first, returns other 2 to top of action_deck_1.
    Also sets einstein_sto_next_roll_bonus=1 for the +1 to next roll.
    Simplified: client receives all 3 drawn to choose from; auto-keeps first, returns 2.
    TODO: accept chosen card ID from client for real player choice.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    from app.models.game import PlayerHandCard as _PHC101
    drawn_ids = []
    for _ in range(3):
        if game.action_deck_1:
            drawn_ids.append(game.action_deck_1.pop(0))
        elif game.action_deck_2:
            drawn_ids.append(game.action_deck_2.pop(0))
    if not drawn_ids:
        return {"applied": False, "reason": "action_deck_empty"}
    # Keep first, return remainder to top of deck_1
    db.add(_PHC101(player_id=player.id, action_card_id=drawn_ids[0]))
    if len(drawn_ids) > 1:
        game.action_deck_1 = drawn_ids[1:] + (game.action_deck_1 or [])
    # +1 to next roll
    cs = dict(player.combat_state or {})
    cs["einstein_sto_next_roll_bonus"] = cs.get("einstein_sto_next_roll_bonus", 0) + 1
    player.combat_state = cs
    return {"applied": True, "cards_drawn": 1, "cards_returned": len(drawn_ids) - 1, "roll_bonus": 1}


def _card_102(player, game, db, *, target_player_id=None) -> dict:
    """Einstein Intent — "Leggi l'intenzione" del boss — disabilita la sua abilità per 1 round.

    Stores boss_ability_disabled_until_round = current_round in combat_state.
    Same mechanism as cards 10/21 (enemy ability disabling).
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    current_round = (player.combat_round or 0) + 1
    cs = dict(player.combat_state or {})
    cs["boss_ability_disabled_until_round"] = current_round
    player.combat_state = cs
    return {"applied": True, "boss_ability_disabled_until_round": current_round}


def _card_103(player, game, db, *, target_player_id=None) -> dict:
    """Transform Element — Il prossimo miss non toglie HP ma 1 Licenza invece.

    Stores transform_element_active=True in combat_state.
    combat.py miss branch: if flag set, player.licenze -= 1 instead of player.hp -= 1, clears flag.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["transform_element_active"] = True
    player.combat_state = cs
    return {"applied": True, "transform_element_active": True}


def _card_104(player, game, db, *, target_player_id=None) -> dict:
    """Flow Variable — Assegna un valore fisso al dado: scegli 5, 7 o 9.

    target_player_id is repurposed as the chosen value (must be 5, 7, or 9).
    Sets next_roll_forced=N — same mechanism as cards 26/62.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    value = target_player_id
    if value not in (5, 7, 9):
        return {"applied": False, "reason": "invalid_value: send 5, 7, or 9 as target_player_id"}
    cs = dict(player.combat_state or {})
    cs["next_roll_forced"] = value
    player.combat_state = cs
    return {"applied": True, "next_roll_forced": value}


def _card_105(player, game, db, *, target_player_id=None) -> dict:
    """Message Transformation — Se il dado è ≤ 3, diventa 6 automaticamente (una sola volta per combat).

    Stores message_transformation_active=True in combat_state.
    combat.py: after base roll (before forced_roll check), if flag and roll <= 3, roll = 6, clears flag.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["message_transformation_active"] = True
    player.combat_state = cs
    return {"applied": True, "message_transformation_active": True}


MANIPOLAZIONE: dict = {
    26: _card_26,
    27: _card_27,
    28: _card_28,
    29: _card_29,
    30: _card_30,
    59: _card_59,
    60: _card_60,
    61: _card_61,
    62: _card_62,
    101: _card_101,
    102: _card_102,
    103: _card_103,
    104: _card_104,
    105: _card_105,
}


def _card_136(player, game, db, *, target_player_id=None) -> dict:
    """Service Forecast — Usa il valore medio (= soglia) invece di tirare il dado.

    Stores service_forecast_use_threshold=True in combat_state.
    combat.py: after computing threshold, if flag set, roll=threshold (guaranteed hit/miss at border),
    then clears the flag.
    """
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    cs = dict(player.combat_state or {})
    cs["service_forecast_use_threshold"] = True
    player.combat_state = cs
    return {"applied": True, "service_forecast_use_threshold": True}


MANIPOLAZIONE_136: dict = {136: _card_136}
