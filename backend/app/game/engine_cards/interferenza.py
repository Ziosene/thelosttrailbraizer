"""Carte Interferenza — giocabili durante il turno altrui (carte 38–40, 70–79, 111–120)."""
from app.models.card import BossCard
from .helpers import get_target


def _card_38(player, game, db, *, target_player_id=None) -> dict:
    """Consulting Hours — Durante il combattimento di un alleato, abbassa la soglia dado del boss di 2 per 2 round.

    Stores consulting_hours_until_round and consulting_hours_threshold_reduction in
    TARGET ally's combat_state. combat.py subtracts the reduction from effective threshold.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat:
        return {"applied": False, "reason": "target_not_in_combat"}

    cs = dict(target.combat_state or {})
    until_round = (target.combat_round or 0) + 2
    cs["consulting_hours_until_round"] = until_round
    cs["consulting_hours_threshold_reduction"] = 2
    target.combat_state = cs
    return {
        "applied": True,
        "target_player_id": target.id,
        "threshold_reduction": 2,
        "until_round": until_round,
    }


def _card_39(player, game, db, *, target_player_id=None) -> dict:
    """War Room — Durante il combattimento di un avversario, il boss recupera 1 HP (può superare il massimo).

    Intentionally no cap — the card text says "può superare il massimo originale".
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat or target.current_boss_hp is None:
        return {"applied": False, "reason": "target_not_in_combat"}

    target.current_boss_hp += 1
    return {"applied": True, "target_player_id": target.id, "boss_healed": 1}


def _card_40(player, game, db, *, target_player_id=None) -> dict:
    """Dreamforce Keynote — Tutti i giocatori guadagnano 3L (o 5L se hai 4+ cert). Pesca 1 carta.

    Legendary. Base: all players +3 Licenze; if caster has 4+ certificazioni, caster gets
    5 instead of 3 (i.e. +2 extra). Player also draws 1 card from the action deck.
    """
    from app.models.game import PlayerHandCard

    # All players +3 Licenze
    for p in game.players:
        p.licenze += 3

    # Caster bonus if 4+ cert (already got +3 above, add the extra 2)
    caster_bonus = 5 if player.certificazioni >= 4 else 3
    if caster_bonus > 3:
        player.licenze += (caster_bonus - 3)

    # Caster draws 1 card
    drawn = 0
    if game.action_deck_1:
        db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
        drawn = 1
    elif game.action_deck_2:
        db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
        drawn = 1

    return {
        "applied": True,
        "licenze_to_all": 3,
        "caster_total_licenze_gained": caster_bonus,
        "cards_drawn": drawn,
    }


def _card_70(player, game, db, *, target_player_id=None) -> dict:
    """Suppression List — Un avversario non può pescare carte nella sua prossima fase draw.

    Stores suppressed_draw=True in target's combat_state.
    turn.py _handle_draw_card: if flag set, skips the card draw and clears the flag.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["suppressed_draw"] = True
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "suppressed_draw": True}


def _card_71(player, game, db, *, target_player_id=None) -> dict:
    """Anypoint MQ — Un avversario non può giocare carte nel suo prossimo turno.

    Stores locked_out=True in target's combat_state.
    turn.py _handle_play_card: if flag set, rejects card plays and clears flag at turn end.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["locked_out"] = True
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "locked_out": True}


def _card_72(player, game, db, *, target_player_id=None) -> dict:
    """Engagement Split — Forza il prossimo tiro dado di un avversario: deve ritirarlo (secondo risultato).

    Stores forced_reroll_next=True in target's combat_state.
    combat.py _handle_roll_dice: if flag set, rolls base dice twice and takes the second result.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat:
        return {"applied": False, "reason": "target_not_in_combat"}
    cs = dict(target.combat_state or {})
    cs["forced_reroll_next"] = True
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "forced_reroll_next": True}


def _card_73(player, game, db, *, target_player_id=None) -> dict:
    """Completion Action — Copia l'effetto di una carta economica avversaria (guadagni le sue Licenze).

    Simplified: +2L immediately (average economic card gain).
    TODO: reactive implementation via event="on_opponent_played_economica".
    """
    player.licenze += 2
    return {"applied": True, "licenze_gained": 2, "note": "simplified_immediate_gain"}


def _card_74(player, game, db, *, target_player_id=None) -> dict:
    """Routing Configuration — Assegna il prossimo boss del mazzo a un avversario.

    Target must fight the assigned boss at their next turn or lose 2 Licenze.
    Stores routing_assigned=True (+ routing_assigned_boss_id) in target's combat_state.
    TODO: turn.py _handle_draw_card: enforce by checking routing_assigned flag.
    """
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


def _card_75(player, game, db, *, target_player_id=None) -> dict:
    """Triggered Send — Ruba 2L dalla ricompensa di un avversario se sconfigge il boss.

    Stores triggered_send_thief_id=player.id in target's combat_state.
    combat.py on boss_defeated: if flag set, transfer 2L from target to thief, clear flag.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat:
        return {"applied": False, "reason": "target_not_in_combat"}
    cs = dict(target.combat_state or {})
    cs["triggered_send_thief_id"] = player.id
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "triggered_send_thief_id": player.id}


