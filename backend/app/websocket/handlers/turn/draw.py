"""
Draw-card phase handler.
"""
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state, _send_hand_state,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.game import engine
from app.game.engine_addons import has_addon as _has_addon_draw


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

    # ── FASE INIZIALE step 0: Tech Debt check BEFORE untapping ───────────────
    # Addon 107 (Tech Debt): each addon idle for 3 consecutive turns generates 1L
    if _has_addon_draw(player, 107):
        _cs107 = dict(player.combat_state or {})
        _td107 = _cs107.get("tech_debt_turns", {})
        _earned107 = 0
        for _pa107 in player.addons:
            _key107 = str(_pa107.id)
            if _pa107.is_tapped:
                # was used last turn (still tapped before untap), reset counter
                _td107[_key107] = 0
            else:
                _td107[_key107] = _td107.get(_key107, 0) + 1
                if _td107[_key107] >= 3:
                    _earned107 += 1
                    _td107[_key107] = 0
        if _earned107:
            player.licenze += _earned107
        _cs107["tech_debt_turns"] = _td107
        player.combat_state = _cs107

    # ── FASE INIZIALE step 1: Untap all addons (moved from end_turn) ─────────
    for pa in player.addons:
        pa.is_tapped = False

    # ── FASE INIZIALE step 2: on-start abilities ──────────────────────────────
    # Passive addon effects on turn start are handled inline below (addons 43, 48, 78, etc.)

    # Card 111 (Tracking Pixel): send target's current hand to tracker at start of each turn
    _tp111 = (player.combat_state or {}).get("tracking_pixel_target_id")
    _tp111_turns = (player.combat_state or {}).get("tracking_pixel_turns", 0)
    if _tp111 and _tp111_turns > 0:
        _tp111_target = next((p for p in game.players if p.id == _tp111), None)
        if _tp111_target:
            from app.models.card import ActionCard as _AC111d
            _hand111 = []
            for hc111 in _tp111_target.hand:
                c111 = db.get(_AC111d, hc111.action_card_id)
                if c111:
                    _hand111.append({"id": c111.id, "number": c111.number, "name": c111.name})
            await manager.send_to_player(game.code, player.user_id, {
                "type": "tracking_pixel_update",
                "target_player_id": _tp111,
                "target_licenze": _tp111_target.licenze,
                "target_hand": _hand111,
                "turns_remaining": _tp111_turns - 1,
            })
        _cs111 = dict(player.combat_state)
        _cs111["tracking_pixel_turns"] = _tp111_turns - 1
        if _cs111["tracking_pixel_turns"] <= 0:
            _cs111.pop("tracking_pixel_target_id", None)
            _cs111.pop("tracking_pixel_turns", None)
        player.combat_state = _cs111

    # ── FASE INIZIALE step 3: process cross-turn combat_state flags ───────────
    _cs_init = dict(player.combat_state or {})
    # Addon 71 (Workflow Rule Combo): clear first_card_free_used at turn start
    _cs_init.pop("first_card_free_used", None)
    # Addon 72 (Process Builder Chain): clear addons_used_this_turn at turn start
    _cs_init.pop("addons_used_this_turn", None)
    # Addon 109 (Proof of Concept): clear per-turn used flag at turn start
    _cs_init.pop("proof_of_concept_used_this_turn", None)
    # Addon 110 (Go-Live Celebration): clear per-turn purchase flag at turn start
    _cs_init.pop("go_live_bought_this_turn", None)
    # Addon 115 (Future Method): clear active flag at turn start (in case combat ended without rolling)
    _cs_init.pop("future_method_active", None)
    # Addon 118 (Pub/Sub API): clear pubsub_earned_from at own turn start
    _cs_init.pop("pubsub_earned_from", None)
    # Addon 124 (Bulk API): clear per-turn bulk purchase slots (per-game used flag persists)
    _cs_init.pop("bulk_api_purchases_remaining", None)
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

    # Addon 117 (Change Data Capture): apply pending recovery from last turn (+2L if lost ≥5L last turn)
    if _has_addon_draw(player, 117):
        _cs117 = dict(player.combat_state or {})
        if _cs117.get("cdc_recovery_pending"):
            player.licenze += 2
            del _cs117["cdc_recovery_pending"]
        _cs117["cdc_licenze_start"] = player.licenze
        player.combat_state = _cs117

    # Addon 113 (Batch Apex Scheduler): deliver scheduled card at turn start (add to hand)
    _cs113_draw = player.combat_state or {}
    if _cs113_draw.get("batch_scheduled_card_id"):
        _scheduled_id113 = _cs113_draw["batch_scheduled_card_id"]
        _cs113_new_draw = dict(_cs113_draw)
        _cs113_new_draw["batch_scheduled_active"] = _scheduled_id113
        del _cs113_new_draw["batch_scheduled_card_id"]
        from app.models.game import PlayerHandCard as _PHC113draw
        db.add(_PHC113draw(player_id=player.id, action_card_id=_scheduled_id113))
        player.combat_state = _cs113_new_draw

    # Addon 120 (Scheduled Flow): decrement countdown at turn start; grant reward when expired
    if _has_addon_draw(player, 120):
        _cs120d = dict(player.combat_state or {})
        if _cs120d.get("scheduled_flow_countdown") is not None:
            _cs120d["scheduled_flow_countdown"] -= 1
            if _cs120d["scheduled_flow_countdown"] <= 0:
                player.licenze += _cs120d.get("scheduled_flow_reward", 0)
                del _cs120d["scheduled_flow_countdown"]
                del _cs120d["scheduled_flow_reward"]
            player.combat_state = _cs120d

    # Addon 131 (Spring Release): every 5 turns, gain 2L automatically
    if _has_addon_draw(player, 131):
        _cs131 = dict(player.combat_state or {})
        _cs131["spring_release_turns"] = _cs131.get("spring_release_turns", 0) + 1
        if _cs131["spring_release_turns"] >= 5:
            player.licenze += 2
            _cs131["spring_release_turns"] = 0
        player.combat_state = _cs131

    # Addon 133 (Winter Release): each addon owned for ≥5 turns gives +1L at start (max 3L)
    if _has_addon_draw(player, 133):
        _cs133d = dict(player.combat_state or {})
        _aq133d = _cs133d.get("addon_acquired_turns", {})
        _earned133 = 0
        for _pa133 in player.addons:
            _acquired_turn133 = _aq133d.get(str(_pa133.id), game.turn_number)
            if game.turn_number - _acquired_turn133 >= 5:
                _earned133 += 1
        player.licenze += min(_earned133, 3)

    # Addon 16 (License Manager): +1L at turn start if player has fewer licenze than any opponent
    if _has_addon_draw(player, 16):
        _others_licenze = [p.licenze for p in game.players if p.id != player.id]
        if _others_licenze and player.licenze < max(_others_licenze):
            player.licenze += 1

    # Addon 21 (Health Cloud): if exactly 1 HP at turn start, restore to full HP
    if _has_addon_draw(player, 21) and player.hp == 1:
        player.hp = player.max_hp

    # Addon 30 (Agentforce): gain 1L at turn start; 2L if more addons than any opponent
    if _has_addon_draw(player, 30):
        _own_addon_count = len(player.addons)
        _max_opponent_addons = max((len(p.addons) for p in game.players if p.id != player.id), default=0)
        player.licenze += 2 if _own_addon_count > _max_opponent_addons else 1

    # Addon 35 (Scheduled Job): gain 1L at turn start if not in combat
    if _has_addon_draw(player, 35) and not player.is_in_combat:
        player.licenze += 1

    # Addon 94 (Release Train): every 4 turns, gain 1 free addon from the deck
    if _has_addon_draw(player, 94):
        _cs94 = dict(player.combat_state or {})
        _cs94["release_train_turns"] = _cs94.get("release_train_turns", 0) + 1
        if _cs94["release_train_turns"] >= 4:
            _cs94["release_train_turns"] = 0
            _addon_id94 = None
            if game.addon_deck_1:
                _addon_deck94 = list(game.addon_deck_1)
                _addon_id94 = _addon_deck94.pop(0)
                game.addon_deck_1 = _addon_deck94
            elif game.addon_deck_2:
                _addon_deck94b = list(game.addon_deck_2)
                _addon_id94 = _addon_deck94b.pop(0)
                game.addon_deck_2 = _addon_deck94b
            if _addon_id94:
                from app.models.game import PlayerAddon as _PA94
                db.add(_PA94(player_id=player.id, addon_id=_addon_id94, is_tapped=False))
                await manager.broadcast(game.code, {
                    "type": "release_train_addon",
                    "player_id": player.id,
                    "addon_card_id": _addon_id94,
                })
        player.combat_state = _cs94

    # Addon 96 (Backlog Refinement): at start of turn, peek at next addon in deck
    if _has_addon_draw(player, 96):
        _peek96 = (game.addon_deck_1 or [])[:1] or (game.addon_deck_2 or [])[:1]
        if _peek96:
            await manager.send_to_player(game.code, player.user_id, {
                "type": "backlog_refinement_peek",
                "addon_card_id": _peek96[0],
            })

    # Addon 10 (Platform Cache): hand size up to 12 instead of 10
    # Addon 100 (Kanban Board): hand size up to 12 instead of 10
    # Addon 112 (Asynchronous Callout): +1 extra card beyond hand limit
    _max_hand = 12 if (_has_addon_draw(player, 10) or _has_addon_draw(player, 100)) else engine.MAX_HAND_SIZE
    if _has_addon_draw(player, 112):
        _max_hand += 1
    if len(player.hand) >= _max_hand:
        await _error(game.code, user_id, "Hand is full")
        return

    deck_num = data.get("deck", 1)  # client sends 1 or 2
    if deck_num not in (1, 2):
        await _error(game.code, user_id, "Invalid deck number (must be 1 or 2)")
        return

    # Track whether the deck was exhausted before this draw (for Addon 177 Stack Overflow)
    _deck_was_exhausted_177 = not game.action_deck_1 and not game.action_deck_2

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

    # Addon 118 (Pub/Sub API): when any opponent draws a card, players with addon 118 gain 1L (max 1 per opponent per turn)
    for _p118 in game.players:
        if _p118.id != player.id and _has_addon_draw(_p118, 118):
            _cs118 = dict(_p118.combat_state or {})
            _already_got118 = list(_cs118.get("pubsub_earned_from") or [])
            if player.id not in _already_got118:
                _p118.licenze += 1
                _already_got118.append(player.id)
                _cs118["pubsub_earned_from"] = _already_got118
                _p118.combat_state = _cs118

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

    # Addon 177 (Stack Overflow): when action deck runs out and reshuffles, draw 1 extra card
    if _has_addon_draw(player, 177) and _deck_was_exhausted_177 and not jinxed:
        _extra177 = None
        if game.action_deck_1:
            _extra177 = game.action_deck_1.pop(0)
        elif game.action_deck_2:
            _extra177 = game.action_deck_2.pop(0)
        if _extra177:
            from app.models.game import PlayerHandCard as _PHC177
            db.add(_PHC177(player_id=player.id, action_card_id=_extra177))

    # Addon 17 (Knowledge Base): draw 1 extra card at start of turn
    if _has_addon_draw(player, 17) and not jinxed:
        _max_hand17 = 12 if (_has_addon_draw(player, 10) or _has_addon_draw(player, 100)) else engine.MAX_HAND_SIZE
        if len(list(player.hand)) < _max_hand17:
            _extra17 = None
            if deck_num == 1 and game.action_deck_1:
                _extra17 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _extra17 = game.action_deck_2.pop(0)
            if _extra17:
                from app.models.game import PlayerHandCard as _PHC17
                db.add(_PHC17(player_id=player.id, action_card_id=_extra17))

    # Passive addon effects on draw are handled inline below (addon 41, etc.)

    # Addon 41 (Trailhead Quest): every 5 cards drawn, gain 1L
    if _has_addon_draw(player, 41) and not jinxed:
        _cs41 = dict(player.combat_state or {})
        _cs41["quest_cards_drawn"] = _cs41.get("quest_cards_drawn", 0) + 1
        if _cs41["quest_cards_drawn"] >= 5:
            player.licenze += 1
            _cs41["quest_cards_drawn"] = 0
        player.combat_state = _cs41

    # Addon 43 (Subscription Billing): +1L automatically at start of each turn
    if _has_addon_draw(player, 43):
        player.licenze += 1

    # Addon 190 (Salesforce+ Premium): draw 1 extra card AND gain 1L at start of each turn
    if _has_addon_draw(player, 190):
        player.licenze += 1
        from app.models.game import PlayerHandCard as _PHC190
        _cid190 = None
        if game.action_deck_1:
            _cid190 = game.action_deck_1.pop(0)
        elif game.action_deck_2:
            _cid190 = game.action_deck_2.pop(0)
        if _cid190:
            db.add(_PHC190(player_id=player.id, action_card_id=_cid190))

    # Addon 200 (The Lost Trailbraizer): +1L per turn
    if _has_addon_draw(player, 200):
        player.licenze += 1

    # Addon 70 (Einstein Relationship Insights): see all opponents' hands
    if _has_addon_draw(player, 70):
        db.flush()
        _all_hands70 = {
            str(p.id): [{"id": hc.id, "action_card_id": hc.action_card_id} for hc in p.hand]
            for p in game.players if p.id != player.id
        }
        await manager.send_to_player(game.code, player.user_id, {
            "type": "einstein_insights",
            "hands": _all_hands70,
        })

    # Addon 78 (Validation Rule): draw 2 cards instead of 1 if hand < 5 at turn start
    if _has_addon_draw(player, 78) and not jinxed:
        db.flush()
        _hand_count78 = len(list(player.hand))
        if _hand_count78 < 5:
            _extra78 = None
            if game.action_deck_1:
                _extra78 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _extra78 = game.action_deck_2.pop(0)
            if _extra78 is not None:
                from app.models.game import PlayerHandCard as _PHC78
                db.add(_PHC78(player_id=player.id, action_card_id=_extra78))

    # Addon 148 (Last Stand): if player is only one with 0 certs while all others have ≥1, +1HP and +2 dice
    if _has_addon_draw(player, 148):
        _others148 = [p for p in game.players if p.id != player.id]
        if (
            player.certificazioni == 0
            and _others148
            and all(p.certificazioni >= 1 for p in _others148)
        ):
            player.hp = min(player.hp + 1, player.max_hp)
            cs148 = dict(player.combat_state or {})
            cs148["last_stand_active"] = True
            player.combat_state = cs148
        else:
            cs148 = dict(player.combat_state or {})
            cs148.pop("last_stand_active", None)
            player.combat_state = cs148

    # Addon 48 (Net Zero Tracker): every 5 turns completed without dying, gain 3L
    if _has_addon_draw(player, 48):
        _cs48 = dict(player.combat_state or {})
        _cs48["net_zero_turns"] = _cs48.get("net_zero_turns", 0) + 1
        if _cs48["net_zero_turns"] >= 5:
            player.licenze += 3
            _cs48["net_zero_turns"] = 0
        player.combat_state = _cs48

    # Addon 170 (Promotion): decrement temporary seniority promotion counter at turn start
    if _has_addon_draw(player, 170):
        _cs170d = dict(player.combat_state or {})
        if _cs170d.get("promotion_turns_remaining"):
            _cs170d["promotion_turns_remaining"] -= 1
            if _cs170d["promotion_turns_remaining"] <= 0:
                # Revert seniority
                _orig170 = _cs170d.pop("promotion_original_seniority", None)
                _cs170d.pop("promotion_turns_remaining", None)
                if _orig170 is not None:
                    from app.models.game import Seniority as _Sen170d, SENIORITY_HP as _HP170d
                    try:
                        _orig_sen170 = _Sen170d(_orig170)
                        player.seniority = _orig_sen170
                        player.max_hp = _HP170d[_orig_sen170]
                        player.hp = min(player.hp, player.max_hp)
                    except (ValueError, TypeError):
                        pass
            player.combat_state = _cs170d

    # Addon 180 (Memory Leak): when this player draws more than 1 card, 1 goes to a Memory Leak holder
    # Count total cards drawn this turn (base 1, +1 if Stack Overflow triggered, +1 if addon 17, etc.)
    # We detect by flushing and counting the player's hand relative to start
    if not jinxed:
        db.flush()
        _hand_after180 = list(player.hand)
        # Estimate cards drawn: any opponent with addon 180 can steal the last one if >1 drawn
        # We track via the difference; simplest: check if addon 177 or 17 or 78 added extras
        _drew_extra180 = (
            _has_addon_draw(player, 177) and _deck_was_exhausted_177 or
            _has_addon_draw(player, 17) or
            (_has_addon_draw(player, 78) and len(_hand_after180) > 0)
        )
        if _drew_extra180 and len(_hand_after180) >= 1:
            for _p180 in game.players:
                if _p180.id != player.id and _has_addon_draw(_p180, 180):
                    # Steal 1 card from the just-drawn cards (last in hand)
                    if _hand_after180:
                        _stolen180 = _hand_after180[-1]
                        _stolen180.player_id = _p180.id
                    break  # only one player can steal per draw

    game.current_phase = TurnPhase.action
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {"type": ServerEvent.CARD_DRAWN, "player_id": player.id})
    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)
