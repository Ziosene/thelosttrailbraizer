"""Carte Economiche — guadagna/ruba Licenze o Certificazioni (carte 1–8, 41–48, 81–88, 121–125)."""
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
    """Forecasting Boost — +5L."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.licenze += 5
    return {"applied": True, "licenze_gained": 5}


def _card_4(player, game, db, *, target_player_id=None) -> dict:
    """License Audit — Ruba 2 Licenze a un avversario a tua scelta."""
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if (target.combat_state or {}).get("licenze_theft_immune"):
        return {"applied": False, "reason": "target_immune"}
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
    if (target.combat_state or {}).get("licenze_theft_immune"):
        return {"applied": False, "reason": "target_immune"}
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
    # Addon 28 (Shield Platform Encryption): immunity to certification theft
    from app.game.engine_addons import has_addon as _ha28
    if _ha28(target, 28):
        return {"applied": False, "reason": "shield_platform_encryption", "target_id": target.id}
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
    """Journey Builder — +1L per ogni boss sconfitto in questa partita (max 5)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    amount = min(player.bosses_defeated, 5)
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
    """Cache Hit — Pesca 3 carte, tienine 1, rimetti le altre 2 in cima al mazzo.

    Draws up to 3 cards and returns their details for client-side selection.
    The client must follow up with a 'cache_hit_keep' action specifying which
    hand_card_id to keep; the handler puts the other 2 back on top of the deck.
    """
    from app.models.game import PlayerHandCard
    drawn_ids = []
    for _ in range(3):
        src = game.action_deck_1 if game.action_deck_1 else game.action_deck_2
        if src:
            cid = src.pop(0)
            hc = PlayerHandCard(player_id=player.id, action_card_id=cid)
            db.add(hc)
            db.flush()
            drawn_ids.append({"hand_card_id": hc.id, "action_card_id": cid})
    cs = dict(player.combat_state or {})
    cs["cache_hit_pending"] = [x["hand_card_id"] for x in drawn_ids]
    player.combat_state = cs
    return {"applied": True, "drew": len(drawn_ids), "choose_one": drawn_ids, "note": "cache_hit_keep_required"}


def _card_45(player, game, db, *, target_player_id=None) -> dict:
    """Prospect Score — +2L per ogni boss sconfitto in questa partita (max 10)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    amount = min(player.bosses_defeated * 2, 10)
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


def _card_121(player, game, db, *, target_player_id=None) -> dict:
    """Lead Score — +1L per carta in mano (max 5)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    gain = min(5, len(list(player.hand)))
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "hand_size": len(list(player.hand))}


def _card_122(player, game, db, *, target_player_id=None) -> dict:
    """Marketing Automation — Per 2 turni, ogni carta che giochi +1L aggiuntiva.

    Stores marketing_automation_turns_remaining=2 in combat_state.
    turn.py play_card: after card is played, if flag > 0, player +1L.
    turn.py end_turn: decrements marketing_automation_turns_remaining.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = dict(player.combat_state or {})
    cs["marketing_automation_turns_remaining"] = 2
    player.combat_state = cs
    return {"applied": True, "marketing_automation_turns_remaining": 2}


def _card_123(player, game, db, *, target_player_id=None) -> dict:
    """Product Catalog — +3L (o +5L se possiedi già ≥2 AddOn)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    gain = 5 if len(list(player.addons)) >= 2 else 3
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "addons_owned": len(list(player.addons))}


def _card_124(player, game, db, *, target_player_id=None) -> dict:
    """Price Book — Il prossimo AddOn costa la metà (floor, min 5 Licenze).

    Stores next_addon_price_half=True in combat_state.
    turn.py buy_addon: if flag set, halve the final cost (floor, min 5), clear flag.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = dict(player.combat_state or {})
    cs["next_addon_price_half"] = True
    player.combat_state = cs
    return {"applied": True, "next_addon_price_half": True}


def _card_125(player, game, db, *, target_player_id=None) -> dict:
    """Approval Process — Se hai già ≥10 Licenze, guadagna 4 Licenze extra."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    if player.licenze < 10:
        return {"applied": False, "reason": "need_at_least_10_licenze"}
    player.licenze += 4
    return {"applied": True, "licenze_gained": 4}