def _card_76(player, game, db, *, target_player_id=None) -> dict:
    """Milestone Action — Guadagni 1L ogni round che un avversario sopravvive in combattimento (max 4).

    Stores milestone_action_remaining=4 in player's combat_state.
    combat.py _handle_roll_dice: after each non-lethal round, all watchers with this flag +1L.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = dict(player.combat_state or {})
    cs["milestone_action_remaining"] = 4
    player.combat_state = cs
    return {"applied": True, "milestone_action_remaining": 4}


def _card_77(player, game, db, *, target_player_id=None) -> dict:
    """Kafka Connector — Per 2 turni, guadagni 1L ogni volta che qualsiasi giocatore gioca una carta.

    Simplified: +3L immediately (expected value ~2 turns × 1.5 cards/turn).
    TODO: store kafka_connector_turns=2 flag; hook in turn.py play_card to award 1L per play.
    """
    player.licenze += 3
    return {"applied": True, "licenze_gained": 3, "note": "simplified_expected_value"}


def _card_78(player, game, db, *, target_player_id=None) -> dict:
    """Custom Redirect — Reindirizza una carta azione avversaria diretta a te verso un altro.

    Reaction-only card: played via play_reaction in the reaction window.
    If played normally via play_card, this handler is never reached (guard in turn.py).
    TODO: implement redirect logic in the reaction window resolution.
    """
    return {"applied": False, "reason": "reaction_only_card"}


def _card_79(player, game, db, *, target_player_id=None) -> dict:
    """SMS Studio — Un avversario perde 1 HP immediatamente."""
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    target.hp = max(0, target.hp - 1)
    return {"applied": True, "target_player_id": target.id, "target_hp_damage": 1}


def _card_111(player, game, db, *, target_player_id=None) -> dict:
    """Tracking Pixel — Monitora un avversario per 3 turni (mano e Licenze sempre visibili).

    Returns target's current hand and licenze (one-time reveal).
    Stores tracking_pixel_target_id + tracking_pixel_turns=3 for future hook.
    TODO: hook into _send_hand_state to continuously send target's info to this player.
    """
    from app.models.card import ActionCard as _AC111
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    hand_info = []
    for hc in target.hand:
        c = db.get(_AC111, hc.action_card_id)
        if c:
            hand_info.append({"id": c.id, "number": c.number, "name": c.name})
    cs = dict(player.combat_state or {})
    cs["tracking_pixel_target_id"] = target.id
    cs["tracking_pixel_turns"] = 3
    player.combat_state = cs
    return {
        "applied": True,
        "target_player_id": target.id,
        "target_licenze": target.licenze,
        "target_hand": hand_info,
        "tracking_turns": 3,
    }


def _card_112(player, game, db, *, target_player_id=None) -> dict:
    """Visitor Activity — Un avversario scarta 2 carte a caso dalla sua mano.

    Picks up to 2 random cards from target's hand and deletes them (discarded).
    """
    import random as _rnd112
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    hand = list(target.hand)
    if not hand:
        return {"applied": False, "reason": "target_hand_empty"}
    to_discard = _rnd112.sample(hand, min(2, len(hand)))
    discarded = []
    for hc in to_discard:
        discarded.append(hc.action_card_id)
        db.delete(hc)
    return {"applied": True, "target_player_id": target.id, "discarded": discarded}


def _card_113(player, game, db, *, target_player_id=None) -> dict:
    """Bounce Management — La prossima carta offensiva diretta a te rimbalza con effetto doppio sull'attaccante.

    Stores bounce_management_active=True in player's combat_state.
    turn.py play_card: if target has this flag and card is Offensiva, cancel original,
    steal 2L from attacker (approximating "double effect"), clear flag.
    """
    cs = dict(player.combat_state or {})
    cs["bounce_management_active"] = True
    player.combat_state = cs
    return {"applied": True, "bounce_management_active": True}


def _card_114(player, game, db, *, target_player_id=None) -> dict:
    """Salesforce Engage — Un avversario deve giocare 1 carta subito o scartarla.

    Simplified: auto-discards a random card from target's hand.
    TODO: give target the option to play the card instead via a reaction window.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    hand = list(target.hand)
    if not hand:
        return {"applied": True, "target_player_id": target.id, "cards_discarded": 0, "note": "target_hand_empty"}
    import random as _rnd114
    hc = _rnd114.choice(hand)
    discarded_id = hc.action_card_id
    game.action_discard = (game.action_discard or []) + [discarded_id]
    db.delete(hc)
    return {"applied": True, "target_player_id": target.id, "discarded_card_id": discarded_id}


