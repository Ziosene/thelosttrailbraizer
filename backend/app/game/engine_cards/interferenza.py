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
    """Anypoint MQ — Metti 1 carta dalla tua mano nella coda di un avversario (la pesca per prima).

    Takes a random card from player's hand, queues it for target's next draw.
    Stores forced_queue_card_id=N in target's combat_state.
    turn.py _handle_draw_card: if flag set, gives that card first (instead of deck draw), clears flag.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    hand = list(player.hand)
    if not hand:
        return {"applied": False, "reason": "no_cards_in_hand"}
    import random as _rnd
    hc = _rnd.choice(hand)
    queued_card_id = hc.action_card_id
    db.delete(hc)
    cs = dict(target.combat_state or {})
    cs["forced_queue_card_id"] = queued_card_id
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "queued_card_id": queued_card_id}


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
    """Triggered Send — Ruba 2L dalla ricompensa boss di un avversario (prima che combatta).

    Simplified: steal 2L from target directly.
    TODO: reactive trigger via event="on_opponent_drew_boss".
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    stolen = min(2, target.licenze)
    target.licenze -= stolen
    player.licenze += stolen
    return {"applied": True, "target_player_id": target.id, "licenze_stolen": stolen}


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
    """Visitor Activity — Per 1 turno, un avversario deve dichiarare ogni carta prima di giocarla.

    Stores visitor_activity_turns=1 in target's combat_state (client-side enforcement signal).
    turn.py draw_card: decrements visitor_activity_turns at start of affected turn.
    """
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    cs = dict(target.combat_state or {})
    cs["visitor_activity_turns"] = 1
    target.combat_state = cs
    return {"applied": True, "target_player_id": target.id, "visitor_activity_turns": 1}


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
    """Delete Records — Elimina 1 AddOn avversario; lui non può riacquistarlo per 3 turni.

    Removes the first addon from target's inventory, returns it to addon_deck_1.
    Stores deleted_addon_blocked_ids=[addon_id] and deleted_addon_block_turns_remaining=3
    in target's combat_state.
    turn.py buy_addon: if addon_id in deleted_addon_blocked_ids, reject purchase.
    turn.py end_turn: decrements deleted_addon_block_turns_remaining; clears both when 0.
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
    cs = dict(target.combat_state or {})
    blocked = list(cs.get("deleted_addon_blocked_ids") or [])
    blocked.append(removed_addon_id)
    cs["deleted_addon_blocked_ids"] = blocked
    cs["deleted_addon_block_turns_remaining"] = 3
    target.combat_state = cs
    return {"applied": True, "target_id": target.id, "removed_addon_id": removed_addon_id}


def _card_190(player, game, db, *, target_player_id=None) -> dict:
    """Unification Rule — Per 1 turno, tutti i giocatori possono usare solo 1 tipo di carta.

    Broadcasts unification_rule_active=True and unification_rule_card_type=<type> to all players.
    turn.py play_card: if rule active for the playing player, reject cards of wrong type.
    turn.py end_turn: clears both flags for the current-turn player.
    Default enforced type: 'Offensiva' (client should specify via a future param).
    """
    for gp in game.players:
        cs = dict(gp.combat_state or {})
        cs["unification_rule_active"] = True
        cs["unification_rule_card_type"] = "Offensiva"
        gp.combat_state = cs
    return {"applied": True, "unification_rule_card_type": "Offensiva", "affected_players": len(list(game.players))}


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
}