def _card_159(player, game, db, *, target_player_id=None) -> dict:
    """Service Report — +1L per boss sconfitto in questa partita (max 7)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    bosses_defeated = len(game.boss_graveyard or [])
    gain = min(7, bosses_defeated)
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "bosses_defeated": bosses_defeated}


def _card_160(player, game, db, *, target_player_id=None) -> dict:
    """Storefront Reference — +2L + 1L per ogni altro giocatore che ha acquistato un AddOn nel round corrente."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    buyers = sum(
        1 for p in game.players
        if p.id != player.id and (p.combat_state or {}).get("bought_addon_this_turn")
    )
    gain = 2 + buyers
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "addon_buyers_this_round": buyers}


def _card_161(player, game, db, *, target_player_id=None) -> dict:
    """Promotions Engine — Per 2 turni il costo degli AddOn è ridotto di 2L per il giocatore.

    Stores promotions_engine_turns_remaining=2 in combat_state.
    turn.py buy_addon: if flag > 0, subtract 2 from addon cost (min 1).
    turn.py end_turn: decrements flag, clears when 0.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = dict(player.combat_state or {})
    cs["promotions_engine_turns_remaining"] = 2
    player.combat_state = cs
    return {"applied": True, "promotions_engine_turns_remaining": 2}


def _card_162(player, game, db, *, target_player_id=None) -> dict:
    """Coupon Code — Riscatta un coupon: guadagna 3 Licenze.

    Simplified: immediate +3L (2-use mechanic not tracked at card instance level).
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.licenze += 3
    return {"applied": True, "licenze_gained": 3}


def _card_163(player, game, db, *, target_player_id=None) -> dict:
    """Inventory Availability — +2L per ogni addon che possiedi in più rispetto all'avversario con meno addon (max 8).

    Finds the opponent with the fewest addons, computes the difference with player's count,
    and awards 2L per addon advantage (capped at 8L).
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    opponents = [p for p in game.players if p.id != player.id]
    if not opponents:
        return {"applied": False, "reason": "no_opponents"}
    min_opponent_addons = min(len(list(p.addons)) for p in opponents)
    advantage = max(0, len(list(player.addons)) - min_opponent_addons)
    gain = min(advantage * 2, 8)
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "addon_advantage": advantage}


def _card_164(player, game, db, *, target_player_id=None) -> dict:
    """Revenue Dashboard — +1L per turno già trascorso (max 6)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    gain = min(6, max(0, game.turn_number - 1))
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "turns_elapsed": game.turn_number - 1}