def _card_115(player, game, db, *, target_player_id=None) -> dict:
    """HTTP Connector — "Richiedi" 1L a un avversario. Se rifiuta, perde 2L.

    Simplified: take 1L from target (they auto-comply).
    TODO: offer target a choice to comply (1L) or refuse (2L) via reaction window.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if (target.combat_state or {}).get("licenze_theft_immune"):
        return {"applied": False, "reason": "target_immune"}
    stolen = min(1, target.licenze)
    target.licenze -= stolen
    player.licenze += stolen
    return {"applied": True, "target_player_id": target.id, "licenze_transferred": stolen}


def _card_116(player, game, db, *, target_player_id=None) -> dict:
    """API Rate Limiting — Un avversario può giocare solo 1 carta nel suo prossimo turno.

    Stores api_rate_limit_max_cards=1 in target's combat_state.
    turn.py play_card: reads api_rate_limit_max_cards as upper bound for max_cards.
    turn.py end_turn: clears api_rate_limit_max_cards from combat_state.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["api_rate_limit_max_cards"] = 1
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "api_rate_limit_max_cards": 1}


def _card_117(player, game, db, *, target_player_id=None) -> dict:
    """JMS Connector — La prossima carta che un avversario gioca contro di te ha un ritardo di 1 turno.

    Simplified: blocks the next card targeting this player regardless of type (broader than web_to_case).
    Stores jms_delay_active=True in player's combat_state.
    turn.py play_card: if target has jms_delay_active, block the card effect, clear flag.
    """
    cs = dict(player.combat_state or {})
    cs["jms_delay_active"] = True
    player.combat_state = cs
    return {"applied": True, "jms_delay_active": True}


def _card_118(player, game, db, *, target_player_id=None) -> dict:
    """Spike Control — Per 2 turni, danno max da una singola fonte = 1HP o 2L.

    Stores spike_control_turns_remaining=2 in player's combat_state.
    combat.py miss branch: no change needed (miss damage is already 1HP).
    turn.py play_card: TODO cap licenze stolen at 2 when target has this flag.
    """
    cs = dict(player.combat_state or {})
    cs["spike_control_turns_remaining"] = 2
    player.combat_state = cs
    return {"applied": True, "spike_control_turns_remaining": 2}


def _card_119(player, game, db, *, target_player_id=None) -> dict:
    """Connect Channel — Per 2 turni, ogni L che un avversario guadagna tu ne guadagni 1 anche tu.

    Simplified: +2L immediately (expected value: 2 turns × 1L/turn).
    TODO: store connect_channel_target_id + turns; hook into all licenza gains.
    """
    player.licenze += 2
    return {"applied": True, "licenze_gained": 2, "note": "simplified_expected_value"}


