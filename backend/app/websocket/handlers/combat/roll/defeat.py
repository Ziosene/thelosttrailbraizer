"""Boss defeat sequence handler."""
import random
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import _apply_elo, _broadcast_state
from app.models.game import GameSession, GameStatus, TurnPhase
from app.models.card import BossCard
from app.game import engine
from app.game import engine_role as _engine_role
from app.game.engine_addons import has_addon, get_addon_pa


async def _boss_defeat_sequence(player, game, db, boss) -> bool:
    """Handle boss defeat sequence (GDD §5.6).

    Returns True if the caller (_handle_roll_dice) should return immediately
    (boss revived, necromancer re-insert, instant_win, or normal victory).
    Returns False if combat continues (should not happen on defeat, but kept
    for safety; in practice callers always return after True).
    """
    player.bosses_defeated += 1

    # ── GDD §5.6 — Morte del Boss: 7-step ordered sequence ───────────────
    # Step 1: pre-reward boss abilities (revive, re-insert) — must fire BEFORE rewards
    defeated_effect = engine.apply_boss_ability(
        boss.id, "on_boss_defeated", cards_played=player.cards_played_this_turn
    )

    # Boss 25 (Heroku Dyno Zombie): one-shot revive — no rewards given
    if defeated_effect["boss_revive"] > 0:
        cs = dict(player.combat_state or {})
        if not cs.get("resurrection_used", False):
            cs["resurrection_used"] = True
            player.combat_state = cs
            player.current_boss_hp = defeated_effect["boss_revive"]
            db.commit()
            db.refresh(game)
            await manager.broadcast(game.code, {
                "type": "boss_revived",
                "player_id": player.id,
                "boss_id": boss.id,
                "new_hp": player.current_boss_hp,
            })
            await _broadcast_state(game, db)
            return True  # combat continues — boss revived, skip all reward steps

    # Boss 34 (Batch Apex Necromancer): first defeat re-inserts boss into deck — no rewards
    if defeated_effect["boss_revive_to_deck"] > 0:
        cs = dict(player.combat_state or {})
        if not cs.get("necromancer_resurrected", False):
            cs["necromancer_resurrected"] = True
            player.combat_state = cs
            game.boss_deck = (game.boss_deck or []) + [boss.id]
            player.is_in_combat = False
            player.current_boss_id = None
            player.current_boss_hp = None
            player.current_boss_source = None
            game.current_phase = TurnPhase.action
            db.commit()
            db.refresh(game)
            await manager.broadcast(game.code, {
                "type": "boss_revived",
                "player_id": player.id,
                "boss_id": boss.id,
                "necromancer": True,
            })
            await _broadcast_state(game, db)
            return True  # combat ended — boss re-inserted, no rewards

    # Card 75 (Triggered Send): thief gains 2L if they set the flag on this player
    _ts_thief_id = (player.combat_state or {}).get("triggered_send_thief_id")
    if _ts_thief_id:
        _ts_thief = next((p for p in game.players if p.id == _ts_thief_id), None)
        if _ts_thief:
            _ts_thief.licenze += 2
            await manager.send_to_player(_ts_thief.user_id, {"type": "triggered_send_reward", "licenze_gained": 2})
        _cs75 = dict(player.combat_state)
        _cs75.pop("triggered_send_thief_id", None)
        player.combat_state = _cs75

    # Step 2: award Licenze reward
    _licenze_reward = boss.reward_licenze
    player.licenze += _licenze_reward
    # Card 262 (World Tour Event): bonus +2L on boss defeat if event active; first combatant +1L extra
    if (player.combat_state or {}).get("world_tour_event_active"):
        player.licenze += 2
        if (player.combat_state or {}).get("world_tour_event_first_bonus"):
            player.licenze += 1
            _cs_wte = dict(player.combat_state)
            _cs_wte.pop("world_tour_event_first_bonus", None)
            player.combat_state = _cs_wte

    # Boss 53 (Einstein Discovery Oracle): check prediction accuracy on boss defeat
    _oracle_pred = (player.combat_state or {}).get("oracle_predicted_rounds")
    if _oracle_pred is not None:
        _actual_rounds = player.combat_round  # 0-indexed; equals total rounds completed
        if abs(_actual_rounds - _oracle_pred) <= 1:
            player.licenze += 3
        else:
            player.licenze = max(0, player.licenze - 2)
        _cs_oracle = dict(player.combat_state)
        _cs_oracle.pop("oracle_predicted_rounds", None)
        player.combat_state = _cs_oracle

    # Card 273 (Trailhead Quest): +5L if no cards played this turn
    if (player.combat_state or {}).get("trailhead_quest_active") and player.cards_played_this_turn == 0:
        player.licenze += 5
        _cs_tq = dict(player.combat_state)
        _cs_tq.pop("trailhead_quest_active", None)
        _cs_tq.pop("trailhead_quest_cards_played", None)
        player.combat_state = _cs_tq
    # Card 285 (Trailhead Superbadge): track consecutive boss defeats; at 3 → +10L +1cert
    if (player.combat_state or {}).get("superbadge_tracking"):
        _cs_sb = dict(player.combat_state)
        _cs_sb["superbadge_defeats"] = _cs_sb.get("superbadge_defeats", 0) + 1
        if _cs_sb["superbadge_defeats"] >= 3:
            player.licenze += 10
            player.certificazioni += 1
            _cs_sb.pop("superbadge_tracking", None)
            _cs_sb.pop("superbadge_defeats", None)
        player.combat_state = _cs_sb

    # Card 296 (Customer Success): watchers with flag get +1L
    for _watcher_cs in game.players:
        if _watcher_cs.id != player.id and (_watcher_cs.combat_state or {}).get("customer_success_active"):
            _watcher_cs.licenze += 1
            _wc_cs = dict(_watcher_cs.combat_state)
            _wc_cs.pop("customer_success_active", None)
            _watcher_cs.combat_state = _wc_cs
    # Card 297 (Trailblazer Spirit): +3L if this boss not previously defeated
    _boss_graveyard = game.boss_graveyard or []
    _trophies_all = []
    for _p2 in game.players:
        _trophies_all.extend(_p2.trophies or [])
    _boss_new = boss.id not in _boss_graveyard and boss.id not in _trophies_all
    if (player.combat_state or {}).get("trailblazer_spirit_active") and _boss_new:
        player.licenze += 3
        _cs_ts = dict(player.combat_state)
        _cs_ts.pop("trailblazer_spirit_active", None)
        player.combat_state = _cs_ts
    # Card 285 (Trailhead Superbadge): track consecutive boss defeats; at 3 → +1cert+10L
    if (player.combat_state or {}).get("superbadge_tracking"):
        _cs_sb = dict(player.combat_state)
        _cs_sb["consecutive_boss_defeats_alive"] = _cs_sb.get("consecutive_boss_defeats_alive", 0) + 1
        if _cs_sb["consecutive_boss_defeats_alive"] >= 3:
            player.certificazioni += 1
            player.licenze += 10
            _cs_sb.pop("superbadge_tracking", None)
            _cs_sb.pop("consecutive_boss_defeats_alive", None)
        player.combat_state = _cs_sb

    # Addon 143 (Double or Nothing): after boss defeat, roll: ≥6 → double L; ≤3 → lose earned L
    if has_addon(player, 143):
        cs143 = player.combat_state or {}
        if not cs143.get("double_or_nothing_used"):
            _don_roll = engine.roll_d10()
            cs143_new = dict(cs143)
            cs143_new["double_or_nothing_used"] = True
            player.combat_state = cs143_new
            await manager.broadcast(game.code, {
                "type": "double_or_nothing_roll",
                "player_id": player.id,
                "roll": _don_roll,
            })
            if _don_roll >= 6:
                player.licenze += _licenze_reward  # double (add same amount again)
            elif _don_roll <= 3:
                player.licenze = max(0, player.licenze - _licenze_reward)  # lose earned L

    # Addon 145 (Risk Matrix): if risk_matrix_reward flag set, gain L equal to boss base HP
    if has_addon(player, 145) and (player.combat_state or {}).get("risk_matrix_reward"):
        _boss_hp_start145 = boss.hp  # boss.hp is the base/original HP of the BossCard
        player.licenze += _boss_hp_start145
        cs145d = dict(player.combat_state)
        del cs145d["risk_matrix_reward"]
        player.combat_state = cs145d

    # Step 3: award Certification (if cert boss)
    _licenze_before_cert = player.licenze  # unused now but kept for reference
    if boss.has_certification:
        player.certificazioni += 1

        # Addon 151 (Certification Path): first cert earned doubles score (flag-based)
        if has_addon(player, 151):
            cs151d = player.combat_state or {}
            if cs151d.get("cert_path_double_pending"):
                cs151d_new = dict(cs151d)
                cs151d_new.pop("cert_path_double_pending", None)
                cs151d_new["cert_path_score_bonus"] = True
                player.combat_state = cs151d_new

        # Addon 152 (Superbadge Grind): 3 consecutive cert boss defeats → extra cert
        if has_addon(player, 152):
            cs152 = dict(player.combat_state or {})
            cs152["superbadge_grind_streak"] = cs152.get("superbadge_grind_streak", 0) + 1
            if cs152["superbadge_grind_streak"] >= 3:
                player.certificazioni += 1
                cs152["superbadge_grind_streak"] = 0
            player.combat_state = cs152

        # Addon 185 (Customer Success): when opponent gets first cert, gain 1L
        if player.certificazioni == 1:  # just got first cert
            for _p185b in game.players:
                if _p185b.id != player.id and has_addon(_p185b, 185):
                    _p185b.licenze += 1

        # Addon 149 (Comeback Mechanic): when any opponent reaches 4 certs, gain 3L
        if player.certificazioni >= 4:
            for _p149 in game.players:
                if _p149.id != player.id and has_addon(_p149, 149):
                    _p149.licenze += 3

        # Addon 160 (Graduation Day): reaching exactly 4 certs → +10L and +2 dice next turn
        if has_addon(player, 160) and player.certificazioni == 4:
            cs160 = dict(player.combat_state or {})
            if not cs160.get("graduation_day_triggered"):
                cs160["graduation_day_triggered"] = True
                cs160["graduation_day_dice_bonus"] = 2
                player.licenze += 10
                player.combat_state = cs160
                await manager.broadcast(game.code, {
                    "type": "graduation_day_triggered",
                    "player_id": player.id,
                })
    else:
        # Non-cert boss resets Addon 152 (Superbadge Grind) streak
        if has_addon(player, 152):
            cs152r = dict(player.combat_state or {})
            cs152r["superbadge_grind_streak"] = 0
            player.combat_state = cs152r

    # Addon 15 (Trailhead Superbadge): +2L when defeating a boss that has a certification
    if has_addon(player, 15) and boss.has_certification:
        player.licenze += 2

    # Addon 7 (Flow Automation): +2L if no damage taken this combat
    if has_addon(player, 7) and (player.combat_state or {}).get("no_damage_this_combat"):
        player.licenze += 2
        _cs7d = dict(player.combat_state)
        _cs7d.pop("no_damage_this_combat", None)
        player.combat_state = _cs7d

    # Step 4: post-reward boss abilities
    # Boss 19 (Dreamforce Hydra): +1 bonus certification on kill
    if defeated_effect["bonus_certification"] > 0:
        player.certificazioni += defeated_effect["bonus_certification"]
    # Boss 20 (Corrupted Trailblazer): +3 licenze if no cards played this turn
    if defeated_effect["bonus_licenze"] > 0:
        player.licenze += defeated_effect["bonus_licenze"]
    # Boss 26 (CPQ Configuration Chaos): next addon purchase costs +3 licenze
    if defeated_effect["next_addon_cost_penalty"] > 0:
        player.pending_addon_cost_penalty = (
            (player.pending_addon_cost_penalty or 0) + defeated_effect["next_addon_cost_penalty"]
        )
    # Boss 99 (CTA Titan): every player who played an action card this combat gains N licenze
    if defeated_effect["bonus_licenze_to_helpers"] > 0:
        for p_help in game.players:
            if p_help.id != player.id and p_help.cards_played_this_turn > 0:
                p_help.licenze += defeated_effect["bonus_licenze_to_helpers"]
    # Boss 100 (Lost Trailblazer Omega): instant win regardless of cert count
    if defeated_effect["instant_win"]:
        player.certificazioni += 5  # Boss 100 reward: 5 certifications
        game.status = GameStatus.finished
        game.winner_id = player.id
        from datetime import datetime, timezone
        game.finished_at = datetime.now(timezone.utc)
        _apply_elo(game, player.id, db)
        db.commit()
        await manager.broadcast(game.code, {"type": ServerEvent.GAME_OVER, "winner_id": player.id})
        await _broadcast_state(game, db)
        return True
    # Boss 31 (AppExchange Parasite): unlock locked addon (untap it)
    if defeated_effect["unlock_locked_addon"] and player.combat_state:
        locked_pa_id = player.combat_state.get("locked_addon_id")
        if locked_pa_id:
            from app.models.game import PlayerAddon as _PA
            pa_unlock = db.get(_PA, locked_pa_id)
            if pa_unlock and pa_unlock.player_id == player.id:
                pa_unlock.is_tapped = False

    # Boss 91 (List View Usurper): clear hand_hidden_in_combat on boss defeat
    if player.combat_state and player.combat_state.get("hand_hidden_in_combat"):
        cs = dict(player.combat_state)
        cs.pop("hand_hidden_in_combat", None)
        player.combat_state = cs
    # Boss 82 (Customer 360 Gorgon): clear petrified cards on defeat
    if player.combat_state and player.combat_state.get("petrified_card_ids"):
        cs = dict(player.combat_state)
        cs.pop("petrified_card_ids", None)
        player.combat_state = cs
    # Addon 81 (Boss Vulnerability Scan): clear per-combat used flag on boss defeat
    if player.combat_state and player.combat_state.get("vulnerability_scan_used"):
        cs = dict(player.combat_state)
        cs.pop("vulnerability_scan_used", None)
        player.combat_state = cs
    # Card 139 (Prospect Lifecycle): boss defeat lifts the addon purchase block
    if player.combat_state and player.combat_state.get("addons_blocked_until_boss_defeat"):
        cs = dict(player.combat_state)
        cs.pop("addons_blocked_until_boss_defeat", None)
        player.combat_state = cs
    # Addon 141 (Calculated Risk): clear flag on boss defeat
    if player.combat_state and player.combat_state.get("calculated_risk_active"):
        cs = dict(player.combat_state)
        cs.pop("calculated_risk_active", None)
        player.combat_state = cs
    # Boss 55 / Boss 74: also apply shadow copy's on_boss_defeated effects
    copy_boss_id = getattr(player, "_copy_boss_id_for_defeat", None)
    if copy_boss_id:
        copy_def = engine.apply_boss_ability(
            copy_boss_id, "on_boss_defeated",
            cards_played=player.cards_played_this_turn,
        )
        if copy_def["bonus_certification"] > 0:
            player.certificazioni += copy_def["bonus_certification"]
        if copy_def["bonus_licenze"] > 0:
            player.licenze += copy_def["bonus_licenze"]
        if copy_def["next_addon_cost_penalty"] > 0:
            player.pending_addon_cost_penalty = (
                (player.pending_addon_cost_penalty or 0) + copy_def["next_addon_cost_penalty"]
            )
    # Boss 100 (Omega): also apply the last legendary boss's on_boss_defeated effects
    if engine.boss_is_omega(boss.id) and game.last_defeated_legendary_boss_id:
        omega_def = engine.apply_boss_ability(
            game.last_defeated_legendary_boss_id, "on_boss_defeated",
            cards_played=player.cards_played_this_turn,
        )
        if omega_def["bonus_certification"] > 0:
            player.certificazioni += omega_def["bonus_certification"]
        if omega_def["bonus_licenze"] > 0:
            player.licenze += omega_def["bonus_licenze"]

    # Addon 97 (Definition of Done): defeat boss at max HP → +2L
    if has_addon(player, 97) and player.hp >= player.max_hp:
        player.licenze += 2

    # Addon 128 (Cross-Object Formula): each boss defeated gives +1L extra
    if has_addon(player, 128):
        player.licenze += 1

    # Addon 137 (ISV Partner): if player owns ≥2 addons of same type, gain +1L on boss defeat
    if has_addon(player, 137):
        _active137 = sum(1 for _pa137 in player.addons if _pa137.card and _pa137.card.addon_type.value == "Attivo")
        _passive137 = sum(1 for _pa137 in player.addons if _pa137.card and _pa137.card.addon_type.value == "Passivo")
        if _active137 >= 2 or _passive137 >= 2:
            player.licenze += 1

    # Addon 161 (Junior Hustle): Junior players gain +2L on each boss defeat
    if has_addon(player, 161):
        from app.models.game import Seniority as _Sen161
        _is_junior161 = player.seniority == _Sen161.junior
        if _is_junior161:
            player.licenze += 2

    # Addon 163 (Mentorship Program): if player to the left has lower seniority, gain +1L on their boss defeat
    # Check all players with addon 163 whose left neighbor (by turn_order) is the winning player
    _turn_order163 = list(game.turn_order or [])
    for _p163 in game.players:
        if has_addon(_p163, 163) and _p163.id != player.id:
            if _turn_order163:
                try:
                    _p163_idx = _turn_order163.index(_p163.id)
                    _left163_idx = (_p163_idx - 1) % len(_turn_order163)
                    _left163_pid = _turn_order163[_left163_idx]
                    if _left163_pid == player.id:
                        # Check seniority: left neighbor should have lower seniority
                        from app.models.game import Seniority as _Sen163
                        _SENIORITY_ORDER163 = [
                            _Sen163.junior, _Sen163.experienced,
                            _Sen163.senior, _Sen163.evangelist,
                        ]
                        try:
                            _p163_seniority_rank = _SENIORITY_ORDER163.index(_p163.seniority)
                            _left_seniority_rank = _SENIORITY_ORDER163.index(player.seniority)
                            if _left_seniority_rank < _p163_seniority_rank:
                                _p163.licenze += 1
                        except (ValueError, TypeError):
                            pass
                except (ValueError, TypeError):
                    pass

    # Addon 167 (Evangelist Aura): on boss defeat, left and right neighbors get +1 dice bonus next combat
    if has_addon(player, 167):
        _n_players167 = len(game.turn_order or [])
        if _n_players167 > 1 and game.turn_order:
            try:
                _p167_idx = game.turn_order.index(player.id)
                _left167_pid = game.turn_order[(_p167_idx - 1) % _n_players167]
                _right167_pid = game.turn_order[(_p167_idx + 1) % _n_players167]
                for _p167 in game.players:
                    if _p167.id in (_left167_pid, _right167_pid):
                        cs167 = dict(_p167.combat_state or {})
                        cs167["evangelist_aura_dice_bonus"] = cs167.get("evangelist_aura_dice_bonus", 0) + 1
                        _p167.combat_state = cs167
            except (ValueError, TypeError):
                pass

    # Addon 169 (Performance Review): track boss defeats count in combat_state
    _cs_bdc169 = dict(player.combat_state or {})
    _cs_bdc169["boss_defeats_count"] = _cs_bdc169.get("boss_defeats_count", 0) + 1
    player.combat_state = _cs_bdc169

    # Addon 181 (Trailblazer Spirit): first player to defeat a specific boss gains +3L
    _boss_id181 = player.current_boss_id  # capture before clearing
    _gs181 = dict(game.game_state or {})
    _first_defeats181 = _gs181.get('first_defeated_boss_ids', [])
    if has_addon(player, 181):
        if _boss_id181 and _boss_id181 not in _first_defeats181:
            player.licenze += 3
    # Always update the set (even if player doesn't have addon 181)
    if _boss_id181 and _boss_id181 not in _first_defeats181:
        _first_defeats181.append(_boss_id181)
        _gs181['first_defeated_boss_ids'] = _first_defeats181
        game.game_state = _gs181

    # Addon 185 (Customer Success): when opponent gets first boss defeat, gain 1L
    _bdc185 = (player.combat_state or {}).get('boss_defeats_count', 0)
    if _bdc185 == 1:  # this is their first boss defeat
        for _p185 in game.players:
            if _p185.id != player.id and has_addon(_p185, 185):
                _p185.licenze += 1

    # Addon 188 (Trailhead Badge Hunter): every 5 boss defeats gain 1 scoring cert
    if has_addon(player, 188):
        _bdc188 = (player.combat_state or {}).get('boss_defeats_count', 0)
        if _bdc188 > 0 and _bdc188 % 5 == 0:
            cs188 = dict(player.combat_state)
            cs188['badge_hunter_score_certs'] = cs188.get('badge_hunter_score_certs', 0) + 1
            player.combat_state = cs188

    # Role passive: Sales Cloud Consultant +1L / B2C Commerce Dev extra card / Pardot Consultant watchers
    _role_boss_reward = _engine_role.on_boss_defeated(player)
    if _role_boss_reward["extra_licenze"]:
        player.licenze += _role_boss_reward["extra_licenze"]
    if _role_boss_reward["extra_cards"]:
        from app.models.game import PlayerHandCard as _PHC_role_b2c
        for _ in range(_role_boss_reward["extra_cards"]):
            if game.action_deck:
                db.add(_PHC_role_b2c(player_id=player.id, action_card_id=game.action_deck.pop(0)))
    # Pardot Consultant: other players watching gain 1L
    for _other_pardot in game.players:
        if _other_pardot.id != player.id:
            _pardot_reward = _engine_role.on_opponent_boss_defeated(_other_pardot)
            if _pardot_reward["extra_licenze"]:
                _other_pardot.licenze += _pardot_reward["extra_licenze"]

    # Addon 126 (Territory Management): other players watching this player defeat a boss gain 1L
    for _p126 in game.players:
        if _p126.id != player.id:
            _terr126 = (_p126.combat_state or {}).get("territory_player_id")
            if _terr126 == player.id:
                _p126.licenze += 1

    # Addon 98 (Acceptance Criteria): player chooses — licenze reward OR 2 action cards.
    # Revoke the licenze already granted, store pending reward, send choice event.
    if has_addon(player, 98):
        _pending98 = boss.reward_licenze
        player.licenze = max(0, player.licenze - _pending98)
        _cs98 = dict(player.combat_state or {})
        _cs98["acceptance_criteria_pending_reward"] = _pending98
        player.combat_state = _cs98
        await manager.send_to_player(player.user_id, {
            "type": "acceptance_criteria_choice_required",
            "licenze_option": _pending98,
            "cards_option": 2,
        })

    # Addon 105 (Epic Feature): every 3 consecutive boss defeats without dying → +1 cert
    if has_addon(player, 105):
        _cs105 = dict(player.combat_state or {})
        _cs105["epic_feature_streak"] = _cs105.get("epic_feature_streak", 0) + 1
        if _cs105["epic_feature_streak"] >= 3:
            player.certificazioni += 1
            _cs105["epic_feature_streak"] = 0
        player.combat_state = _cs105

    # Addon 106 (Story Points): each boss defeated gives +1L per boss original HP
    if has_addon(player, 106):
        player.licenze += boss.hp  # boss.hp is the original/base HP of the BossCard

    # Addon 42 (Revenue Cloud Optimizer): +2L extra on boss defeat if player has ≥20 licenze
    if has_addon(player, 42) and player.licenze >= 20:
        player.licenze += 2

    # Addon 75 (Cascade Update): untap all tapped active addons on boss defeat
    if has_addon(player, 75):
        for _pa75 in player.addons:
            if _pa75.is_tapped:
                _pa75.is_tapped = False

    # Addon 76 (Rollup Summary): track boss defeats for future ELO bonus
    if has_addon(player, 76):
        _cs76 = dict(player.combat_state or {})
        _cs76["rollup_boss_defeats"] = _cs76.get("rollup_boss_defeats", 0) + 1
        player.combat_state = _cs76

    # Addon 44 (Loyalty Points Engine): other players with this addon gain +1L on any boss defeat
    for _other44 in game.players:
        if _other44.id != player.id and has_addon(_other44, 44):
            _other44.licenze += 1

    # Addon 52 (Scratch Org): trim excess cards at end of combat (boss defeated)
    if has_addon(player, 52):
        db.flush()
        hand52 = list(player.hand)
        while len(hand52) > engine.MAX_HAND_SIZE:
            excess52 = hand52.pop()
            game.action_discard = (game.action_discard or []) + [excess52.action_card_id]
            db.delete(excess52)

    # Track last defeated boss for mimic (55) / shape shifter (74) / omega (100) routing
    game.last_defeated_boss_id = boss.id
    if boss.has_certification:
        game.last_defeated_legendary_boss_id = boss.id

    # Step 5 & 6: Trophy (cert boss) or Cimitero Boss (non-cert)
    source = player.current_boss_source
    if boss.has_certification:
        # Cert boss becomes a trophy in the player's possession.
        # Can be stolen or destroyed by other players via card effects.
        # Only goes to boss_graveyard if destroyed from a player's trophies.
        player.trophies = (player.trophies or []) + [boss.id]
    else:
        # Non-cert bosses go to the shared graveyard
        game.boss_graveyard = (game.boss_graveyard or []) + [boss.id]

    # Step 7: Refill market slot if boss was taken from market
    if source == "market_1":
        game.boss_market_1 = game.boss_deck.pop(0) if game.boss_deck else None
    elif source == "market_2":
        game.boss_market_2 = game.boss_deck.pop(0) if game.boss_deck else None

    player.is_in_combat = False
    player.current_boss_id = None
    player.current_boss_hp = None
    player.current_boss_source = None
    game.current_phase = TurnPhase.action

    if engine.check_victory(player.certificazioni):
        game.status = GameStatus.finished
        game.winner_id = player.id
        from datetime import datetime, timezone
        game.finished_at = datetime.now(timezone.utc)
        _apply_elo(game, player.id, db)
        db.commit()
        await manager.broadcast(game.code, {
            "type": ServerEvent.GAME_OVER,
            "winner_id": player.id,
        })
        await _broadcast_state(game, db)
        return True

    return False
