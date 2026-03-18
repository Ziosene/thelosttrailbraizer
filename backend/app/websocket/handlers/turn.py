"""
Turn phase handlers: draw card, play card, buy addon, use addon, end turn.
"""
import random
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state, _send_hand_state,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.models.card import ActionCard, BossCard, AddonCard
from app.game import engine
from app.game.engine_cards import apply_action_card_effect
from app.websocket.reaction_manager import open_reaction_window


async def _handle_draw_card(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Game not in progress")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if game.current_phase != TurnPhase.draw:
        await _error(game.code, user_id, "Not in draw phase")
        return

    # ── FASE INIZIALE step 1: Untap all addons (moved from end_turn) ─────────
    for pa in player.addons:
        pa.is_tapped = False

    # ── FASE INIZIALE step 2: on-start abilities ──────────────────────────────
    # TODO: trigger_passive_addons(event="on_turn_start", player, game, db)

    # ── FASE INIZIALE step 3: process cross-turn combat_state flags ───────────
    _cs_init = dict(player.combat_state or {})
    # Card 44 (Object Store): auto-return stored licenze at start of new turn
    _stored_lic = _cs_init.pop("object_store_licenze", 0)
    if _stored_lic:
        player.licenze += _stored_lic
    # Card 43 (Drip Program): deliver next licenza installment
    _drip = _cs_init.get("drip_program_remaining", 0)
    if _drip > 0:
        player.licenze += 1
        if _drip <= 1:
            _cs_init.pop("drip_program_remaining", None)
        else:
            _cs_init["drip_program_remaining"] = _drip - 1
    # Card 42 (Engagement Studio): clear fought_this_turn so it's fresh for this new turn
    _cs_init.pop("fought_this_turn", None)
    # Card 70 (Suppression List): skip draw this turn if suppressed
    _suppressed = _cs_init.pop("suppressed_draw", False)
    # Card 71 (Anypoint MQ): deliver forced queued card before normal draw
    _forced_queue_id = _cs_init.pop("forced_queue_card_id", None)
    player.combat_state = _cs_init or {}

    if _forced_queue_id:
        from app.models.game import PlayerHandCard as _PHCQ
        db.add(_PHCQ(player_id=player.id, action_card_id=_forced_queue_id))

    if _suppressed:
        game.current_phase = TurnPhase.action
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": ServerEvent.CARD_DRAWN,
            "player_id": player.id,
            "suppressed": True,
        })
        await _broadcast_state(game, db)
        await _send_hand_state(game.code, player, db)
        return

    if len(player.hand) >= engine.MAX_HAND_SIZE:
        await _error(game.code, user_id, "Hand is full")
        return

    deck_num = data.get("deck", 1)  # client sends 1 or 2
    if deck_num not in (1, 2):
        await _error(game.code, user_id, "Invalid deck number (must be 1 or 2)")
        return

    # Try to draw from the requested deck; if empty, reshuffle shared discard into both decks
    if deck_num == 1:
        if not game.action_deck_1 and game.action_discard:
            new_deck = engine.shuffle_deck(game.action_discard)
            game.action_deck_1, game.action_deck_2 = engine.split_deck(new_deck)
            game.action_discard = []
        drawn = [game.action_deck_1.pop(0)] if game.action_deck_1 else []
    else:
        if not game.action_deck_2 and game.action_discard:
            new_deck = engine.shuffle_deck(game.action_discard)
            game.action_deck_1, game.action_deck_2 = engine.split_deck(new_deck)
            game.action_discard = []
        drawn = [game.action_deck_2.pop(0)] if game.action_deck_2 else []
    if not drawn:
        await _error(game.code, user_id, f"No cards left in deck {deck_num}")
        return

    from app.models.game import PlayerHandCard

    # Boss 81 (Trailhead Jinx): drawn cards may be jinxed — d10 ≤ 3 → card discarded, no effect
    jinxed = False
    if player.is_in_combat and player.current_boss_id and engine.boss_jinx_on_draw(player.current_boss_id):
        if engine.roll_d10() <= 3:
            jinxed = True
            game.action_discard = (game.action_discard or []) + [drawn[0]]

    if not jinxed:
        db.add(PlayerHandCard(player_id=player.id, action_card_id=drawn[0]))

    # Card 138 (Pardot Form Handler): when ANY player draws, other players watching earn a mirror draw (max 2)
    from app.models.game import PlayerHandCard as _PHC138
    for _watcher in game.players:
        if _watcher.id != player.id and not _watcher.is_in_combat:
            _pf = (_watcher.combat_state or {}).get("pardot_form_handler_remaining", 0)
            if _pf > 0 and len(list(_watcher.hand)) < engine.MAX_HAND_SIZE:
                _pf_src = game.action_deck_1 if game.action_deck_1 else game.action_deck_2
                if _pf_src:
                    db.add(_PHC138(player_id=_watcher.id, action_card_id=_pf_src.pop(0)))
            if _pf > 0:
                _wc = dict(_watcher.combat_state)
                _wc["pardot_form_handler_remaining"] = _pf - 1
                if _wc["pardot_form_handler_remaining"] <= 0:
                    _wc.pop("pardot_form_handler_remaining", None)
                _watcher.combat_state = _wc

    # Card 188 (Update Records): drain 1L on each draw while flag active
    _ur_drain = (player.combat_state or {}).get("update_records_licenze_drain_turns", 0)
    if _ur_drain > 0:
        player.licenze = max(0, player.licenze - 1)

    # Card 178 (VM Queue): deliver next queued card to hand at draw time
    _vm_queue = list((player.combat_state or {}).get("vm_queue_card_ids") or [])
    if _vm_queue:
        _vm_card_id = _vm_queue.pop(0)
        from app.models.game import PlayerHandCard as _PHCVM
        if len(list(player.hand)) < engine.MAX_HAND_SIZE:
            db.add(_PHCVM(player_id=player.id, action_card_id=_vm_card_id))
        _cs_vm = dict(player.combat_state)
        if _vm_queue:
            _cs_vm["vm_queue_card_ids"] = _vm_queue
        else:
            _cs_vm.pop("vm_queue_card_ids", None)
        player.combat_state = _cs_vm

    # Boss 92 (Einstein Copilot Seraph): every card drawn during combat costs 1 HP
    if player.is_in_combat and player.current_boss_id:
        hp_cost = engine.boss_draw_costs_hp(player.current_boss_id)
        if hp_cost > 0:
            player.hp = max(0, player.hp - hp_cost)

    # TODO: trigger_passive_addons(event="on_draw", player, game, db)

    game.current_phase = TurnPhase.action
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {"type": ServerEvent.CARD_DRAWN, "player_id": player.id})
    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)