def _card_120(player, game, db, *, target_player_id=None) -> dict:
    """Event Monitoring — Ogni carta che un avversario gioca nel suo turno ti dà 1L (max 2).

    Stores event_monitoring_target_id + event_monitoring_remaining=2 in player's combat_state.
    turn.py play_card: after each card is played, checks all players for event_monitoring on the
    current player and awards 1L (decrementing the counter).
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(player.combat_state or {})
    cs["event_monitoring_target_id"] = target.id
    cs["event_monitoring_remaining"] = 2
    player.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "event_monitoring_remaining": 2}


def _card_139(player, game, db, *, target_player_id=None) -> dict:
    """Prospect Lifecycle — Imponi un lifecycle a un avversario: non può acquistare AddOn finché non sconfigge il prossimo boss.

    Stores addons_blocked_until_boss_defeat=True in target's combat_state.
    turn.py buy_addon: if flag active on player, block purchase.
    combat.py boss defeated branch: clears addons_blocked_until_boss_defeat from combat_state.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["addons_blocked_until_boss_defeat"] = True
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "addons_blocked_until_boss_defeat": True}


def _card_140(player, game, db, *, target_player_id=None) -> dict:
    """Campaign Influence — Ogni Licenza guadagnata da qualsiasi giocatore in questo round ti dà 1L (max 3 totali).

    Stores campaign_influence_remaining=3 in player's combat_state.
    turn.py / wherever licenze are gained: after awarding L to any player, check all others for
    campaign_influence_remaining > 0 and award 1L, decrement counter.
    Simplified fallback: +3L immediately (hook provides dynamic upside).
    """
    cs = dict(player.combat_state or {})
    cs["campaign_influence_remaining"] = 3
    player.combat_state = cs
    return {"applied": True, "campaign_influence_remaining": 3}


def _card_181(player, game, db, *, target_player_id=None) -> dict:
    """Communications Cloud — Un avversario deve giocare 1 carta specifica al suo prossimo turno.

    Stores forced_card_id=<card_id> in target's combat_state.
    turn.py play_card: if forced_card_id set, require the player to play that card first.
    Simplified: forces the first card in target's hand.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    hand = list(target.hand)
    if not hand:
        return {"applied": False, "reason": "target_hand_empty"}
    forced_card_id = hand[0].action_card_id
    cs = dict(target.combat_state or {})
    cs["forced_card_id"] = forced_card_id
    target.combat_state = cs
    return {"applied": True, "target_id": target.id, "forced_card_id": forced_card_id}


def _card_182(player, game, db, *, target_player_id=None) -> dict:
    """Interaction Studio — Il prossimo boss di un avversario ha la sua abilità disabilitata.

    Stores next_boss_ability_disabled=True in target's combat_state.
    combat.py _handle_start_combat: if flag active, skip boss ability activation, clear flag.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["next_boss_ability_disabled"] = True
    target.combat_state = cs
    return {"applied": True, "target_id": target.id, "next_boss_ability_disabled": True}


def _card_183(player, game, db, *, target_player_id=None) -> dict:
    """Code Review — Blocca 1 carta dalla mano di un avversario fino al suo prossimo turno.

    Stores code_review_blocked_card_ids=[card_id] in target's combat_state.
    turn.py play_card: if card.id in list, reject with 'card_blocked_by_code_review'.
    turn.py end_turn: clears code_review_blocked_card_ids.
    Simplified: blocks the first card in target's hand.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    hand = list(target.hand)
    if not hand:
        return {"applied": False, "reason": "target_hand_empty"}
    blocked_id = hand[0].action_card_id
    cs = dict(target.combat_state or {})
    blocked = list(cs.get("code_review_blocked_card_ids") or [])
    blocked.append(blocked_id)
    cs["code_review_blocked_card_ids"] = blocked
    target.combat_state = cs
    return {"applied": True, "target_id": target.id, "blocked_card_id": blocked_id}


def _card_184(player, game, db, *, target_player_id=None) -> dict:
    """Amendment Quote — Riduce di 1 il bonus principale di un AddOn avversario per 1 turno.

    Stores amendment_quote_active=True in target's combat_state.
    turn.py use_addon: if flag active, reduce addon bonus by 1.
    turn.py end_turn: clears amendment_quote_active.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["amendment_quote_active"] = True
    target.combat_state = cs
    return {"applied": True, "target_id": target.id, "amendment_quote_active": True}


