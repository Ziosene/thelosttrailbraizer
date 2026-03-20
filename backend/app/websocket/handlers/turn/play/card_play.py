"""
Play-card phase handler.
"""
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state, _send_hand_state,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.models.card import ActionCard, BossCard
from app.game import engine
from app.game import engine_boss
from app.game.engine_cards import apply_action_card_effect
from app.game.engine_addons import has_addon as _has_addon_play
from app.game import engine_role as _engine_role
from app.websocket.reaction_manager import open_reaction_window


async def _handle_play_card(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase not in (TurnPhase.action, TurnPhase.combat):
        await _error(game.code, user_id, "Cannot play card now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    # Role passive: JavaScript Developer I can play 3 cards per turn
    _role_max_cards = _engine_role.get_cards_per_turn(player)
    _effective_max = max(engine.MAX_CARDS_PER_TURN, _role_max_cards)
    # Addon 87 (API Throttle Bypass): immune to boss card-play limits
    _boss_card_limit_raw = (
        engine.boss_max_cards_per_turn(player.current_boss_id, _effective_max)
        if player.is_in_combat and player.current_boss_id
        else _effective_max
    )
    max_cards = _effective_max if _has_addon_play(player, 87) else _boss_card_limit_raw
    # Card 116 (API Rate Limiting): opponent imposed a lower card-play limit for this turn
    _api_limit = (player.combat_state or {}).get("api_rate_limit_max_cards")
    if _api_limit is not None and not _has_addon_play(player, 87):
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
    # Addon 37 (Deployment Pipeline): +1 extra card this turn
    if (player.combat_state or {}).get("deployment_pipeline_extra_card"):
        max_cards += 1
    # Addon 150 (Wildcards): bypass card play limit for this turn
    _wildcards_play = (player.combat_state or {}).get("wildcards_active", False)
    if player.cards_played_this_turn >= max_cards and not _wildcards_play:
        await _error(game.code, user_id, "Card limit reached this turn")
        return

    # Valida il timing della carta (campo "Quando")
    if card:
        _when = (card.when or "").strip().lower()
        if _when in ("durante combattimento", "durante il combattimento"):
            if not player.is_in_combat:
                await _error(game.code, user_id, f"Carta '{card.name}' può essere giocata solo durante il combattimento")
                return
        elif _when in ("fuori dal combattimento", "fuori dal combat"):
            if player.is_in_combat:
                await _error(game.code, user_id, f"Carta '{card.name}' può essere giocata solo fuori dal combattimento")
                return
        # "In qualsiasi momento" e "Automatica" sono sempre valide

    if player.is_in_combat and player.current_boss_id:
        current_round_pc = (player.combat_round or 0) + 1

        # Boss  9 (Code Coverage Ghoul): offensive cards blocked
        if engine_boss.boss_offensive_cards_blocked(player.current_boss_id):
            if card and card.card_type == "offensiva":
                await _error(game.code, user_id, "Boss 9: offensive cards are blocked during this fight")
                return

        # Boss 17 (Validation Rule Hell): dice-modifier cards have no effect (silently consumed)
        _boss17_dice_blocked = engine_boss.boss_dice_modifiers_blocked(player.current_boss_id)

        # Boss  8 (MuleSoft Kraken): interference cards double their licenze effect
        _boss8_interference_doubled = engine_boss.boss_interference_doubled(player.current_boss_id)

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

    # Addon 65 (Permission Set Group): immune to locked_out flag
    if (player.combat_state or {}).get("locked_out") and not _has_addon_play(player, 65):
        await _error(game.code, user_id, "You are locked out and cannot play cards this turn")
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

    # Addon 54 (Unlocked Package): immune to boss abilities that block card play.
    # No boss currently uses the "blocks_card_play" engine flag — this section
    # is a placeholder for future boss abilities that generically block card play.

    game.action_discard.append(hc.action_card_id)
    db.delete(hc)
    # Card 243 (Einstein GPT): next card plays for free (no slot consumed)
    # Addon 113 (Batch Apex Scheduler): scheduled card plays for free (no slot consumed)
    _batch_scheduled113 = (player.combat_state or {}).get("batch_scheduled_active")
    _is_scheduled113 = _batch_scheduled113 is not None and card and card.id == _batch_scheduled113
    _egpt_free = (player.combat_state or {}).get("einstein_gpt_free_play")
    if _is_scheduled113:
        _cs113_play = dict(player.combat_state)
        _cs113_play.pop("batch_scheduled_active", None)
        player.combat_state = _cs113_play
        # Don't increment cards_played_this_turn
    elif _egpt_free:
        _cs_egpt = dict(player.combat_state)
        _cs_egpt.pop("einstein_gpt_free_play", None)
        player.combat_state = _cs_egpt
    else:
        # Addon 109 (Proof of Concept): one free card slot per turn
        _cs109_play = player.combat_state or {}
        if _cs109_play.get("proof_of_concept_active"):
            _cs109_new = dict(_cs109_play)
            _cs109_new.pop("proof_of_concept_active", None)
            player.combat_state = _cs109_new
        # Addon 71 (Workflow Rule Combo): first card each turn doesn't count toward limit
        elif _has_addon_play(player, 71) and not _cs109_play.get("first_card_free_used"):
            _cs71_new = dict(_cs109_play)
            _cs71_new["first_card_free_used"] = True
            player.combat_state = _cs71_new
        # Addon 195 (Copy/Paste): one free card play per activation
        elif _cs109_play.get('copy_paste_active'):
            _cs195p_new = dict(_cs109_play)
            del _cs195p_new['copy_paste_active']
            player.combat_state = _cs195p_new
            # skip cards_played increment
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

    # Addon 191 (404 Not Found): block incoming card targeting
    if card and card_approved and target_player_id:
        _tgt191 = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        if _tgt191 and (_tgt191.combat_state or {}).get('not_found_active'):
            await _error(game.code, user_id, "Target is 404 Not Found this turn")
            return

    # Check target-side protections for any card targeting another player
    if card and card_approved and target_player_id:
        _tgt_trust = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        # Addon 66 (Trust Layer): target is protected from all opponent cards for 1 turn
        if _tgt_trust and (_tgt_trust.combat_state or {}).get("trust_layer_active"):
            await _error(game.code, user_id, "Target is protected by Trust Layer")
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

            # Addon 184 (Trust First): block the very first offensive card ever played against this player
            if card_approved and _has_addon_play(_tgt_check, 184):
                _cs184 = _tgt_check.combat_state or {}
                if not _cs184.get('trust_first_used') and card.card_type == 'offensiva':
                    cs184_new = dict(_cs184)
                    cs184_new['trust_first_used'] = True
                    _tgt_check.combat_state = cs184_new
                    card_approved = False
                    db.commit()
                    await manager.broadcast(game.code, {"type": "trust_first_blocked", "player_id": _tgt_check.id})
                    await _broadcast_state(game, db)
                    return

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
        # Boss 17 (Validation Rule Hell): dice-modifier cards are silently consumed with no effect
        _b17_blocked = _boss17_dice_blocked if player.is_in_combat and player.current_boss_id else False
        _dice_modifier_types = {"manipolazione"}  # card types that modify dice
        _is_dice_modifier = card.card_type and card.card_type.lower() in _dice_modifier_types
        if _b17_blocked and _is_dice_modifier:
            card_effect_result = {"applied": False, "blocked_by": "validation_rule_hell"}
        else:
            card_effect_result = apply_action_card_effect(
                card, player, game, db,
                target_player_id=target_player_id,
            )
        # Boss 8 (MuleSoft Kraken): interference cards double their licenze steal/loss effect
        if (player.is_in_combat and player.current_boss_id and
                _boss8_interference_doubled and
                card.card_type and card.card_type.lower() == "interferenza" and
                isinstance(card_effect_result, dict) and card_effect_result.get("applied")):
            _licenze_stolen8 = card_effect_result.get("licenze_stolen", 0)
            _licenze_lost8 = card_effect_result.get("licenze_lost", 0)
            if _licenze_stolen8 > 0:
                _target8 = next((p for p in game.players if p.id == target_player_id), None)
                if _target8:
                    _extra8 = min(_licenze_stolen8, _target8.licenze)
                    _target8.licenze -= _extra8
                    player.licenze += _extra8
            if _licenze_lost8 > 0 and target_player_id:
                _target8b = next((p for p in game.players if p.id == target_player_id), None)
                if _target8b:
                    _extra8b = min(_licenze_lost8, _target8b.licenze)
                    _target8b.licenze -= _extra8b

    # ── Pending reaction: the engine function needs a reaction from the TARGET ──
    if isinstance(card_effect_result, dict) and card_effect_result.get("status") == "pending_reaction":
        _rt = card_effect_result.get("reaction_type")
        _rt_target_id = card_effect_result.get("target_player_id")
        _rt_target = next((p for p in game.players if p.id == _rt_target_id), None)

        if _rt == "play_or_discard" and _rt_target:
            # Card 114 (Salesforce Engage): target must play a card or one is auto-discarded
            await manager.send_to_player(game.code, _rt_target.user_id, {
                "type": "card114_play_or_discard",
                "caster_player_id": player.id,
                "options": card_effect_result.get("target_hand", []),
            })
            db.commit(); db.refresh(game)
            _r114 = await open_reaction_window(game.code, _rt_target.id, timeout=20.0)
            if _r114 and _r114.get("action") == "play" and _r114.get("hand_card_id"):
                # target chose to play a card — use existing play logic via reaction
                pass  # card is played via reaction window in normal flow
            else:
                # auto-discard a random card
                import random as _rnd114p
                _hand114p = list(_rt_target.hand)
                if _hand114p:
                    from app.models.game import PlayerHandCard as _PHC114p
                    _hc114p = _rnd114p.choice(_hand114p)
                    game.action_discard = (game.action_discard or []) + [_hc114p.action_card_id]
                    db.delete(_hc114p)
            card_effect_result = {"applied": True, "target_player_id": _rt_target_id}

        elif _rt == "comply_or_refuse" and _rt_target:
            # Card 115 (HTTP Connector): target complies (1L) or refuses (2L)
            await manager.send_to_player(game.code, _rt_target.user_id, {
                "type": "card115_comply_or_refuse",
                "caster_player_id": player.id,
                "comply_cost": card_effect_result.get("comply_cost", 1),
                "refuse_cost": card_effect_result.get("refuse_cost", 2),
            })
            db.commit(); db.refresh(game)
            _r115 = await open_reaction_window(game.code, _rt_target.id, timeout=20.0)
            if _r115 and _r115.get("action") == "refuse":
                _cost115 = min(card_effect_result.get("refuse_cost", 2), _rt_target.licenze)
                _rt_target.licenze -= _cost115
                # caster gets nothing on refusal
                card_effect_result = {"applied": True, "target_player_id": _rt_target_id, "refused": True, "target_licenze_lost": _cost115}
            else:
                # comply: target loses 1L, caster gains 1L
                _cost115c = min(card_effect_result.get("comply_cost", 1), _rt_target.licenze)
                _rt_target.licenze -= _cost115c
                player.licenze += _cost115c
                card_effect_result = {"applied": True, "target_player_id": _rt_target_id, "licenze_transferred": _cost115c}

    # ── Pending choice: the engine function needs player input before completing ──
    if isinstance(card_effect_result, dict) and card_effect_result.get("status") == "pending_choice":
        _cs_pending = dict(player.combat_state or {})
        _cs_pending["pending_card_choice"] = {
            "hand_card_id": hand_card_id,
            "card_number": card_effect_result["card_number"],
            "choice_type": card_effect_result["choice_type"],
            **{k: v for k, v in card_effect_result.items() if k not in ("status", "choice_type", "card_number")},
        }
        player.combat_state = _cs_pending
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "card_choice_required",
            "choice_type": card_effect_result["choice_type"],
            "card_number": card_effect_result["card_number"],
            "options": card_effect_result.get("options", []),
            **{k: v for k, v in card_effect_result.items() if k not in ("status", "choice_type", "card_number", "options")},
        })
        await _broadcast_state(game, db)
        return

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

    # Addon 103 (Named Credential): immune to interferenza cards that cause Licenze loss
    if card and card_approved and not original_cancelled and target_player_id and card.card_type == "Interferenza":
        _tgt103 = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        if _tgt103 and _has_addon_play(_tgt103, 103) and isinstance(card_effect_result, dict):
            _stolen103 = card_effect_result.get("licenze_stolen", 0)
            if _stolen103 and _stolen103 > 0:
                # Refund the stolen licenze back to target and reverse from caster
                _tgt103.licenze += _stolen103
                player.licenze = max(0, player.licenze - _stolen103)

    # Role passive: IAM Architect — immune to licenze theft (any card type)
    if card and card_approved and not original_cancelled and target_player_id and isinstance(card_effect_result, dict):
        _tgt_iam = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        if _tgt_iam and _engine_role.is_immune_to_licenze_theft(_tgt_iam):
            _stolen_iam = card_effect_result.get("licenze_stolen", 0)
            if _stolen_iam and _stolen_iam > 0:
                # Refund the stolen licenze back to target and reverse from caster
                _tgt_iam.licenze += _stolen_iam
                player.licenze = max(0, player.licenze - _stolen_iam)
                card_effect_result = dict(card_effect_result)
                card_effect_result["licenze_stolen"] = 0

    # Role passive: Role Hierarchy (addon 64) — passive addon, always active
    # If target has addon 64 AND target's seniority > attacker's seniority, halve licenze_stolen
    if card and card_approved and not original_cancelled and target_player_id and isinstance(card_effect_result, dict):
        _tgt64 = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        if _tgt64:
            _rh_active64 = any(
                pa.addon.number == 64 and not pa.is_tapped
                for pa in (_tgt64.addons if hasattr(_tgt64, "addons") else [])
                if pa.addon
            )
            if _rh_active64:
                from app.models.game import Seniority as _SenRH64
                _RH_RANK64 = {_SenRH64.junior: 1, _SenRH64.experienced: 2, _SenRH64.senior: 3, _SenRH64.evangelist: 4}
                _my_rank_rh64 = _RH_RANK64.get(player.seniority, 0)
                _target_rank_rh64 = _RH_RANK64.get(_tgt64.seniority, 0)
                if _target_rank_rh64 > _my_rank_rh64:
                    _stolen_rh64 = card_effect_result.get("licenze_stolen", 0)
                    if _stolen_rh64 > 0:
                        _refund_rh64 = _stolen_rh64 - _stolen_rh64 // 2
                        _tgt64.licenze += _refund_rh64
                        player.licenze = max(0, player.licenze - _refund_rh64)
                        card_effect_result = dict(card_effect_result)
                        card_effect_result["licenze_stolen"] = _stolen_rh64 // 2

    # Role passive: Marketing Cloud Developer — offensive cards deal +1 damage (applied as +1L grant to caster)
    # NOTE: boss HP damage is handled separately in roll.py; here we handle player-vs-player offensive cards
    if card and card_approved and not original_cancelled and target_player_id and card.card_type == "Offensiva":
        _mcd_bonus = _engine_role.get_offensive_card_bonus_damage(player)
        if _mcd_bonus > 0:
            _tgt_mcd = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
            if _tgt_mcd:
                # Steal 1 extra licenza from target as bonus offensive damage
                _mcd_steal = min(_mcd_bonus, _tgt_mcd.licenze)
                _tgt_mcd.licenze -= _mcd_steal
                player.licenze += _mcd_steal

    # Addon 168 (Role Conflict): when an opponent with the same role plays a card against you, effect halved
    if card and card_approved and not original_cancelled and target_player_id and isinstance(card_effect_result, dict):
        _tgt168 = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        if _tgt168 and _has_addon_play(_tgt168, 168):
            _attacker_role168 = getattr(player, "role", None)
            _target_role168 = getattr(_tgt168, "role", None)
            if _attacker_role168 and _target_role168 and _attacker_role168 == _target_role168:
                # Halve licenze_stolen and hp_damage
                _stolen168 = card_effect_result.get("licenze_stolen", 0)
                _hp_dmg168 = card_effect_result.get("hp_damage", 0)
                if _stolen168 > 0:
                    _refund168 = _stolen168 - _stolen168 // 2
                    _tgt168.licenze += _refund168
                    player.licenze = max(0, player.licenze - _refund168)
                    card_effect_result = dict(card_effect_result)
                    card_effect_result["licenze_stolen"] = _stolen168 // 2
                if _hp_dmg168 > 0:
                    card_effect_result = dict(card_effect_result)
                    card_effect_result["hp_damage"] = _hp_dmg168 // 2
                await manager.broadcast(game.code, {
                    "type": "addon_103_blocked",
                    "player_id": _tgt103.id,
                    "licenze_refunded": _stolen103,
                })

    # Addon 14 (Salesforce Billing): target recovers 1L when licenze are stolen from them
    if card and card_approved and not original_cancelled and isinstance(card_effect_result, dict):
        _stolen14 = card_effect_result.get("licenze_stolen", 0)
        _stolen_from14 = card_effect_result.get("from_player_id")
        if _stolen14 and _stolen14 > 0 and _stolen_from14:
            _victim14 = next((p for p in game.players if p.id == _stolen_from14), None)
            if _victim14 and _has_addon_play(_victim14, 14):
                _victim14.licenze += 1

    # Addon 182 (Salesforce Values): when playing defensive or economic card during opponent's turn, gain 2L
    if card and card_approved and not original_cancelled and _has_addon_play(player, 182):
        _current_turn_player_id182 = game.turn_order[game.current_turn_index] if game.turn_order else None
        if _current_turn_player_id182 and _current_turn_player_id182 != player.id:
            _card_type182 = card.card_type if card else ''
            if _card_type182 in ('difensiva', 'economica', 'Difensiva', 'Economica'):
                player.licenze += 2

    # Addon 8 (MuleSoft Connector): other players with this addon earn +1L when this player plays a card
    if card and card_approved and not original_cancelled:
        for _other8 in game.players:
            if _other8.id != player.id and _has_addon_play(_other8, 8):
                _other8.licenze += 1

    # Addon 20 (Custom Metadata): +1L extra on any licenze gain from a card action
    if card and card_approved and not original_cancelled:
        _gained20 = card_effect_result.get("licenze_gained", 0) if isinstance(card_effect_result, dict) else 0
        if _gained20 > 0 and _has_addon_play(player, 20):
            player.licenze += 1

    # Addon 25 (Proactive Monitoring): if an opponent's card targets you, gain 1L
    if card and card_approved and not original_cancelled and target_player_id and target_player_id != player.id:
        _target25 = next((p for p in game.players if p.id == target_player_id), None)
        if _target25 and _has_addon_play(_target25, 25):
            _target25.licenze += 1

    # Addon 18 (Field History Tracking): track last played card as last discarded
    if card and card_approved and not original_cancelled:
        _cs18_play = dict(player.combat_state or {})
        _cs18_play["last_discarded_card_id"] = hc.action_card_id
        player.combat_state = _cs18_play

    # Addon 47 (Partner Community): +1L when you play a card that gives L or HP to another player
    if card and card_approved and not original_cancelled and target_player_id and target_player_id != player.id:
        if _has_addon_play(player, 47) and isinstance(card_effect_result, dict):
            _licenze_to_target47 = card_effect_result.get("target_compensation_licenze", 0)
            # Also check if the target gained licenze or HP through positive effects
            # Cards that donate L directly (e.g., "licenze_donated" key)
            _donated47 = card_effect_result.get("licenze_donated", 0)
            if _licenze_to_target47 > 0 or _donated47 > 0:
                player.licenze += 1

    # Addon 61 (Org Wide Default): offensive cards targeting this player have -1 effectiveness
    if card and card_approved and not original_cancelled and target_player_id and card.card_type == "Offensiva":
        _tgt61 = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        if _tgt61 and _has_addon_play(_tgt61, 61) and isinstance(card_effect_result, dict):
            # Reduce licenze_stolen by 1 (min 0), give back to target
            _stolen61 = card_effect_result.get("licenze_stolen", 0)
            if _stolen61 > 0:
                _reduction61 = min(1, _stolen61)
                _tgt61.licenze += _reduction61

    # Card 57 (API Proxy): defensive card — next offensive card against target loses 1 from licenze_stolen/hp_damage
    if card and card_approved and not original_cancelled and target_player_id and card.card_type == "Offensiva":
        _tgt57 = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        if _tgt57 and (_tgt57.combat_state or {}).get("api_proxy_active") and isinstance(card_effect_result, dict):
            _stolen57 = card_effect_result.get("licenze_stolen", 0)
            _hp57 = card_effect_result.get("hp_damage", 0)
            if _stolen57 > 0:
                _tgt57.licenze += 1
                card_effect_result["licenze_stolen"] = max(0, _stolen57 - 1)
            elif _hp57 > 0:
                card_effect_result["hp_damage"] = max(0, _hp57 - 1)
            # Consume the proxy
            _cs57_clear = dict(_tgt57.combat_state)
            _cs57_clear.pop("api_proxy_active", None)
            _tgt57.combat_state = _cs57_clear

    # Addon 79 (Auto-Response Rules): when hit by offensive card, steal 1L from attacker
    if card and card_approved and not original_cancelled and target_player_id and card.card_type == "Offensiva":
        _tgt79 = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        if _tgt79 and _has_addon_play(_tgt79, 79) and player.licenze > 0:
            player.licenze -= 1
            _tgt79.licenze += 1

    # Card 77 (Kafka Connector): any player with kafka_connector_turns_remaining earns +1L per card played
    if card and card_approved and not original_cancelled:
        for _kc_player in game.players:
            _kc_cs = _kc_player.combat_state or {}
            _kc_turns = _kc_cs.get("kafka_connector_turns_remaining", 0)
            if _kc_turns > 0 and _kc_player.id != player.id:
                _kc_player.licenze += 1
                _kc_new = dict(_kc_cs)
                _kc_new["kafka_connector_turns_remaining"] = _kc_turns - 1
                _kc_player.combat_state = _kc_new

    # Card 118 (Spike Control): cap licenze_stolen at 2 when target has spike_control active
    if card and card_approved and not original_cancelled and target_player_id and isinstance(card_effect_result, dict):
        _tgt118 = next((p for p in game.players if p.id == target_player_id and p.id != player.id), None)
        if _tgt118 and (_tgt118.combat_state or {}).get("spike_control_turns_remaining", 0) > 0:
            _stolen118 = card_effect_result.get("licenze_stolen", 0)
            if _stolen118 > 2:
                _excess118 = _stolen118 - 2
                _tgt118.licenze += _excess118
                player.licenze = max(0, player.licenze - _excess118)

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