async def _handle_play_card(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase not in (TurnPhase.action, TurnPhase.combat):
        await _error(game.code, user_id, "Cannot play card now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    max_cards = (
        engine.boss_max_cards_per_turn(player.current_boss_id, engine.MAX_CARDS_PER_TURN)
        if player.is_in_combat and player.current_boss_id
        else engine.MAX_CARDS_PER_TURN
    )
    # Card 116 (API Rate Limiting): opponent imposed a lower card-play limit for this turn
    _api_limit = (player.combat_state or {}).get("api_rate_limit_max_cards")
    if _api_limit is not None:
        max_cards = min(max_cards, _api_limit)
    # Card 226 (Shortcut): bonus card plays this turn (skip draw = extra slots)
    max_cards += (player.combat_state or {}).get("shortcut_extra_plays", 0)
    # Card 201 (Web Studio): +1 card slot this turn
    if (player.combat_state or {}).get("web_studio_extra_card"):
        max_cards += 1
    # Card 269 (Trailhead GO): set max to 4 if higher than current limit
    _tg_max = (player.combat_state or {}).get("trailhead_go_max_cards")
    if _tg_max is not None:
        max_cards = max(max_cards, _tg_max)
    # Card 283 (Queueable Job): set max to 5 if higher than current limit
    _qj_max = (player.combat_state or {}).get("queueable_job_max_cards")
    if _qj_max is not None:
        max_cards = max(max_cards, _qj_max)
    if player.cards_played_this_turn >= max_cards:
        await _error(game.code, user_id, "Card limit reached this turn")
        return

    # TODO: validare il timing della carta prima di giocarla.
    # Ogni carta ha un campo "Quando" (es. "Durante combattimento", "Fuori dal combattimento",
    # "In qualsiasi momento", "Automatica"). Attualmente non viene verificato.
    # Va implementata una funzione can_play_card(card, game) che confronta
    # card.timing con game.current_phase e player.is_in_combat.

    if player.is_in_combat and player.current_boss_id:
        current_round_pc = (player.combat_round or 0) + 1

        # Boss  9 (Code Coverage Ghoul): offensive cards blocked
        # TODO: enforce once card.card_type is used in apply_action_card_effect
        # Boss 17 (Validation Rule Hell): dice-modifier cards have no effect
        # TODO: pass flag into apply_action_card_effect
        # Boss  8 (MuleSoft Kraken): interference doubled in card effect logic — TODO

        # Boss 38 (Einstein Bot Imposter): on even rounds, first card played is cancelled
        if engine.boss_cancels_next_card(player.current_boss_id, current_round_pc):
            if player.cards_played_this_turn == 0:
                # Card consumed but has no effect this round
                hand_card_id_early = data.get("hand_card_id")
                from app.models.game import PlayerHandCard as _PHC
                hc_early = db.get(_PHC, hand_card_id_early)
                if hc_early and hc_early.player_id == player.id:
                    card_early = db.get(ActionCard, hc_early.action_card_id)
                    game.action_discard.append(hc_early.action_card_id)
                    db.delete(hc_early)
                    player.cards_played_this_turn += 1
                    db.commit()
                    db.refresh(game)
                    await manager.broadcast(game.code, {
                        "type": ServerEvent.CARD_PLAYED,
                        "player_id": player.id,
                        "card": {"id": card_early.id, "name": card_early.name} if card_early else {},
                        "cancelled_by_boss": True,
                    })
                    await _broadcast_state(game, db)
                    await _send_hand_state(game.code, player, db)
                    return

        # Boss 41 (Quip Wisp): reveal the card to all, then offer opponents (in turn order)
        # the chance to pay 1L to cancel it. First to accept blocks the card (discarded).
        if engine.boss_opponents_can_block_card(player.current_boss_id):
            hand_card_id_peek = data.get("hand_card_id")
            from app.models.game import PlayerHandCard as _PHC2
            hc_peek = db.get(_PHC2, hand_card_id_peek)
            if hc_peek:
                card_peek = db.get(ActionCard, hc_peek.action_card_id)
                card_info = {"id": card_peek.id, "name": card_peek.name} if card_peek else {}
                # Notify everyone (including combatant) that the card has been revealed
                await manager.broadcast(game.code, {
                    "type": "card_declared",
                    "player_id": player.id,
                    "card": card_info,
                    "blockable": True,
                    "cost": 1,
                })
                # Offer block in turn order starting from the player after the combatant
                turn_order = game.turn_order or []
                combatant_pos = turn_order.index(player.id) if player.id in turn_order else -1
                ordered_ids = (
                    turn_order[combatant_pos + 1:] + turn_order[:combatant_pos]
                    if combatant_pos >= 0 else turn_order
                )
                _quip_blocked = False
                for opp_pid in ordered_ids:
                    opp = next((p for p in game.players if p.id == opp_pid and p.id != player.id), None)
                    if not opp or opp.licenze < 1:
                        continue
                    await manager.send_to_player(game.code, opp.user_id, {
                        "type": "quip_block_window_open",
                        "card": card_info,
                        "cost": 1,
                        "timeout_ms": 5000,
                    })
                    block_response = await open_reaction_window(game.code, opp.id, timeout=5.0)
                    await manager.send_to_player(game.code, opp.user_id, {
                        "type": "quip_block_window_closed",
                    })
                    if block_response and block_response.get("action") == "block":
                        opp.licenze -= 1
                        _quip_blocked = True
                        await manager.broadcast(game.code, {
                            "type": "card_blocked",
                            "reason": "quip_wisp",
                            "blocker_player_id": opp.id,
                            "card": card_info,
                        })
                        break
                if _quip_blocked:
                    card_approved = False

        # Boss 65 (Einstein Vision Stalker): reveals card and cancels it if offensive
        if engine.boss_cancels_offensive_if_revealed(player.current_boss_id):
            hand_card_id_reveal = data.get("hand_card_id")
            from app.models.game import PlayerHandCard as _PHC3
            hc_reveal = db.get(_PHC3, hand_card_id_reveal)
            if hc_reveal:
                card_reveal = db.get(ActionCard, hc_reveal.action_card_id)
                if card_reveal and card_reveal.card_type == "Offensiva":
                    game.action_discard.append(hc_reveal.action_card_id)
                    db.delete(hc_reveal)
                    player.cards_played_this_turn += 1
                    db.commit()
                    db.refresh(game)
                    await manager.broadcast(game.code, {
                        "type": ServerEvent.CARD_PLAYED,
                        "player_id": player.id,
                        "card": {"id": card_reveal.id, "name": card_reveal.name} if card_reveal else {},
                        "cancelled_by_boss": True,
                    })
                    await _broadcast_state(game, db)
                    await _send_hand_state(game.code, player, db)
                    return

    hand_card_id = data.get("hand_card_id")
    from app.models.game import PlayerHandCard
    hc = db.get(PlayerHandCard, hand_card_id)
    if not hc or hc.player_id != player.id:
        await _error(game.code, user_id, "Card not in hand")
        return

    card = db.get(ActionCard, hc.action_card_id)

    # Card 183 (Code Review): blocked cards cannot be played until next turn
    if card and card.id in list((player.combat_state or {}).get("code_review_blocked_card_ids") or []):
        await _error(game.code, user_id, "card_blocked_by_code_review")
        return

    # Card 190 (Unification Rule): only cards of the mandated type may be played
    _unification_type = (player.combat_state or {}).get("unification_rule_card_type")
    if _unification_type and (player.combat_state or {}).get("unification_rule_active"):
        if card and card.card_type != _unification_type:
            await _error(game.code, user_id, f"unification_rule: only {_unification_type} cards allowed this turn")
            return

    # Card 212 (High Velocity Sales): if all_in flag set, no more cards may be played this turn
    if (player.combat_state or {}).get("high_velocity_all_in"):
        await _error(game.code, user_id, "high_velocity_all_in: no more cards this turn")
        return

    # Boss 64 (Order Management Maelstrom): escalating licenze cost per card played this combat
    if player.is_in_combat and player.current_boss_id and engine.boss_card_play_escalating_cost(player.current_boss_id):
        _cs_ms = player.combat_state or {}
        _maelstrom_extra = _cs_ms.get("maelstrom_cards_played_combat", 0) + 1
        if player.licenze < _maelstrom_extra:
            await _error(game.code, user_id, f"maelstrom: need {_maelstrom_extra}L extra to play this card (have {player.licenze}L)")
            return
        player.licenze -= _maelstrom_extra
        cs_ms = dict(_cs_ms)
        cs_ms["maelstrom_cards_played_combat"] = cs_ms.get("maelstrom_cards_played_combat", 0) + 1
        player.combat_state = cs_ms

    # Card 27 (Lucky Roll): reaction-only — must be played via the post-roll reaction window,
    # not via play_card. Guard here prevents the card from being consumed without effect.
    if card and card.number == 27:
        await _error(game.code, user_id, "Lucky Roll is a reaction card: wait for the post-roll window to use it")
        return

    # Card 78 (Custom Redirect): reaction-only — played via play_reaction when targeted by an opponent.
    if card and card.number == 78:
        await _error(game.code, user_id, "Custom Redirect is a reaction card: play it when targeted by an opponent")
        return

    # Boss 82 (Customer 360 Gorgon): petrified cards cannot be played this fight
    if player.is_in_combat and player.combat_state:
        petrified = player.combat_state.get("petrified_card_ids", [])
        if card and card.id in petrified:
            await _error(game.code, user_id, "This card is petrified and cannot be played")
            return

    # Boss 86 (Record Type Ravager): only declared card type may be played
    if player.is_in_combat and player.combat_state:
        allowed_type = player.combat_state.get("allowed_card_type")
        if allowed_type and card and card.card_type != allowed_type:
            await _error(game.code, user_id, f"Boss restricts you to {allowed_type} cards only")
            return

    game.action_discard.append(hc.action_card_id)
    db.delete(hc)
    # Card 243 (Einstein GPT): next card plays for free (no slot consumed)
    _egpt_free = (player.combat_state or {}).get("einstein_gpt_free_play")
    if _egpt_free:
        _cs_egpt = dict(player.combat_state)
        _cs_egpt.pop("einstein_gpt_free_play", None)
        player.combat_state = _cs_egpt
    else:
        player.cards_played_this_turn += 1
    card_approved = True  # may be set to False by boss 69 below

    if player.is_in_combat and player.current_boss_id and card:
        current_round_post = (player.combat_round or 0) + 1

        # Boss 69 (Approval Process Bureaucrat): every card must pass an approval roll
        # d10 ≤ 4 → card consumed but has no effect
        if engine.boss_requires_approval_roll(player.current_boss_id):
            approval_roll = engine.roll_d10()
            if approval_roll <= 4:
                card_approved = False

        # Boss 59 (Trailblazer Community Mob): boss heals when opponent plays an interference card
        # Interference cards played by NON-combatant players against this player also heal the boss
        if card.card_type == "Interferenza":
            boss_heal_interference = engine.boss_heals_on_interference(player.current_boss_id)
            if boss_heal_interference > 0:
                boss_card_hi = db.get(BossCard, player.current_boss_id)
                if boss_card_hi:
                    player.current_boss_hp = min(boss_card_hi.hp, (player.current_boss_hp or 0) + boss_heal_interference)

        # Boss 72 (DevOps Center Saboteur): boss heals when combatant plays a defensive card
        if card.card_type == "Difensiva":
            boss_heal_def = engine.boss_heals_on_defensive_card(player.current_boss_id)
            if boss_heal_def > 0:
                boss_card_hd = db.get(BossCard, player.current_boss_id)
                if boss_card_hd:
                    player.current_boss_hp = min(boss_card_hd.hp, (player.current_boss_hp or 0) + boss_heal_def)

        # Boss 96 (Compliance Cloud Sentinel): 1 extra HP per card played beyond the first this turn
        compliance_penalty = engine.boss_compliance_penalty_per_extra_card(player.current_boss_id)
        if compliance_penalty > 0 and player.cards_played_this_turn > 1:
            extra_compliance_dmg = compliance_penalty  # 1 HP per extra card (not cumulative — fires each play)
            player.hp = max(0, player.hp - extra_compliance_dmg)

    # ── Reaction window ───────────────────────────────────────────────────────
    # Se la carta colpisce un avversario specifico e quell'avversario ha ancora
    # budget carte (cards_played_this_turn < MAX_CARDS_PER_TURN), gli apriamo
    # una finestra di reazione PRIMA di applicare l'effetto originale.
    target_player_id = data.get("target_player_id")

    # Card 287 (404 Not Found): block outgoing card targeting while active
    if (player.combat_state or {}).get("not_found_active") and target_player_id:
        if (player.combat_state or {}).get("not_found_until_turn", 0) >= game.turn_number:
            await _error(game.code, user_id, "404 Not Found: you cannot target other players this turn")
            return

    # Check target-side protections for Offensiva cards
    if card and card_approved and target_player_id and card.card_type == "Offensiva":
        _tgt_check = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        if _tgt_check:
            # Card 287 (404 Not Found): block incoming targeting
            if (_tgt_check.combat_state or {}).get("not_found_active") and \
                    (_tgt_check.combat_state or {}).get("not_found_until_turn", 0) >= game.turn_number:
                card_approved = False
                await manager.broadcast(game.code, {
                    "type": "card_blocked",
                    "reason": "404_not_found",
                    "target_player_id": _tgt_check.id,
                })
            # Card 271 (Ohana Pledge): block Offensiva toward the caster
            _truce_caster = (_tgt_check.combat_state or {}).get("ohana_truce_caster_id")
            _truce_until = (_tgt_check.combat_state or {}).get("ohana_truce_until_turn", 0)
            if _truce_caster == player.id and _truce_until >= game.turn_number:
                card_approved = False
                await manager.broadcast(game.code, {
                    "type": "card_blocked",
                    "reason": "ohana_truce",
                    "target_player_id": _tgt_check.id,
                })
            # Card 295 (Trust First): cancel first ever Offensiva targeting this player
            if card_approved and (_tgt_check.combat_state or {}).get("trust_first_active"):
                card_approved = False
                _cs_tf = dict(_tgt_check.combat_state)
                _cs_tf.pop("trust_first_active", None)
                _tgt_check.combat_state = _cs_tf
                await manager.broadcast(game.code, {
                    "type": "card_blocked",
                    "reason": "trust_first",
                    "target_player_id": _tgt_check.id,
                })

    reaction_target = None
    reaction_response = None

    # Card 283 (Queueable Job): skip reaction window while plays_remaining > 0
    _skip_reaction = (player.combat_state or {}).get("queueable_job_plays_remaining", 0) > 0
    if _skip_reaction:
        _cs_qj = dict(player.combat_state)
        _cs_qj["queueable_job_plays_remaining"] = max(0, _cs_qj["queueable_job_plays_remaining"] - 1)
        if _cs_qj["queueable_job_plays_remaining"] == 0:
            _cs_qj.pop("queueable_job_plays_remaining", None)
        player.combat_state = _cs_qj

    if card and card_approved and target_player_id and not _skip_reaction:
        reaction_target = next(
            (p for p in game.players if p.id == target_player_id and p.id != player.id),
            None,
        )
        if reaction_target and reaction_target.cards_played_this_turn < engine.MAX_CARDS_PER_TURN:
            await manager.send_to_player(game.code, reaction_target.user_id, {
                "type": ServerEvent.REACTION_WINDOW_OPEN,
                "trigger_card": {"id": card.id, "name": card.name},
                "attacker_player_id": player.id,
                "timeout_ms": 8000,
            })
            reaction_response = await open_reaction_window(
                game.code, reaction_target.id, timeout=8.0
            )
            await manager.send_to_player(game.code, reaction_target.user_id, {
                "type": ServerEvent.REACTION_WINDOW_CLOSED,
            })

    # ── Risoluzione reazione ──────────────────────────────────────────────────
    original_cancelled = False
    reaction_card_result: dict = {}

    if reaction_response and reaction_response.get("action") == "play" and reaction_target:
        rhc_id = reaction_response.get("hand_card_id")
        from app.models.game import PlayerHandCard as _RPHC
        rhc = db.get(_RPHC, rhc_id)
        if rhc and rhc.player_id == reaction_target.id:
            reaction_card = db.get(ActionCard, rhc.action_card_id)
            # Consuma la carta di reazione
            game.action_discard = (game.action_discard or []) + [rhc.action_card_id]
            db.delete(rhc)
            reaction_target.cards_played_this_turn += 1

            if reaction_card:
                if reaction_card.number == 20:
                    # Shield Platform: annulla la carta originale, nessun altro effetto
                    original_cancelled = True
                    reaction_card_result = {
                        "card_number": 20, "applied": True, "cancelled_original": True,
                    }
                elif reaction_card.number == 7 and card and card.card_type == "Economica":
                    # Chargeback come reazione a un furto di Licenze:
                    # annulla il furto e dà +1L al difensore (recupero + bonus)
                    original_cancelled = True
                    reaction_target.licenze += 1
                    reaction_card_result = {
                        "card_number": 7, "applied": True,
                        "cancelled_original": True, "licenze_gained": 1,
                    }
                else:
                    # Qualsiasi altra carta fuori turno: si applica,
                    # poi l'originale si applica comunque
                    reaction_card_result = apply_action_card_effect(
                        reaction_card, reaction_target, game, db,
                        target_player_id=player.id,
                    )

    # ── Card 99 (Web-to-Case) / Card 100 (Preference Center): target immunity checks ───────────
    if card and card_approved and not original_cancelled and target_player_id:
        _immunity_target = next(
            (p for p in game.players if p.id == target_player_id and p.id != player.id), None
        )
        if _immunity_target and _immunity_target.combat_state:
            # Card 99: block next offensive card targeting this player
            if _immunity_target.combat_state.get("web_to_case_active") and card.card_type == "Offensiva":
                original_cancelled = True
                _cs99 = dict(_immunity_target.combat_state)
                _cs99.pop("web_to_case_active", None)
                _immunity_target.combat_state = _cs99
                card_effect_result = {"card_number": card.number, "applied": False, "blocked_by": "web_to_case"}
            # Card 100: block cards of the immune type targeting this player
            elif _immunity_target.combat_state.get("preference_immunity_type") == card.card_type:
                original_cancelled = True
                _cs100 = dict(_immunity_target.combat_state)
                _cs100.pop("preference_immunity_type", None)
                _immunity_target.combat_state = _cs100
                card_effect_result = {"card_number": card.number, "applied": False, "blocked_by": "preference_center"}
            # Card 113 (Bounce Management): Offensiva ricochets back at attacker with double Licenze steal
            elif _immunity_target.combat_state.get("bounce_management_active") and card.card_type == "Offensiva":
                original_cancelled = True
                _cs113 = dict(_immunity_target.combat_state)
                _cs113.pop("bounce_management_active", None)
                _immunity_target.combat_state = _cs113
                player.licenze = max(0, player.licenze - 2)  # double-effect approximation
                card_effect_result = {"card_number": card.number, "applied": False, "blocked_by": "bounce_management", "attacker_licenze_lost": 2}
            # Card 117 (JMS Connector): delay any card targeting this player (block it once)
            elif _immunity_target.combat_state.get("jms_delay_active"):
                original_cancelled = True
                _cs117 = dict(_immunity_target.combat_state)
                _cs117.pop("jms_delay_active", None)
                _immunity_target.combat_state = _cs117
                card_effect_result = {"card_number": card.number, "applied": False, "blocked_by": "jms_delay"}
            # Card 206 (Landing Page): next Offensiva targeting this player gives +2L instead of effect
            elif _immunity_target.combat_state.get("landing_page_active") and card.card_type == "Offensiva":
                original_cancelled = True
                _cs206 = dict(_immunity_target.combat_state)
                _cs206.pop("landing_page_active", None)
                _immunity_target.combat_state = _cs206
                _immunity_target.licenze += 2
                card_effect_result = {"card_number": card.number, "applied": False, "blocked_by": "landing_page", "target_licenze_gained": 2}

    # Card 211 (Sales Engagement): any card played against a player with this flag gives that player +1L
    if card and card_approved and target_player_id and not original_cancelled:
        _se_target = next(
            (p for p in game.players if p.id == target_player_id and p.id != player.id), None
        )
        if _se_target and (_se_target.combat_state or {}).get("sales_engagement_active"):
            _se_target.licenze += 1

    # Card 222 (Block Kit): player's next card has -1 to its primary numeric effect
    if card and card_approved and not original_cancelled:
        _cs_bk = player.combat_state or {}
        if _cs_bk.get("block_kit_pending"):
            # Effect reduction: subtract 1L from the player (proxy: undo part of the card benefit)
            # The simplest hook: take back 1L if player gained any
            _gained = card_effect_result.get("licenze_gained", 0) if isinstance(card_effect_result, dict) else 0
            if _gained > 0:
                player.licenze = max(0, player.licenze - 1)
            _cs_bk2 = dict(player.combat_state)
            _cs_bk2.pop("block_kit_pending", None)
            player.combat_state = _cs_bk2

    # Card 207 (Feedback Management): any card targeting a player with this flag gives them +1L
    if card and card_approved and target_player_id and not original_cancelled:
        _fm_target = next(
            (p for p in game.players if p.id == target_player_id and p.id != player.id), None
        )
        if _fm_target and (_fm_target.combat_state or {}).get("feedback_management_remaining", 0) > 0:
            _fm_target.licenze += 1
            _cs_fm = dict(_fm_target.combat_state)
            _fm_rem = _cs_fm["feedback_management_remaining"] - 1
            if _fm_rem <= 0:
                _cs_fm.pop("feedback_management_remaining", None)
            else:
                _cs_fm["feedback_management_remaining"] = _fm_rem
            _fm_target.combat_state = _cs_fm

    # Card 201 (Web Studio): Offensiva targeting this player deals -1 effect (grant +1L refund to target)
    if card and card_approved and not original_cancelled and target_player_id and card.card_type == "Offensiva":
        _ws_target = next(
            (p for p in game.players if p.id == target_player_id and p.id != player.id), None
        )
        if _ws_target and (_ws_target.combat_state or {}).get("web_studio_active"):
            _ws_target.licenze += 1  # compensate 1 damage point

    # ── Effetto carta originale (a meno che non sia stato annullato) ──────────
    if not card_effect_result:
        card_effect_result = {}
    if card and card_approved and not original_cancelled:
        card_effect_result = apply_action_card_effect(
            card, player, game, db,
            target_player_id=target_player_id,
        )

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.CARD_PLAYED,
        "player_id": player.id,
        "card": {"id": card.id, "name": card.name, "effect": card.effect} if card else {},
        "effect_result": card_effect_result,
    })
    if reaction_card_result:
        await manager.broadcast(game.code, {
            "type": ServerEvent.REACTION_RESOLVED,
            "reactor_player_id": reaction_target.id if reaction_target else None,
            "original_cancelled": original_cancelled,
            "reaction_effect": reaction_card_result,
        })
    # Card 122 (Marketing Automation): while active, caster earns +1L each time they play a card
    if (player.combat_state or {}).get("marketing_automation_turns_remaining", 0) > 0:
        player.licenze += 1

    # Card 146 (Digital HQ): track distinct card types played this turn
    if card and card.card_type:
        _cs_ct = dict(player.combat_state or {})
        _types_played = list(_cs_ct.get("card_types_played_this_turn") or [])
        if card.card_type not in _types_played:
            _types_played.append(card.card_type)
            _cs_ct["card_types_played_this_turn"] = _types_played
            player.combat_state = _cs_ct

    # Card 234 (Integration Pattern): 2nd card played this turn has +1 to numeric effect
    if card and card_approved and not original_cancelled:
        if player.cards_played_this_turn == 2 and (player.combat_state or {}).get("integration_pattern_boost"):
            player.licenze += 1  # proxy: +1L as the numeric boost
            _cs_ip = dict(player.combat_state)
            _cs_ip.pop("integration_pattern_boost", None)
            player.combat_state = _cs_ip

    # Card 242 (App Builder): track type counts; draw 1 bonus when any type reaches 2 plays
    if card and card_approved and not original_cancelled and card.card_type:
        _cs_ab = player.combat_state or {}
        if _cs_ab.get("app_builder_active"):
            _ab_counts = dict(_cs_ab.get("app_builder_type_counts") or {})
            _ab_counts[card.card_type] = _ab_counts.get(card.card_type, 0) + 1
            _cs_ab2 = dict(_cs_ab)
            _cs_ab2["app_builder_type_counts"] = _ab_counts
            if _ab_counts[card.card_type] == 2:
                # Trigger bonus draw
                from app.models.game import PlayerHandCard as _PHC242
                if game.action_deck_1:
                    db.add(_PHC242(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
                elif game.action_deck_2:
                    db.add(_PHC242(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
                _cs_ab2.pop("app_builder_active", None)
                _cs_ab2.pop("app_builder_type_counts", None)
            player.combat_state = _cs_ab2

    # Card 120 (Event Monitoring): watchers earn 1L each time this player plays a card (max 2)
    for _watcher in game.players:
        if _watcher.id != player.id and (_watcher.combat_state or {}).get("event_monitoring_target_id") == player.id:
            _em = _watcher.combat_state.get("event_monitoring_remaining", 0)
            if _em > 0:
                _watcher.licenze += 1
                _wc = dict(_watcher.combat_state)
                if _em <= 1:
                    _wc.pop("event_monitoring_target_id", None)
                    _wc.pop("event_monitoring_remaining", None)
                else:
                    _wc["event_monitoring_remaining"] = _em - 1
                _watcher.combat_state = _wc
    db.commit()

    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)
    if reaction_target:
        await _send_hand_state(game.code, reaction_target, db)
    # Card 227 (Anypoint Visualizer): if any player has flag active, broadcast all hands to all players
    if any((p.combat_state or {}).get("anypoint_visualizer_active") for p in game.players):
        for _p in game.players:
            await _send_hand_state(game.code, _p, db)


async def _handle_buy_addon(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.action:
        await _error(game.code, user_id, "Cannot buy addon now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    # source: "market_1" | "market_2" | "deck_1" | "deck_2"
    source = data.get("source", "market_1")
    if source not in ("market_1", "market_2", "deck_1", "deck_2"):
        await _error(game.code, user_id, "Invalid source (market_1/market_2/deck_1/deck_2)")
        return

    if source == "market_1":
        if not game.addon_market_1:
            await _error(game.code, user_id, "No addon in market slot 1")
            return
        addon_id = game.addon_market_1
    elif source == "market_2":
        if not game.addon_market_2:
            await _error(game.code, user_id, "No addon in market slot 2")
            return
        addon_id = game.addon_market_2
    elif source == "deck_1":
        if not game.addon_deck_1:
            await _error(game.code, user_id, "Addon deck 1 is empty")
            return
        addon_id = game.addon_deck_1.pop(0)
    else:  # deck_2
        if not game.addon_deck_2:
            await _error(game.code, user_id, "Addon deck 2 is empty")
            return
        addon_id = game.addon_deck_2.pop(0)

    addon = db.get(AddonCard, addon_id)
    if not addon:
        await _error(game.code, user_id, "Addon not found")
        return

    # Card 18 (Org Takeover): opponent blocked this player from buying addons next turn
    if (player.combat_state or {}).get("addons_blocked_next_turn"):
        await _error(game.code, user_id, "Addon purchases blocked this turn (Org Takeover)")
        return

    # Card 139 (Prospect Lifecycle): addon purchases blocked until next boss defeat
    if (player.combat_state or {}).get("addons_blocked_until_boss_defeat"):
        await _error(game.code, user_id, "Addon purchases blocked until you defeat a boss (Prospect Lifecycle)")
        return

    # Card 189 (Delete Records): specific addon IDs blocked from repurchase for N turns
    _blocked_addon_ids = list((player.combat_state or {}).get("deleted_addon_blocked_ids") or [])
    if addon_id in _blocked_addon_ids:
        await _error(game.code, user_id, "This addon was deleted and cannot be repurchased yet (Delete Records)")
        return

    # Boss 60 (Connected App Infiltrator): addon purchases are blocked during this combat
    if player.is_in_combat and player.current_boss_id:
        if engine.boss_blocks_addon_purchase(player.current_boss_id):
            await _error(game.code, user_id, "Addon purchases are blocked by the boss")
            return

    cost = addon.cost + (player.pending_addon_cost_penalty or 0)
    # Card 272 (ISV Ecosystem): fix next addon cost to 5 for this turn (one-shot)
    if (player.combat_state or {}).get("isv_ecosystem_active"):
        cost = 5
        _cs_isv = dict(player.combat_state)
        _cs_isv.pop("isv_ecosystem_active", None)
        player.combat_state = _cs_isv
    # Card 47 (Contracted Price): fix next addon cost to 5 (overrides base cost + penalty)
    _price_fixed = (player.combat_state or {}).get("next_addon_price_fixed")
    if _price_fixed is not None:
        cost = _price_fixed
    else:
        # Card 48 (Price Rule): reduce next addon cost by N
        _price_discount = (player.combat_state or {}).get("next_addon_price_discount", 0)
        cost = max(0, cost - _price_discount)
        # Card 124 (Price Book): halve next addon cost (floor, min 5)
        if (player.combat_state or {}).get("next_addon_price_half"):
            cost = max(5, cost // 2)
        # Card 161 (Promotions Engine): -2L addon cost for N turns
        if (player.combat_state or {}).get("promotions_engine_turns_remaining", 0) > 0:
            cost = max(1, cost - 2)
        # Card 154 (Sustainability Cloud): discount = HP lost since card played
        _sus_hp_lost = (player.combat_state or {}).get("sustainability_hp_lost", 0)
        if _sus_hp_lost > 0 and (player.combat_state or {}).get("sustainability_discount_pending"):
            cost = max(1, cost - _sus_hp_lost)
            _cs_sus_buy = dict(player.combat_state)
            _cs_sus_buy.pop("sustainability_discount_pending", None)
            _cs_sus_buy.pop("sustainability_hp_lost", None)
            player.combat_state = _cs_sus_buy
    if player.licenze < cost:
        await _error(game.code, user_id, f"Need {cost} Licenze (have {player.licenze})")
        return

    player.licenze -= cost
    player.pending_addon_cost_penalty = 0  # penalty consumed on first purchase (boss 26)
    # Card 87 (Block Pricing): track cumulative addon spend for payout calculation
    cs_spend = dict(player.combat_state or {})
    cs_spend["total_addon_licenze_spent"] = cs_spend.get("total_addon_licenze_spent", 0) + cost
    player.combat_state = cs_spend
    # Consume addon price modifiers
    _cs_price = player.combat_state or {}
    if _price_fixed is not None or _cs_price.get("next_addon_price_discount", 0) or _cs_price.get("next_addon_price_half"):
        cs_addon = dict(_cs_price)
        cs_addon.pop("next_addon_price_fixed", None)
        cs_addon.pop("next_addon_price_discount", None)
        cs_addon.pop("next_addon_price_half", None)
        player.combat_state = cs_addon

    # Bought addons are tracked as owned by player; market slot gets refilled
    if source == "market_1":
        game.addon_market_1 = game.addon_deck_1.pop(0) if game.addon_deck_1 else None
    elif source == "market_2":
        game.addon_market_2 = game.addon_deck_2.pop(0) if game.addon_deck_2 else None
    # deck_1 / deck_2: card already popped above, nothing else to do

    from app.models.game import PlayerAddon
    db.add(PlayerAddon(player_id=player.id, addon_id=addon_id))

    # Card 160 (Storefront Reference): mark that this player bought an addon this turn
    _cs_bat = dict(player.combat_state or {})
    _cs_bat["bought_addon_this_turn"] = True
    player.combat_state = _cs_bat

    # TODO: triggherare gli addon passivi con trigger "quando acquisti un addon" (sia il nuovo che quelli già posseduti).
    # Alcuni addon esistenti danno bonus al momento dell'acquisto di un nuovo addon.
    # Va chiamata trigger_passive_addons(event="on_addon_bought", player, game, new_addon=addon, db).
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_BOUGHT,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name},
    })
    await _broadcast_state(game, db)


async def _handle_use_addon(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase not in (TurnPhase.action, TurnPhase.combat):
        await _error(game.code, user_id, "Cannot use addon now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    player_addon_id = data.get("player_addon_id")
    from app.models.game import PlayerAddon
    pa = db.get(PlayerAddon, player_addon_id)
    if not pa or pa.player_id != player.id:
        await _error(game.code, user_id, "Addon not owned by you")
        return

    addon = db.get(AddonCard, pa.addon_id)
    if not addon:
        await _error(game.code, user_id, "Addon not found")
        return

    if addon.addon_type.value != "Attivo":
        await _error(game.code, user_id, "Only active addons can be used manually")
        return

    if pa.is_tapped:
        await _error(game.code, user_id, "Addon is tapped (already used this turn)")
        return

    # Boss 31 (AppExchange Parasite): locked addon cannot be used during this fight
    if player.is_in_combat and player.combat_state:
        if player.combat_state.get("locked_addon_id") == pa.id:
            await _error(game.code, user_id, "This addon is locked by the boss for this fight")
            return

    # Boss 15 (trust.salesforce.DOOM) / Boss 79 (ISVForce Overlord): ALL addons disabled
    for p in game.players:
        if p.is_in_combat and p.current_boss_id:
            p_round = (p.combat_round or 0) + 1
            if engine.boss_disables_all_addons(p.current_boss_id, combat_round=p_round):
                await _error(game.code, user_id, "All addons are disabled while this boss is in play")
                return

    # Boss 4 (Cursed Friday Deployment) / Boss 77 (SFDX Imp): combatant's addons disabled
    if player.is_in_combat and player.current_boss_id:
        current_round = (player.combat_round or 0) + 1
        if engine.boss_addons_disabled(player.current_boss_id, current_round):
            await _error(game.code, user_id, "Addons are disabled by the boss this round")
            return

    pa.is_tapped = True

    # Card 185 (Record Triggered Flow): other players watching earn 1L when this player uses an addon
    for _watcher in game.players:
        if _watcher.id != player.id:
            _rtf = (_watcher.combat_state or {}).get("record_triggered_flow_remaining", 0)
            if _rtf > 0:
                _watcher.licenze += 1
                _wc_rtf = dict(_watcher.combat_state)
                _wc_rtf["record_triggered_flow_remaining"] = _rtf - 1
                if _wc_rtf["record_triggered_flow_remaining"] <= 0:
                    _wc_rtf.pop("record_triggered_flow_remaining", None)
                    _wc_rtf.pop("record_triggered_flow_watcher_id", None)
                _watcher.combat_state = _wc_rtf

    # Boss 49 (Managed Package Leech): boss heals 1 HP every time combatant activates an addon
    if player.is_in_combat and player.current_boss_id:
        boss_for_addon = db.get(BossCard, player.current_boss_id)
        heal = engine.boss_heals_on_addon_use(player.current_boss_id)
        if heal > 0 and boss_for_addon:
            player.current_boss_hp = min(boss_for_addon.hp, (player.current_boss_hp or 0) + heal)

    db.commit()
    db.refresh(game)

    # TODO: implementare gli effetti di tutti i 200 addon attivi.
    # Attualmente l'addon viene tappato ma il suo effetto NON viene applicato.
    # Ogni addon va gestito per nome (addon.name) o numero (addon.number) in
    # una funzione dedicata tipo apply_addon_effect(addon, player, game, db).
    # Gli addon Passivi hanno effetti che si attivano automaticamente in
    # determinati momenti del gioco (roll_dice, acquisto, inizio turno, ecc.)
    # e vanno anch'essi implementati nei punti giusti del flusso.
    # Vedere cards/addon_cards.md per l'effetto completo di ogni addon.

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_USED,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name, "effect": addon.effect},
    })
    await _broadcast_state(game, db)


async def _handle_end_turn(game: GameSession, user_id: int, db: Session):
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Game not in progress")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if game.current_phase not in (TurnPhase.action, TurnPhase.draw):
        await _error(game.code, user_id, "Cannot end turn now (in combat?)")
        return

    # ── FASE FINALE step 1: on-end abilities ─────────────────────────────────
    # TODO: trigger_passive_addons(event="on_turn_end", player, game, db)

    # ── FASE FINALE step 2: discard excess cards (hand > 10) ─────────────────
    hand_cards = list(player.hand)
    excess = len(hand_cards) - engine.MAX_HAND_SIZE
    if excess > 0:
        # Player must choose which to discard — for now auto-discard last drawn
        to_discard = hand_cards[-excess:]
        for hc_ex in to_discard:
            game.action_discard = (game.action_discard or []) + [hc_ex.action_card_id]
            db.delete(hc_ex)

    # ── FASE FINALE step 3: "until end of turn" effects expire ───────────────
    # TODO: expire timed effects stored in combat_state (e.g. "until_round" flags)
    # when a proper effect-duration system is introduced.

    # ── FASE FINALE step 4: reset HP to max_hp ───────────────────────────────
    player.hp = player.max_hp

    # Card 18 (Org Takeover): clear the one-turn addon block when this player's turn ends
    if player.combat_state and player.combat_state.get("addons_blocked_next_turn"):
        cs = dict(player.combat_state)
        cs.pop("addons_blocked_next_turn")
        player.combat_state = cs

    # Card 116 (API Rate Limiting): clear the rate limit after the affected turn ends
    if player.combat_state and player.combat_state.get("api_rate_limit_max_cards") is not None:
        cs = dict(player.combat_state)
        cs.pop("api_rate_limit_max_cards", None)
        player.combat_state = cs

    # Card 122 (Marketing Automation): decrement turns counter at turn end
    if player.combat_state and player.combat_state.get("marketing_automation_turns_remaining", 0) > 0:
        cs = dict(player.combat_state)
        cs["marketing_automation_turns_remaining"] -= 1
        if cs["marketing_automation_turns_remaining"] <= 0:
            cs.pop("marketing_automation_turns_remaining", None)
        player.combat_state = cs

    # Card 112 (Visitor Activity): decrement the mandatory-declaration counter at turn end
    if player.combat_state and player.combat_state.get("visitor_activity_turns", 0) > 0:
        cs = dict(player.combat_state)
        cs["visitor_activity_turns"] = cs["visitor_activity_turns"] - 1
        if cs["visitor_activity_turns"] <= 0:
            cs.pop("visitor_activity_turns", None)
        player.combat_state = cs

    # Card 37 (Free Trial): remove free trial addons at end of turn
    if player.combat_state and player.combat_state.get("free_trial_addon_player_addon_ids"):
        from app.models.game import PlayerAddon as _PA_ft
        trial_ids = list(player.combat_state.get("free_trial_addon_player_addon_ids", []))
        for pa_id in trial_ids:
            pa_ft = db.get(_PA_ft, pa_id)
            if pa_ft and pa_ft.player_id == player.id:
                game.addon_graveyard = (game.addon_graveyard or []) + [pa_ft.addon_id]
                db.delete(pa_ft)
        cs = dict(player.combat_state)
        cs.pop("free_trial_addon_player_addon_ids", None)
        player.combat_state = cs

    # Batch 7 end-of-turn cleanups (single cs mutation for performance)
    if player.combat_state:
        cs = dict(player.combat_state)
        # Card 160 (Storefront Reference): clear per-turn addon-bought flag
        cs.pop("bought_addon_this_turn", None)
        # Card 161 (Promotions Engine): decrement turns counter
        _pe = cs.get("promotions_engine_turns_remaining", 0)
        if _pe > 0:
            _pe -= 1
            if _pe <= 0:
                cs.pop("promotions_engine_turns_remaining", None)
            else:
                cs["promotions_engine_turns_remaining"] = _pe
        # Card 183 (Code Review): blocked card IDs expire after one turn
        cs.pop("code_review_blocked_card_ids", None)
        # Card 184 (Amendment Quote): one-turn nerf expires
        cs.pop("amendment_quote_active", None)
        # Card 187 (API Manager): decrement rate-limit turns; clear both when done
        _ar = cs.get("api_rate_limit_turns_remaining", 0)
        if _ar > 0:
            _ar -= 1
            if _ar <= 0:
                cs.pop("api_rate_limit_turns_remaining", None)
                cs.pop("api_rate_limit_max_cards", None)
            else:
                cs["api_rate_limit_turns_remaining"] = _ar
        # Card 188 (Update Records): decrement licenze-drain turns
        _ur = cs.get("update_records_licenze_drain_turns", 0)
        if _ur > 0:
            _ur -= 1
            if _ur <= 0:
                cs.pop("update_records_licenze_drain_turns", None)
            else:
                cs["update_records_licenze_drain_turns"] = _ur
        # Card 189 (Delete Records): decrement blocked-addon-repurchase turns
        _db_turns = cs.get("deleted_addon_block_turns_remaining", 0)
        if _db_turns > 0:
            _db_turns -= 1
            if _db_turns <= 0:
                cs.pop("deleted_addon_block_turns_remaining", None)
                cs.pop("deleted_addon_blocked_ids", None)
            else:
                cs["deleted_addon_block_turns_remaining"] = _db_turns
        # Card 190 (Unification Rule): one-turn rule expires
        cs.pop("unification_rule_active", None)
        cs.pop("unification_rule_card_type", None)
        # Card 146 (Digital HQ): clear per-turn card-types list
        cs.pop("card_types_played_this_turn", None)
        # Card 171 (Copilot Studio): clear per-round boost
        cs.pop("copilot_studio_boost_active", None)
        # Card 212 (High Velocity Sales): clear all-in flag
        cs.pop("high_velocity_all_in", None)
        # Card 211 (Sales Engagement): clear per-turn engagement flag
        cs.pop("sales_engagement_active", None)
        # Card 226 (Shortcut): consume extra plays granted this turn
        cs.pop("shortcut_extra_plays", None)
        # Card 201 (Web Studio): consume extra card slot granted this turn
        cs.pop("web_studio_extra_card", None)
        # Card 241 (Object Storage): clear per-turn theft immunity
        cs.pop("licenze_theft_immune", None)
        # Card 269 (Trailhead GO): clear per-turn max cards override
        cs.pop("trailhead_go_max_cards", None)
        # Card 283 (Queueable Job): clear per-turn max cards override
        cs.pop("queueable_job_max_cards", None)
        # Card 215 (B2B Analytics): decrement target reveal turns
        _ba = cs.get("b2b_analytics_turns", 0)
        if _ba > 0:
            _ba -= 1
            if _ba <= 0:
                cs.pop("b2b_analytics_turns", None)
                cs.pop("b2b_analytics_target_id", None)
            else:
                cs["b2b_analytics_turns"] = _ba
        # Card 227 (Anypoint Visualizer): clear per-turn flag
        cs.pop("anypoint_visualizer_active", None)
        # Card 213 (Cadence): track turns without combat
        if not player.is_in_combat:
            cs["cadence_no_combat_turns"] = cs.get("cadence_no_combat_turns", 0) + 1
        else:
            cs["cadence_no_combat_turns"] = 0
        # Card 258 (Salesforce Tower): one-turn HP floor expires
        cs.pop("salesforce_tower_active", None)
        # Card 262 (World Tour Event): one-turn boss reward bonus expires
        cs.pop("world_tour_event_active", None)
        cs.pop("world_tour_event_first_bonus", None)
        # Card 242 (App Builder): clear type counters if not triggered
        cs.pop("app_builder_type_counts", None)
        cs.pop("app_builder_active", None)
        # Card 249 (Work Item): recover 1 card from discard at end of turn
        if cs.pop("work_item_active", False):
            discard_wi = list(game.action_discard or [])
            if discard_wi:
                wi_card_id = discard_wi.pop(-1)
                game.action_discard = discard_wi
                from app.models.game import PlayerHandCard as _PHCWI
                if len(list(player.hand)) < engine.MAX_HAND_SIZE:
                    db.add(_PHCWI(player_id=player.id, action_card_id=wi_card_id))
        # Card 234 (Integration Pattern): clear boost if unused
        cs.pop("integration_pattern_boost", None)
        # Card 272 (ISV Ecosystem): clear per-turn cost-fix flag
        cs.pop("isv_ecosystem_active", None)
        # Card 273 (Trailhead Quest): clear per-turn card count tracking
        cs.pop("trailhead_quest_cards_played", None)
        # Card 287 (404 Not Found): clear if expired
        if cs.get("not_found_until_turn", 0) < game.turn_number:
            cs.pop("not_found_active", None)
            cs.pop("not_found_until_turn", None)
        # Card 271 (Ohana Pledge): clear truce if expired
        if cs.get("ohana_truce_until_turn", 0) < game.turn_number:
            cs.pop("ohana_truce_caster_id", None)
            cs.pop("ohana_truce_until_turn", None)
        player.combat_state = cs

    # Card 209 (Activity Score): track consecutive turns where player played at least 1 card
    if player.cards_played_this_turn > 0:
        _cs_act = dict(player.combat_state or {})
        _cs_act["consecutive_turns_with_cards"] = _cs_act.get("consecutive_turns_with_cards", 0) + 1
        player.combat_state = _cs_act
    else:
        _cs_act = dict(player.combat_state or {})
        if "consecutive_turns_with_cards" in _cs_act:
            _cs_act["consecutive_turns_with_cards"] = 0
            player.combat_state = _cs_act

    # Card 205 (MicroSite): track turns where player ended at full HP (not attacked / not damaged)
    if player.hp >= player.max_hp:
        _cs_ms = dict(player.combat_state or {})
        _cs_ms["turns_not_attacked"] = _cs_ms.get("turns_not_attacked", 0) + 1
        player.combat_state = _cs_ms
    else:
        _cs_ms = dict(player.combat_state or {})
        if "turns_not_attacked" in _cs_ms:
            _cs_ms["turns_not_attacked"] = 0
            player.combat_state = _cs_ms

    # Card 208 (Smart Capture Form): clear per-turn hand-reveal flag
    if player.combat_state and player.combat_state.get("hand_revealed_this_turn"):
        _cs_hrt = dict(player.combat_state)
        _cs_hrt.pop("hand_revealed_this_turn", None)
        player.combat_state = _cs_hrt

    player.cards_played_this_turn = 0

    # Advance turn
    game.current_turn_index = (game.current_turn_index + 1) % len(game.turn_order)
    if game.current_turn_index == 0:
        game.turn_number += 1
    game.current_phase = TurnPhase.draw

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.TURN_ENDED,
        "player_id": player.id,
        "next_player_id": game.turn_order[game.current_turn_index],
    })
    await _broadcast_state(game, db)