def _card_185(player, game, db, *, target_player_id=None) -> dict:
    """Record Triggered Flow — Guadagni 1L ogni volta che un avversario usa un AddOn attivo.

    Stores record_triggered_flow_watcher_id=player.id and record_triggered_flow_remaining=3
    in player's combat_state.
    turn.py use_addon (used by an opponent): checks all other players for this flag,
    awards 1L to each watcher, decrements the counter; clears when 0.
    """
    cs = dict(player.combat_state or {})
    cs["record_triggered_flow_watcher_id"] = player.id
    cs["record_triggered_flow_remaining"] = 3
    player.combat_state = cs
    return {"applied": True, "record_triggered_flow_remaining": 3}


def _card_186(player, game, db, *, target_player_id=None) -> dict:
    """Push Notification — Forza un avversario a giocare immediatamente 1 carta dalla sua mano.

    Simplified: target discards 1 card (simulates forced discard without full WS routing).
    Full implementation: WS handler routes a forced play_card event for the target.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    hand = list(target.hand)
    if not hand:
        return {"applied": False, "reason": "target_hand_empty"}
    discarded = hand[0]
    discard = list(game.action_discard or [])
    discard.append(discarded.action_card_id)
    game.action_discard = discard
    db.delete(discarded)
    return {"applied": True, "target_id": target.id, "discarded_card_id": discarded.action_card_id}


def _card_187(player, game, db, *, target_player_id=None) -> dict:
    """API Manager — Un avversario può fare solo 1 azione per turno per i prossimi 2 turni.

    Stores api_rate_limit_turns_remaining=2 and api_rate_limit_max_cards=1 in target's cs.
    turn.py play_card: if api_rate_limit_max_cards and cards_played_this_turn >= limit, reject.
    turn.py end_turn: decrements api_rate_limit_turns_remaining; clears both keys when 0.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["api_rate_limit_turns_remaining"] = 2
    cs["api_rate_limit_max_cards"] = 1
    target.combat_state = cs
    return {"applied": True, "target_id": target.id, "api_rate_limit_turns_remaining": 2}


def _card_188(player, game, db, *, target_player_id=None) -> dict:
    """Update Records — L'effetto di un AddOn avversario si riduce di 1 per 2 turni.

    Simplified: drains 1L from target each time they draw a card, for 2 turns.
    Stores update_records_licenze_drain_turns=2 in target's combat_state.
    turn.py draw_card: if flag > 0, drain 1L from that player.
    turn.py end_turn: decrements flag, clears when 0.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["update_records_licenze_drain_turns"] = 2
    target.combat_state = cs
    return {"applied": True, "target_id": target.id, "update_records_licenze_drain_turns": 2}


def _card_189(player, game, db, *, target_player_id=None) -> dict:
    """Delete Records — Elimina 1 AddOn avversario: torna nel mazzo addon.

    Removes the first addon from target's inventory and returns it to addon_deck_1.
    No purchase restriction applied.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    addons = list(target.addons)
    if not addons:
        return {"applied": False, "reason": "target_has_no_addons"}
    removed = addons[0]
    removed_addon_id = removed.addon_id
    db.delete(removed)
    deck = list(game.addon_deck_1 or [])
    deck.append(removed_addon_id)
    game.addon_deck_1 = deck
    return {"applied": True, "target_id": target.id, "removed_addon_id": removed_addon_id}


def _card_190(player, game, db, *, target_player_id=None) -> dict:
    """Unification Rule — Ruba 1 addon a un avversario (passa nel tuo inventario).

    Moves the first addon from target's inventory to player's inventory.
    """
    from app.models.game import PlayerAddon as _PA190
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    addons = list(target.addons)
    if not addons:
        return {"applied": False, "reason": "target_has_no_addons"}
    stolen = addons[0]
    stolen_addon_id = stolen.addon_id
    db.delete(stolen)
    db.add(_PA190(player_id=player.id, addon_id=stolen_addon_id))
    return {"applied": True, "target_id": target.id, "stolen_addon_id": stolen_addon_id}


