"""
End-turn phase handler.
"""
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.game import engine
from app.game.engine_addons import has_addon as _has_addon_end


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
    # Passive addon effects on turn end are handled inline below (addons 125, 117, 183, etc.)

    # Card 74 (Routing Configuration): if player still has routing_assigned at end of turn, lose 2L
    _cs74 = player.combat_state or {}
    if _cs74.get("routing_assigned"):
        player.licenze = max(0, player.licenze - 2)
        cs74_clear = dict(_cs74)
        cs74_clear.pop("routing_assigned", None)
        cs74_clear.pop("routing_assigned_boss_id", None)
        player.combat_state = cs74_clear

    # Card 118 (Spike Control): decrement turns_remaining at end of turn
    _cs118 = player.combat_state or {}
    if _cs118.get("spike_control_turns_remaining", 0) > 0:
        cs118e = dict(_cs118)
        cs118e["spike_control_turns_remaining"] -= 1
        if cs118e["spike_control_turns_remaining"] <= 0:
            cs118e.pop("spike_control_turns_remaining", None)
        player.combat_state = cs118e

    # ── FASE FINALE step 2: discard excess cards (hand > 10 or 12 with Kanban/Platform Cache) ───
    # Addon 100 (Kanban Board): max hand size 12 instead of 10
    # Addon 112 (Asynchronous Callout): +1 extra card beyond hand limit
    _hand_limit_end = 12 if (_has_addon_end(player, 100) or _has_addon_end(player, 10)) else engine.MAX_HAND_SIZE
    if _has_addon_end(player, 112):
        _hand_limit_end += 1
    hand_cards = list(player.hand)
    excess = len(hand_cards) - _hand_limit_end
    discarded_card_ids: list = []
    if excess > 0:
        # Player must choose which to discard — for now auto-discard last drawn
        to_discard = hand_cards[-excess:]
        for hc_ex in to_discard:
            discarded_card_ids.append(hc_ex.action_card_id)
            game.action_discard = (game.action_discard or []) + [hc_ex.action_card_id]
            db.delete(hc_ex)

    # Addon 18 (Field History Tracking): track last discarded card at end of turn
    if discarded_card_ids:
        _cs18_end = dict(player.combat_state or {})
        _cs18_end["last_discarded_card_id"] = discarded_card_ids[-1]
        player.combat_state = _cs18_end

    # ── FASE FINALE step 3: "until end of turn" effects expire ───────────────
    # Each timed effect is cleared individually below (card 18, card 116, etc.).
    # No generic expiry system needed — all flags are cleared by their specific handlers.

    # ── FASE FINALE step 4: reset HP to max_hp (solo se vivo) ───────────────
    # I giocatori morti (hp=0) vengono rianimati all'inizio del LORO prossimo turno, non qui.
    if player.hp > 0:
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

    # Addon 91 (Free Trial): remove borrowed addon at end of turn; it stays in market (never removed)
    if player.combat_state and player.combat_state.get("free_trial_borrowed_pa_id"):
        from app.models.game import PlayerAddon as _PA91et
        _borrowed91 = db.get(_PA91et, player.combat_state["free_trial_borrowed_pa_id"])
        if _borrowed91:
            db.delete(_borrowed91)
        _cs91_new_et = dict(player.combat_state)
        _cs91_new_et.pop("free_trial_borrowed_pa_id", None)
        _cs91_new_et.pop("free_trial_borrowed_addon_id", None)
        player.combat_state = _cs91_new_et

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
        # Regola base: reset combat-per-turn tracker
        cs.pop("fought_this_turn", None)
        cs.pop("extra_combat_remaining", None)
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
                _hand_limit_wi = 12 if (_has_addon_end(player, 100) or _has_addon_end(player, 10)) else engine.MAX_HAND_SIZE
                if len(list(player.hand)) < _hand_limit_wi:
                    db.add(_PHCWI(player_id=player.id, action_card_id=wi_card_id))
        # Card 234 (Integration Pattern): clear boost if unused
        cs.pop("integration_pattern_boost", None)
        # Card 272 (ISV Ecosystem): clear per-turn cost-fix flag
        cs.pop("isv_ecosystem_active", None)
        # Addon 37 (Deployment Pipeline): clear per-turn extra card slot
        cs.pop("deployment_pipeline_extra_card", None)
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

    # Addon 150 (Wildcards): clear wildcards_active at end of turn
    if player.combat_state and player.combat_state.get("wildcards_active"):
        cs_wc = dict(player.combat_state)
        cs_wc.pop("wildcards_active", None)
        player.combat_state = cs_wc

    # Addon 66 (Trust Layer): clear protection flag at end of turn for ALL players
    for _p_tl in game.players:
        if (_p_tl.combat_state or {}).get("trust_layer_active"):
            _cs_tl = dict(_p_tl.combat_state)
            _cs_tl.pop("trust_layer_active", None)
            _p_tl.combat_state = _cs_tl

    # Addon 65 (Permission Set Group): clear locked_out for all players at end of turn (already immune,
    # but clearing is still needed for other players without addon 65)
    # (locked_out is cleared when the player's turn ends via the Anypoint MQ card effect)

    # Addon 183 (Ohana Spirit): if all active players are alive at end of turn, gain 1L
    if _has_addon_end(player, 183):
        if all(p.hp > 0 for p in game.players if not p.is_eliminated):
            player.licenze += 1

    # Addon 191 (404 Not Found): clear not_found_active flag at end of turn for ALL players
    for _p191 in game.players:
        if (_p191.combat_state or {}).get('not_found_active'):
            _cs191e = dict(_p191.combat_state)
            _cs191e.pop('not_found_active', None)
            _p191.combat_state = _cs191e

    # Addon 195 (Copy/Paste): clear copy_paste_active at end of turn (safety cleanup)
    if player.combat_state and player.combat_state.get('copy_paste_active'):
        _cs195e = dict(player.combat_state)
        _cs195e.pop('copy_paste_active', None)
        player.combat_state = _cs195e

    # Addon 125 (Aggregate Query): at end of turn, if played ≥2 cards, gain +1L
    if _has_addon_end(player, 125):
        _played125 = player.cards_played_this_turn
        if _played125 >= 2:
            player.licenze += 1

    # Addon 117 (Change Data Capture): if player lost ≥5L this turn, flag recovery for next turn
    if _has_addon_end(player, 117):
        _cs117e = dict(player.combat_state or {})
        _start117 = _cs117e.get("cdc_licenze_start", player.licenze)
        if _start117 - player.licenze >= 5:
            _cs117e["cdc_recovery_pending"] = True
        _cs117e.pop("cdc_licenze_start", None)
        player.combat_state = _cs117e

    player.cards_played_this_turn = 0

    # Clear death_penalty_pending if player skipped the choice (avoids frozen game)
    if (player.combat_state or {}).get("death_penalty_pending"):
        cs_dp = dict(player.combat_state)
        cs_dp.pop("death_penalty_pending", None)
        player.combat_state = cs_dp

    # Advance turn
    game.current_turn_index = (game.current_turn_index + 1) % len(game.turn_order)
    if game.current_turn_index == 0:
        game.turn_number += 1
    game.current_phase = TurnPhase.draw

    # Resurrezione: se il prossimo giocatore era morto (hp=0), rianimalo all'inizio del suo turno
    _next_player_id = game.turn_order[game.current_turn_index]
    _next_player = next((p for p in game.players if p.id == _next_player_id), None)
    if _next_player and _next_player.hp == 0:
        _next_player.hp = _next_player.max_hp
        for pa_rev in _next_player.addons:
            pa_rev.is_tapped = False
        # Pulisci anche il flag di penalità morte se non ancora risolto
        if (_next_player.combat_state or {}).get("death_penalty_pending"):
            cs_rev = dict(_next_player.combat_state)
            cs_rev.pop("death_penalty_pending", None)
            _next_player.combat_state = cs_rev

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.TURN_ENDED,
        "player_id": player.id,
        "next_player_id": game.turn_order[game.current_turn_index],
    })
    await _broadcast_state(game, db)
