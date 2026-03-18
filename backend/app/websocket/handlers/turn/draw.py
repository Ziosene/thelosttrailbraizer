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

    # Addon 16 (License Manager): +1L at turn start if player has fewer licenze than any opponent
    if _has_addon_draw(player, 16):
        _others_licenze = [p.licenze for p in game.players if p.id != player.id]
        if _others_licenze and player.licenze < max(_others_licenze):
            player.licenze += 1

    # Addon 10 (Platform Cache): hand size up to 12 instead of 10
    _max_hand = 12 if _has_addon_draw(player, 10) else engine.MAX_HAND_SIZE
    if len(player.hand) >= _max_hand:
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

    # Addon 17 (Knowledge Base): draw 1 extra card at start of turn
    if _has_addon_draw(player, 17) and not jinxed:
        _max_hand17 = 12 if _has_addon_draw(player, 10) else engine.MAX_HAND_SIZE
        if len(list(player.hand)) < _max_hand17:
            _extra17 = None
            if deck_num == 1 and game.action_deck_1:
                _extra17 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _extra17 = game.action_deck_2.pop(0)
            if _extra17:
                from app.models.game import PlayerHandCard as _PHC17
                db.add(_PHC17(player_id=player.id, action_card_id=_extra17))

    # TODO: trigger_passive_addons(event="on_draw", player, game, db)

    game.current_phase = TurnPhase.action
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {"type": ServerEvent.CARD_DRAWN, "player_id": player.id})
    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)