def _card_222(player, game, db, *, target_player_id=None) -> dict:
    """Block Kit — Riduce l'effetto della prossima carta di un avversario di 1 punto.

    Stores block_kit_pending=True in target's combat_state.
    turn.py play_card: if target has block_kit_pending, -1L or -1HP to that card's effect.
    """
    if not target_player_id:
        return {"applied": False, "reason": "target_required"}
    from app.game.engine_cards.helpers import get_target
    target = get_target(game, target_player_id)
    if not target:
        return {"applied": False, "reason": "target_not_found"}
    cs = dict(target.combat_state or {})
    cs["block_kit_pending"] = True
    target.combat_state = cs
    return {"applied": True, "target_id": target.id, "block_kit_pending": True}


def _card_224(player, game, db, *, target_player_id=None) -> dict:
    """Canvas — Boss -2HP; soglia dado -2 per il resto del combattimento."""
    if not player.is_in_combat:
        return {"applied": False, "reason": "not_in_combat"}
    player.current_boss_hp = max(0, (player.current_boss_hp or 0) - 2)
    cs = dict(player.combat_state or {})
    cs["boss_threshold_reduction"] = cs.get("boss_threshold_reduction", 0) + 2
    player.combat_state = cs
    return {"applied": True, "boss_hp_lost": 2, "boss_threshold_reduction": cs["boss_threshold_reduction"]}


def _card_225(player, game, db, *, target_player_id=None) -> dict:
    """Huddle — Tutti i giocatori devono mostrare la propria mano per 1 turno.

    Sets hand_revealed_this_turn=True for ALL players.
    Client/broadcast uses this flag to show hands.
    """
    for gp in game.players:
        cs = dict(gp.combat_state or {})
        cs["hand_revealed_this_turn"] = True
        gp.combat_state = cs
    return {"applied": True, "players_revealed": len(list(game.players))}


def _card_229(player, game, db, *, target_player_id=None) -> dict:
    """SLA Tier — Degrada livello di servizio: target perde il bonus di 1 addon per questo turno.

    Taps the most recently acquired untapped addon of target.
    """
    if not target_player_id:
        return {"applied": False, "reason": "target_required"}
    from app.game.engine_cards.helpers import get_target
    target = get_target(game, target_player_id)
    if not target:
        return {"applied": False, "reason": "target_not_found"}
    untapped = [pa for pa in target.addons if not pa.is_tapped]
    if not untapped:
        return {"applied": False, "reason": "no_untapped_addons"}
    # Tap the most recently acquired (last in list)
    untapped[-1].is_tapped = True
    return {"applied": True, "target_id": target.id, "tapped_addon_id": untapped[-1].addon_id}


def _card_236(player, game, db, *, target_player_id=None) -> dict:
    """API Governance — L'avversario con più Licenze perde 3L."""
    opponents = [p for p in game.players if p.id != player.id]
    if not opponents:
        return {"applied": False, "reason": "no_opponents"}
    richest = max(opponents, key=lambda p: p.licenze)
    lost = min(3, richest.licenze)
    richest.licenze -= lost
    return {"applied": True, "target_id": richest.id, "licenze_lost": lost}


def _card_237(player, game, db, *, target_player_id=None) -> dict:
    """Dataflow — Forza un avversario a darti 1 carta dalla sua mano."""
    if not target_player_id:
        return {"applied": False, "reason": "target_required"}
    from app.game.engine_cards.helpers import get_target
    from app.models.game import PlayerHandCard as _PHC237
    target = get_target(game, target_player_id)
    if not target:
        return {"applied": False, "reason": "target_not_found"}
    hand = list(target.hand)
    if not hand:
        return {"applied": False, "reason": "target_has_no_cards"}
    stolen = hand[-1]
    stolen_card_id = stolen.action_card_id
    db.delete(stolen)
    db.add(_PHC237(player_id=player.id, action_card_id=stolen_card_id))
    return {"applied": True, "stolen_card_id": stolen_card_id}


def _card_246(player, game, db, *, target_player_id=None) -> dict:
    """Agent Topic — Per 1 turno solo il tipo dichiarato può essere giocato da chiunque.

    Like Unification Rule (190) but defaults to 'Economica' as the mandated type.
    Stores unification_rule_active + unification_rule_card_type for all players.
    Cleared in end_turn.
    """
    for gp in game.players:
        cs = dict(gp.combat_state or {})
        cs["unification_rule_active"] = True
        cs["unification_rule_card_type"] = "Economica"
        gp.combat_state = cs
    return {"applied": True, "unification_rule_card_type": "Economica", "players_affected": len(list(game.players))}