def _card_165(player, game, db, *, target_player_id=None) -> dict:
    """Deal Insights — Guadagna Licenze pari agli HP rimasti × 2."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    gain = player.hp * 2
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain, "hp_remaining": player.hp}


def _card_166(player, game, db, *, target_player_id=None) -> dict:
    """Financial Services Cloud — +1L per ogni 10L possedute (max +3)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    gain = min(3, player.licenze // 10)
    player.licenze += gain
    return {"applied": True, "licenze_gained": gain}


def _card_167(player, game, db, *, target_player_id=None) -> dict:
    """Nonprofit Cloud — Dona 2L a un avversario; guadagni 3L e peschi 1 carta."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    from app.models.game import PlayerHandCard as _PHC167
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    donated = min(2, player.licenze)
    player.licenze -= donated
    target.licenze += donated
    player.licenze += 3
    drew = False
    if game.action_deck_1:
        db.add(_PHC167(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
        drew = True
    elif game.action_deck_2:
        db.add(_PHC167(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
        drew = True
    return {"applied": True, "licenze_donated": donated, "licenze_gained": 3, "drew_card": drew}


def _card_168(player, game, db, *, target_player_id=None) -> dict:
    """Consumer Goods Cloud — +1L per ogni giocatore in partita (incluso te)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player_count = len(list(game.players))
    player.licenze += player_count
    return {"applied": True, "licenze_gained": player_count, "player_count": player_count}


def _card_208(player, game, db, *, target_player_id=None) -> dict:
    """Smart Capture Form — +1L per ogni carta in mano adesso."""
    hand_count = len(list(player.hand))
    player.licenze += hand_count
    return {"applied": True, "licenze_gained": hand_count, "hand_count": hand_count}


def _card_209(player, game, db, *, target_player_id=None) -> dict:
    """Activity Score — Se hai giocato carte in 3 turni consecutivi senza saltare, +4L.

    Checks consecutive_turns_with_cards counter in combat_state (incremented by turn.py end_turn).
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = dict(player.combat_state or {})
    streak = cs.get("consecutive_turns_with_cards", 0)
    if streak >= 3:
        player.licenze += 4
        return {"applied": True, "streak": streak, "licenze_gained": 4}
    return {"applied": False, "reason": "streak_too_low", "streak": streak, "required": 3}


def _card_210(player, game, db, *, target_player_id=None) -> dict:
    """Activity Timeline — Recupera 1 carta tra le ultime 5 scarti e guadagna 1L."""
    from app.models.game import PlayerHandCard as _PHC210
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    discard = list(game.action_discard or [])
    if not discard:
        player.licenze += 1
        return {"applied": True, "licenze_gained": 1, "reason": "empty_discard"}
    # Take last card from discard (most recent)
    card_id = discard.pop(-1)
    game.action_discard = discard
    db.add(_PHC210(player_id=player.id, action_card_id=card_id))
    player.licenze += 1
    return {"applied": True, "recovered_card_id": card_id, "licenze_gained": 1}


def _card_211(player, game, db, *, target_player_id=None) -> dict:
    """Sales Engagement — Ogni avversario che gioca una carta contro di te questo turno ti dà 1L.

    Stores sales_engagement_active=True. turn.py play_card: if target has flag, +1L to target.
    """
    cs = dict(player.combat_state or {})
    cs["sales_engagement_active"] = True
    player.combat_state = cs
    return {"applied": True, "sales_engagement_active": True}


def _card_212(player, game, db, *, target_player_id=None) -> dict:
    """High Velocity Sales — Fuori combattimento: +3L. In combattimento: boss -2HP ma no altre azioni.

    In combat: deals 2HP to boss, sets high_velocity_all_in=True (no more cards this turn).
    """
    if player.is_in_combat:
        player.current_boss_hp = max(0, player.current_boss_hp - 2)
        cs = dict(player.combat_state or {})
        cs["high_velocity_all_in"] = True
        player.combat_state = cs
        return {"applied": True, "boss_damage": 2, "all_in": True}
    player.licenze += 3
    return {"applied": True, "licenze_gained": 3}


def _card_213(player, game, db, *, target_player_id=None) -> dict:
    """Cadence — +1L per ogni turno trascorso senza combattere in questa partita (max 6).

    Reads cadence_no_combat_turns counter (incremented in end_turn when not in combat).
    """
    counter = (player.combat_state or {}).get("cadence_no_combat_turns", 0)
    reward = min(6, counter)
    player.licenze += reward
    return {"applied": True, "licenze_gained": reward, "cadence_turns": counter}


def _card_214(player, game, db, *, target_player_id=None) -> dict:
    """Customer Lifecycle — +1L per ogni boss sconfitto in questa partita (max 5)."""
    reward = min(5, player.bosses_defeated)
    player.licenze += reward
    return {"applied": True, "licenze_gained": reward, "bosses_defeated": player.bosses_defeated}


def _card_230(player, game, db, *, target_player_id=None) -> dict:
    """Client Application — +2L; +4L se un avversario ha più AddOn di te."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    my_addons = len(list(player.addons))
    max_opponent_addons = max((len(list(p.addons)) for p in game.players if p.id != player.id), default=0)
    reward = 4 if max_opponent_addons > my_addons else 2
    player.licenze += reward
    return {"applied": True, "licenze_gained": reward, "my_addons": my_addons, "max_opp_addons": max_opponent_addons}


def _card_235(player, game, db, *, target_player_id=None) -> dict:
    """Anypoint Exchange — +2L e scambia 1 carta dalla mano con 1 dal mazzo azione."""
    from app.models.game import PlayerHandCard as _PHC235
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.licenze += 2
    # Swap: discard last card in hand and draw from deck
    hand = list(player.hand)
    swapped = False
    if hand:
        hc_swap = hand[-1]
        game.action_discard = (game.action_discard or []) + [hc_swap.action_card_id]
        db.delete(hc_swap)
        if game.action_deck_1:
            db.add(_PHC235(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            swapped = True
        elif game.action_deck_2:
            db.add(_PHC235(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
            swapped = True
    return {"applied": True, "licenze_gained": 2, "swapped": swapped}


def _card_241(player, game, db, *, target_player_id=None) -> dict:
    """Object Storage — Le tue licenze non possono essere rubate questo turno."""
    cs = dict(player.combat_state or {})
    cs["licenze_theft_immune"] = True
    player.combat_state = cs
    return {"applied": True, "licenze_theft_immune": True}


def _card_244(player, game, db, *, target_player_id=None) -> dict:
    """Prompt Template — +2L per ogni AddOn Passivo posseduto (max 5 totale)."""
    from app.models.card import AddonCard as _ADC244
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    passive_count = sum(
        1 for pa in player.addons
        if (a := db.get(_ADC244, pa.addon_id)) and a.addon_type.value == "Passivo"
    )
    reward = min(5, passive_count * 2)
    if reward == 0:
        return {"applied": False, "reason": "no_passive_addons"}
    player.licenze += reward
    return {"applied": True, "licenze_gained": reward, "passive_addons": passive_count}


def _card_251(player, game, db, *, target_player_id=None) -> dict:
    """Trailblazer Community — +1L per ogni giocatore che ha almeno 1 Certificazione."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    certified = sum(1 for p in game.players if (p.certificazioni or 0) >= 1)
    player.licenze += certified
    return {"applied": True, "licenze_gained": certified, "certified_players": certified}


def _card_252(player, game, db, *, target_player_id=None) -> dict:
    """AppExchange Partner — +2L; +5L se possiedi ≥5 AddOn."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    reward = 5 if len(list(player.addons)) >= 5 else 2
    player.licenze += reward
    return {"applied": True, "licenze_gained": reward, "addon_count": len(list(player.addons))}


def _card_253(player, game, db, *, target_player_id=None) -> dict:
    """Dreamforce Badge — +3L e pesca 1 carta extra."""
    from app.models.game import PlayerHandCard as _PHC253
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.licenze += 3
    drew = False
    if game.action_deck_1:
        db.add(_PHC253(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
        drew = True
    elif game.action_deck_2:
        db.add(_PHC253(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
        drew = True
    return {"applied": True, "licenze_gained": 3, "drew_card": drew}


def _card_254(player, game, db, *, target_player_id=None) -> dict:
    """MVP Award — +5L se hai giocato ≥2 carte di tipo diverso questo turno."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    types_played = list((player.combat_state or {}).get("card_types_played_this_turn") or [])
    if len(set(types_played)) >= 2:
        player.licenze += 5
        return {"applied": True, "licenze_gained": 5, "types_played": types_played}
    return {"applied": False, "reason": "need_2_different_types", "types_played": types_played}


def _card_255(player, game, db, *, target_player_id=None) -> dict:
    """Platinum Partner — +3L per ogni Certificazione posseduta."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    certs = player.certificazioni or 0
    reward = certs * 3
    if reward == 0:
        return {"applied": False, "reason": "no_certifications"}
    player.licenze += reward
    return {"applied": True, "licenze_gained": reward, "certifications": certs}


def _card_256(player, game, db, *, target_player_id=None) -> dict:
    """Green IT — +3L; +5L se non hai usato carte Offensive questo turno."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    types_played = list((player.combat_state or {}).get("card_types_played_this_turn") or [])
    reward = 3 if "Offensiva" in types_played else 5
    player.licenze += reward
    return {"applied": True, "licenze_gained": reward, "no_offensive": "Offensiva" not in types_played}


def _card_257(player, game, db, *, target_player_id=None) -> dict:
    """Education Cloud — Il giocatore con meno boss sconfitti pesca 1 carta (2 se sei tu)."""
    from app.models.game import PlayerHandCard as _PHC257
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    min_bosses = min(p.bosses_defeated for p in game.players)
    beneficiaries = [p for p in game.players if p.bosses_defeated == min_bosses]
    drew_self = 0
    drew_others = 0
    for bp in beneficiaries:
        n = 2 if bp.id == player.id else 1
        for _ in range(n):
            if game.action_deck_1:
                db.add(_PHC257(player_id=bp.id, action_card_id=game.action_deck_1.pop(0)))
            elif game.action_deck_2:
                db.add(_PHC257(player_id=bp.id, action_card_id=game.action_deck_2.pop(0)))
            if bp.id == player.id:
                drew_self += 1
            else:
                drew_others += 1
    return {"applied": True, "drew_self": drew_self, "drew_others": drew_others}


def _card_272(player, game, db, *, target_player_id=None) -> dict:
    """ISV Ecosystem — Il costo del prossimo addon questo turno è 5L fissi."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = player.combat_state or {}
    cs["isv_ecosystem_active"] = True
    player.combat_state = cs
    return {"applied": True, "effect": "next_addon_costs_5L"}


def _card_274(player, game, db, *, target_player_id=None) -> dict:
    """Engagement Score — +1L per addon posseduto (max 5)."""
    gained = min(5, len(list(player.addons)))
    player.licenze += gained
    return {"applied": True, "licenze_gained": gained, "addons_owned": gained}


def _card_275(player, game, db, *, target_player_id=None) -> dict:
    """Lead Conversion — Spendi 5L per ottenere +1 al prossimo tiro Elo."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    if player.licenze < 5:
        return {"applied": False, "reason": "not_enough_licenze"}
    player.licenze -= 5
    cs = player.combat_state or {}
    cs["lead_conversion_elo_bonus"] = cs.get("lead_conversion_elo_bonus", 0) + 1
    player.combat_state = cs
    return {"applied": True, "spent": 5, "elo_bonus": cs["lead_conversion_elo_bonus"]}


def _card_276(player, game, db, *, target_player_id=None) -> dict:
    """Web-to-Lead — +1L per ogni avversario fuori combattimento."""
    opponents_out = [p for p in game.players if p.id != player.id and not p.is_in_combat]
    gained = len(opponents_out)
    player.licenze += gained
    return {"applied": True, "licenze_gained": gained}


def _card_279(player, game, db, *, target_player_id=None) -> dict:
    """Salesforce Genie (Leggendaria) — Se in combattimento: +3L+2HP; altrimenti +5L."""
    if player.is_in_combat:
        player.licenze += 3
        player.hp = min(player.hp + 2, player.max_hp)
        return {"applied": True, "licenze_gained": 3, "hp_gained": 2}
    player.licenze += 5
    return {"applied": True, "licenze_gained": 5}


def _card_280(player, game, db, *, target_player_id=None) -> dict:
    """Salesforce Ohana (Leggendaria) — Tutti i giocatori +3L+1HP; tu +5L extra."""
    for p in game.players:
        p.licenze += 3
        p.hp = min(p.hp + 1, p.max_hp)
    player.licenze += 5
    return {"applied": True, "all_licenze": 3, "all_hp": 1, "self_bonus_licenze": 5}


def _card_285(player, game, db, *, target_player_id=None) -> dict:
    """Trailhead Superbadge (Leggendaria) — Traccia boss sconfitti consecutivi; al 3° +10L +1 certificazione.

    Stores superbadge_tracking=True and superbadge_defeats=0 in combat_state.
    combat.py boss_defeated hook: if superbadge_tracking, increment superbadge_defeats.
    At superbadge_defeats >= 3: player.licenze += 10, player.certificazioni += 1, clear flags.
    Counter resets to 0 if player retreats (handled in retreat logic).
    """
    cs = dict(player.combat_state or {})
    cs["superbadge_tracking"] = True
    cs.setdefault("superbadge_defeats", 0)
    player.combat_state = cs
    return {"applied": True, "superbadge_tracking": True, "superbadge_defeats": cs["superbadge_defeats"]}


def _card_286(player, game, db, *, target_player_id=None) -> dict:
    """Hyperforce Region (Leggendaria) — Tira d10: 1-3→+3L, 4-6→+5L, 7-10→+7L."""
    import random
    roll = random.randint(1, 10)
    if roll <= 3:
        gained = 3
    elif roll <= 6:
        gained = 5
    else:
        gained = 7
    player.licenze += gained
    return {"applied": True, "roll": roll, "licenze_gained": gained}


def _card_292(player, game, db, *, target_player_id=None) -> dict:
    """Admin Appreciation Day — Ruolo Admin: +5L+pesca 2; altri: +2L."""
    from app.models.game import PlayerHandCard as _PHC292
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    if getattr(player, "role", None) == "Administrator":
        player.licenze += 5
        drew = 0
        for _ in range(2):
            if game.action_deck_1:
                db.add(_PHC292(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
                drew += 1
            elif game.action_deck_2:
                db.add(_PHC292(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
                drew += 1
        return {"applied": True, "licenze_gained": 5, "drew": drew}
    player.licenze += 2
    return {"applied": True, "licenze_gained": 2}


def _card_293(player, game, db, *, target_player_id=None) -> dict:
    """Salesforce Values — +2L immediati (idealmente giocato nel turno avversario)."""
    player.licenze += 2
    return {"applied": True, "licenze_gained": 2}


def _card_294(player, game, db, *, target_player_id=None) -> dict:
    """Ohana Spirit — +2L se tutti i giocatori sono ancora vivi."""
    all_alive = all(p.hp > 0 for p in game.players)
    if all_alive:
        player.licenze += 2
        return {"applied": True, "licenze_gained": 2}
    return {"applied": True, "licenze_gained": 0, "reason": "not_all_alive"}


def _card_296(player, game, db, *, target_player_id=None) -> dict:
    """Customer Success — Al prossimo boss sconfitto, gli spettatori con questa flag +1L."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = player.combat_state or {}
    cs["customer_success_active"] = True
    player.combat_state = cs
    return {"applied": True, "effect": "watcher_bonus_on_next_boss_defeat"}


def _card_297(player, game, db, *, target_player_id=None) -> dict:
    """Trailblazer Spirit — +1L per ogni certificazione posseduta (max 5)."""
    gained = min(5, player.certificazioni)
    player.licenze += gained
    return {"applied": True, "licenze_gained": gained, "certificazioni": player.certificazioni}


def _card_298(player, game, db, *, target_player_id=None) -> dict:
    """Salesforce+ Premium — Pesca 2 carte e guadagna +2L."""
    from app.models.game import PlayerHandCard as _PHC298
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    drew = 0
    for _ in range(2):
        if game.action_deck_1:
            db.add(_PHC298(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            drew += 1
        elif game.action_deck_2:
            db.add(_PHC298(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
            drew += 1
    player.licenze += 2
    return {"applied": True, "drew": drew, "licenze_gained": 2}


ECONOMICA: dict = {
    1:   _card_1,
    2:   _card_2,
    3:   _card_3,
    4:   _card_4,
    5:   _card_5,
    6:   _card_6,
    7:   _card_7,
    8:   _card_8,
    41:  _card_41,
    42:  _card_42,
    43:  _card_43,
    44:  _card_44,
    45:  _card_45,
    46:  _card_46,
    47:  _card_47,
    48:  _card_48,
    81:  _card_81,
    82:  _card_82,
    83:  _card_83,
    84:  _card_84,
    85:  _card_85,
    86:  _card_86,
    87:  _card_87,
    88:  _card_88,
    121: _card_121,
    122: _card_122,
    123: _card_123,
    124: _card_124,
    125: _card_125,
    159: _card_159,
    160: _card_160,
    161: _card_161,
    162: _card_162,
    163: _card_163,
    164: _card_164,
    165: _card_165,
    166: _card_166,
    167: _card_167,
    168: _card_168,
    208: _card_208,
    209: _card_209,
    210: _card_210,
    211: _card_211,
    212: _card_212,
    213: _card_213,
    214: _card_214,
    230: _card_230,
    235: _card_235,
    241: _card_241,
    244: _card_244,
    251: _card_251,
    252: _card_252,
    253: _card_253,
    254: _card_254,
    255: _card_255,
    256: _card_256,
    257: _card_257,
    272: _card_272,
    274: _card_274,
    275: _card_275,
    276: _card_276,
    279: _card_279,
    280: _card_280,
    285: _card_285,
    286: _card_286,
    292: _card_292,
    293: _card_293,
    294: _card_294,
    296: _card_296,
    297: _card_297,
    298: _card_298,
}
