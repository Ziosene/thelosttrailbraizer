"""Carte Economiche — guadagna/ruba Licenze o Certificazioni (carte 1–8, 41–48, 81–88)."""
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


def _card_81(player, game, db, *, target_player_id=None) -> dict:
    """Automation Rule — +2 Licenze. Se mano < 3 carte, +4 invece."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    gain = 4 if len(list(player.hand)) < 3 else 2
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain}


def _card_82(player, game, db, *, target_player_id=None) -> dict:
    """Segmentation Rule — +1 Licenza per ogni giocatore con meno Licenze di te."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    gain = sum(1 for p in game.players if p.id != player.id and p.licenze < player.licenze)
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "qualifying_players": gain}


def _card_83(player, game, db, *, target_player_id=None) -> dict:
    """Discount Schedule — +4 Licenze (solo +2 se hai già 10 o più Licenze)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    gain = 2 if player.licenze >= 10 else 4
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain}


def _card_84(player, game, db, *, target_player_id=None) -> dict:
    """Renewal Opportunity — Paga 5 Licenze per proteggere un AddOn dalla morte.

    Stores renewal_protected=True in combat_state.
    combat.py player death: if flag set, the first AddOn is spared from the death-tap.
    """
    if player.licenze < 5:
        return {"applied": False, "reason": "not_enough_licenze (need 5)"}
    if not list(player.addons):
        return {"applied": False, "reason": "no_addons_to_protect"}
    player.licenze -= 5
    cs = dict(player.combat_state or {})
    cs["renewal_protected"] = True
    player.combat_state = cs
    return {"applied": True, "licenze_paid": 5, "renewal_protected": True}


def _card_85(player, game, db, *, target_player_id=None) -> dict:
    """Summary Variable — +1L ogni 10 Licenze totali in gioco tra tutti i giocatori (max 4)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    total = sum(p.licenze for p in game.players)
    gain = min(4, total // 10)
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "total_in_play": total}


def _card_86(player, game, db, *, target_player_id=None) -> dict:
    """Percent of Total — +30% delle Licenze del giocatore più ricco (floor, min 1)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    richest = max((p.licenze for p in game.players), default=0)
    gain = max(1, int(richest * 0.30))
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "richest_player_licenze": richest}


def _card_87(player, game, db, *, target_player_id=None) -> dict:
    """Block Pricing — +2L per ogni blocco di 5 Licenze spese in AddOn durante la partita (max 6).

    Reads total_addon_licenze_spent from combat_state (tracked in _handle_buy_addon).
    Simplified: counts len(player.addons) * 5 as estimate if no tracking present.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    total_spent = (player.combat_state or {}).get("total_addon_licenze_spent") or len(list(player.addons)) * 5
    gain = min(6, (total_spent // 5) * 2)
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "total_addon_spent": total_spent}


def _card_88(player, game, db, *, target_player_id=None) -> dict:
    """Quote Calculator — Il giocatore con meno Licenze pesca 1 carta; tu +3 Licenze."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    from app.models.game import PlayerHandCard as _PHC88
    from app.game import engine as _eng88
    # +3 Licenze to caster
    player.licenze += 3
    # Poorest player (by licenze, excluding caster) draws 1 card
    others = [p for p in game.players if p.id != player.id]
    if others:
        poorest = min(others, key=lambda p: p.licenze)
        if game.action_deck_1:
            db.add(_PHC88(player_id=poorest.id, action_card_id=game.action_deck_1.pop(0)))
        elif game.action_deck_2:
            db.add(_PHC88(player_id=poorest.id, action_card_id=game.action_deck_2.pop(0)))
    return {"applied": True, "licenze_gained": 3, "poorest_player_drew": bool(others)}


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
    81: _card_81,
    82: _card_82,
    83: _card_83,
    84: _card_84,
    85: _card_85,
    86: _card_86,
    87: _card_87,
    88: _card_88,
}