def _card_268(player, game, db, *, target_player_id=None) -> dict:
    """ISV Summit — Ogni avversario senza addon -2L; ogni avversario con addon ti dà +1L."""
    gained = 0
    penalized = 0
    for gp in game.players:
        if gp.id == player.id:
            continue
        if list(gp.addons):
            gained += 1
        else:
            gp.licenze = max(0, gp.licenze - 2)
            penalized += 1
    player.licenze += gained
    return {"applied": True, "licenze_gained": gained, "penalized_players": penalized}


def _card_271(player, game, db, *, target_player_id=None) -> dict:
    """Ohana Pledge — Tutti gli avversari entrano in tregua Ohana per 2 turni (nessuna Offensiva verso il caster)."""
    truce_until = game.turn_number + 2
    for gp in game.players:
        if gp.id == player.id:
            continue
        cs = dict(gp.combat_state or {})
        cs["ohana_truce_caster_id"] = player.id
        cs["ohana_truce_until_turn"] = truce_until
        gp.combat_state = cs
    return {"applied": True, "truce_until_turn": truce_until, "players_affected": len(list(game.players)) - 1}


def _card_277(player, game, db, *, target_player_id=None) -> dict:
    """Form Handler — Prende l'ultima carta dalla mano di ogni giocatore, le mescola e ridistribuisce casualmente."""
    import random
    from app.models.game import PlayerHandCard as _PHC277
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    pool = []
    for gp in game.players:
        hand = list(gp.hand)
        if hand:
            taken = hand[-1]
            pool.append(taken.action_card_id)
            db.delete(taken)
    if not pool:
        return {"applied": True, "redistributed": 0}
    random.shuffle(pool)
    players_list = list(game.players)
    for i, card_id in enumerate(pool):
        recipient = players_list[i % len(players_list)]
        db.add(_PHC277(player_id=recipient.id, action_card_id=card_id))
    return {"applied": True, "redistributed": len(pool)}


def _card_278(player, game, db, *, target_player_id=None) -> dict:
    """Marc Benioff Mode (Leggendaria) — Azzera le licenze di tutti gli avversari; tu guadagni la metà."""
    total_stolen = 0
    for gp in game.players:
        if gp.id == player.id:
            continue
        total_stolen += gp.licenze
        gp.licenze = 0
    player.licenze += total_stolen // 2
    return {"applied": True, "total_stolen": total_stolen, "licenze_gained": total_stolen // 2}


def _card_98(player, game, db, *, target_player_id=None) -> dict:
    """Pause Element — Un avversario in combattimento salta 1 round (né lui né il boss perdono HP).

    Stores pause_element_rounds_remaining=1 in target's combat_state.
    combat.py: if flag > 0 on that player, nullifies the round (no roll processed), decrements flag.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    if not target.is_in_combat:
        return {"applied": False, "reason": "target_not_in_combat"}
    cs = dict(target.combat_state or {})
    cs["pause_element_rounds_remaining"] = cs.get("pause_element_rounds_remaining", 0) + 1
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id,
            "pause_element_rounds_remaining": cs["pause_element_rounds_remaining"]}


INTERFERENZA: dict = {
    38:  _card_38,
    39:  _card_39,
    40:  _card_40,
    70:  _card_70,
    71:  _card_71,
    72:  _card_72,
    73:  _card_73,
    74:  _card_74,
    75:  _card_75,
    76:  _card_76,
    77:  _card_77,
    78:  _card_78,
    79:  _card_79,
    98:  _card_98,
    111: _card_111,
    112: _card_112,
    113: _card_113,
    114: _card_114,
    115: _card_115,
    116: _card_116,
    117: _card_117,
    118: _card_118,
    119: _card_119,
    120: _card_120,
    139: _card_139,
    140: _card_140,
    181: _card_181,
    182: _card_182,
    183: _card_183,
    184: _card_184,
    185: _card_185,
    186: _card_186,
    187: _card_187,
    188: _card_188,
    189: _card_189,
    190: _card_190,
    222: _card_222,
    224: _card_224,
    225: _card_225,
    229: _card_229,
    236: _card_236,
    237: _card_237,
    246: _card_246,
    268: _card_268,
    271: _card_271,
    277: _card_277,
    278: _card_278,
}
