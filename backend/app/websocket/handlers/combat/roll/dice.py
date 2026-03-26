"""Main roll dice handler."""
import random
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state, _send_hand_state,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.models.card import ActionCard, BossCard
from app.game import engine
from app.game import engine_role as _engine_role
from app.game.engine_addons import has_addon
from app.websocket.reaction_manager import open_reaction_window
from app.websocket.handlers.combat.roll.defeat import _boss_defeat_sequence
from app.websocket.handlers.combat.roll.death import _player_death_sequence


async def _handle_roll_dice(game: GameSession, user_id: int, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.combat:
        await _error(game.code, user_id, "Not in combat phase")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player) or not player.is_in_combat:
        await _error(game.code, user_id, "Not your combat")
        return

    boss = db.get(BossCard, player.current_boss_id)
    if not boss:
        await _error(game.code, user_id, "Boss not found")
        return

    # Addon 24 (Einstein Next Best Action): skip this round — neutral
    if (player.combat_state or {}).get("skip_next_round_neutral"):
        cs_nba = dict(player.combat_state)
        cs_nba.pop("skip_next_round_neutral", None)
        player.combat_state = cs_nba
        player.combat_round = (player.combat_round or 0) + 1
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {"type": "round_skipped", "player_id": player.id, "reason": "einstein_nba"})
        await _broadcast_state(game, db)
        return

    # Addon 142 (All or Nothing): skip this round — gain +4 to next roll
    if (player.combat_state or {}).get("all_or_nothing_pending"):
        cs142_skip = dict(player.combat_state)
        del cs142_skip["all_or_nothing_pending"]
        cs142_skip["all_or_nothing_bonus"] = 4
        player.combat_state = cs142_skip
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {"type": "all_or_nothing_skipped", "player_id": player.id})
        await _broadcast_state(game, db)
        return

    # combat_round is still 0-indexed here; current roll = round N+1
    current_round = (player.combat_round or 0) + 1

    # ── Boss 55 (mimic) / Boss 74 (shape shifter): copy last defeated boss ───
    copy_boss_id: int | None = None
    if game.last_defeated_boss_id:
        if engine.boss_is_mimic(boss.id):
            copy_boss_id = game.last_defeated_boss_id
        elif engine.boss_is_shape_shifter(boss.id) and current_round % 2 == 0:
            copy_boss_id = game.last_defeated_boss_id

    # ── on_round_start effects (before rolling) ──────────────────────────
    # Card 10 (SOQL Blast) can disable the boss ability for N rounds.
    _boss_ability_disabled = (
        (player.combat_state or {}).get("boss_ability_disabled_until_round", 0) >= current_round
    )
    round_start = engine.apply_boss_ability(
        boss.id, "on_round_start" if not _boss_ability_disabled else "_disabled",
        combat_round=current_round,
        cards_played=player.cards_played_this_turn,
    )

    # Boss 18 (Tech Debt Lich): drain 1 Licenza every round
    # Addon 46 (Order Management System): immune to boss licenze drain
    # Addon 162 (Senior Privilege): Senior/Evangelist can ignore 1 negative boss effect per game
    if round_start["licenza_drain"] > 0 and not has_addon(player, 46):
        _cs162_drain = player.combat_state or {}
        _skip162_drain = False
        if has_addon(player, 162):
            from app.models.game import Seniority as _Sen162d
            if player.seniority in (_Sen162d.senior, _Sen162d.evangelist):
                if not _cs162_drain.get("senior_privilege_used"):
                    _cs162_new_drain = dict(_cs162_drain)
                    _cs162_new_drain["senior_privilege_used"] = True
                    player.combat_state = _cs162_new_drain
                    _skip162_drain = True
        if not _skip162_drain:
            player.licenze = max(0, player.licenze - round_start["licenza_drain"])

    # Boss 13 (Flow Builder Gone Rogue): discard 1 card or take 1 HP
    if round_start["force_discard_or_damage"] > 0:
        hand_cards = list(player.hand)
        if hand_cards:
            await manager.send_to_player(game.code, player.user_id, {
                "type": "boss13_discard_required",
                "player_id": player.id,
                "options": [{"hand_card_id": hc.id, "action_card_id": hc.action_card_id} for hc in hand_cards],
                "or_take_hp": round_start["force_discard_or_damage"],
            })
            _b13_resp = await open_reaction_window(game.code, player.id, timeout=20.0)
            if _b13_resp and _b13_resp.get("action") == "discard":
                _b13_hcid = _b13_resp.get("hand_card_id")
                from app.models.game import PlayerHandCard as _PHC13
                _b13_hc = db.get(_PHC13, _b13_hcid)
                if _b13_hc and _b13_hc.player_id == player.id:
                    game.action_discard = (game.action_discard or []) + [_b13_hc.action_card_id]
                    db.delete(_b13_hc)
                else:
                    player.hp = max(0, player.hp - round_start["force_discard_or_damage"])
            else:
                # timeout or "take_hp" response
                player.hp = max(0, player.hp - round_start["force_discard_or_damage"])
        else:
            player.hp = max(0, player.hp - round_start["force_discard_or_damage"])

    # Boss 42 (Revenue Cloud Devourer): drain 1 licenza; if 0 licenze → drain 1 HP
    # Addon 46 (Order Management System): immune to boss licenze drain (HP drain still applies)
    if round_start["licenza_or_hp_drain"] > 0:
        n = round_start["licenza_or_hp_drain"]
        if has_addon(player, 46):
            pass  # immune to boss licenze drain
        elif player.licenze >= n:
            player.licenze -= n
        else:
            player.hp = max(0, player.hp - n)

    # Boss 46 (Process Builder Abomination): involuntarily discard 1 extra card every round
    if round_start["force_extra_card_discard"]:
        hand_cards_fe = list(player.hand)
        if hand_cards_fe:
            hc_fe = random.choice(hand_cards_fe)
            game.action_discard = (game.action_discard or []) + [hc_fe.action_card_id]
            db.delete(hc_fe)

    # Boss 35 (Platform Event Gremlin): chaos roll — extra d10; on 1 → random penalty
    if round_start["bonus_chaos_roll"]:
        chaos_roll = engine.roll_d10()
        if chaos_roll == 1:
            chaos_penalty = random.choice(["card", "hp", "licenza_opponent"])
            if chaos_penalty == "card":
                hand_cards_ch = list(player.hand)
                if hand_cards_ch:
                    hc_ch = random.choice(hand_cards_ch)
                    game.action_discard = (game.action_discard or []) + [hc_ch.action_card_id]
                    db.delete(hc_ch)
            elif chaos_penalty == "hp":
                player.hp = max(0, player.hp - 1)
            else:
                opponents_ch = [p for p in game.players if p.id != player.id]
                if opponents_ch:
                    random.choice(opponents_ch).licenze += 2

    # Boss 53 (Einstein Discovery Oracle): boss predicts hit/miss; correct → double round effect
    prediction = None
    if round_start["makes_prediction"]:
        prediction = random.choice(["hit", "miss"])
        await manager.broadcast(game.code, {
            "type": "boss_prediction",
            "player_id": player.id,
            "prediction": prediction,
        })

    # Boss 93 (Subscription Management Tormentor): lose 1L/round; if at 0L take 1 HP instead
    # Addon 46 (Order Management System): immune to boss licenze drain
    if round_start["subscription_drain"] > 0:
        if has_addon(player, 46):
            pass  # immune to boss licenze drain
        elif player.licenze > 0:
            player.licenze -= 1
        else:
            player.hp = max(0, player.hp - 1)

    # Boss 100 (Omega): apply last legendary boss's on_round_start effects in parallel
    # Addon 46 (Order Management System): immune to boss licenze drain
    if engine.boss_is_omega(boss.id) and game.last_defeated_legendary_boss_id:
        omega_rs = engine.apply_boss_ability(
            game.last_defeated_legendary_boss_id, "on_round_start",
            combat_round=current_round,
            cards_played=player.cards_played_this_turn,
        )
        if omega_rs["licenza_drain"] > 0 and not has_addon(player, 46):
            player.licenze = max(0, player.licenze - omega_rs["licenza_drain"])
        if omega_rs["licenza_or_hp_drain"] > 0:
            n = omega_rs["licenza_or_hp_drain"]
            if has_addon(player, 46):
                pass  # immune to boss licenze drain
            elif player.licenze >= n:
                player.licenze -= n
            else:
                player.hp = max(0, player.hp - n)
        if omega_rs["subscription_drain"] > 0:
            if has_addon(player, 46):
                pass  # immune to boss licenze drain
            elif player.licenze > 0:
                player.licenze -= 1
            else:
                player.hp = max(0, player.hp - 1)

    # Boss 55 / Boss 74: apply shadow copy's on_round_start effects
    if copy_boss_id:
        copy_rs = engine.apply_boss_ability(
            copy_boss_id, "on_round_start",
            combat_round=current_round,
            cards_played=player.cards_played_this_turn,
        )
        # Addon 46 (Order Management System): immune to boss licenze drain
        if copy_rs["licenza_drain"] > 0 and not has_addon(player, 46):
            player.licenze = max(0, player.licenze - copy_rs["licenza_drain"])
        if copy_rs["licenza_or_hp_drain"] > 0:
            n = copy_rs["licenza_or_hp_drain"]
            if has_addon(player, 46):
                pass  # immune
            elif player.licenze >= n:
                player.licenze -= n
            else:
                player.hp = max(0, player.hp - n)
        if copy_rs["force_discard_or_damage"] > 0:
            hcl = list(player.hand)
            if hcl:
                hc_cp = random.choice(hcl)
                game.action_discard = (game.action_discard or []) + [hc_cp.action_card_id]
                db.delete(hc_cp)
            else:
                player.hp = max(0, player.hp - copy_rs["force_discard_or_damage"])
        if copy_rs["subscription_drain"] > 0:
            if has_addon(player, 46):
                pass  # immune
            elif player.licenze > 0:
                player.licenze -= 1
            else:
                player.hp = max(0, player.hp - 1)

    # Boss 45 (Agentforce Rebellion): each owned addon costs 1L/round; can't pay → addon tapped
    # Addon 46 (Order Management System): immune to boss licenze drain
    threshold_bonus = 0
    if round_start["addon_licenze_drain"] and not has_addon(player, 46):
        addons_45 = list(player.addons)
        tapped_by_drain = []
        for pa_45 in addons_45:
            if player.licenze >= 1:
                player.licenze -= 1
            else:
                pa_45.is_tapped = True
                tapped_by_drain.append(pa_45.addon_id)
        if tapped_by_drain:
            await manager.broadcast(game.code, {
                "type": "addons_tapped_by_boss",
                "player_id": player.id,
                "addon_ids": tapped_by_drain,
                "reason": "agentforce_rebellion",
            })

    # Boss 65 (Einstein Vision Stalker): predict above/below 5 each round; correct → -1L
    if round_start["predicts_roll_direction"]:
        _stalker_pred = "above" if random.randint(0, 1) == 0 else "below"
        cs = dict(player.combat_state or {})
        cs["stalker_prediction"] = _stalker_pred
        player.combat_state = cs
        await manager.broadcast(game.code, {
            "type": "stalker_prediction",
            "player_id": player.id,
            "prediction": _stalker_pred,
        })

    # Boss 58 (Prompt Builder Djinn): roll d4 each round → set random threshold
    if round_start["randomize_threshold"]:
        _d4 = random.randint(1, 4)
        _djinn_thresholds = {1: 2, 2: 4, 3: 6, 4: 8}
        _djinn_t = _djinn_thresholds[_d4]
        cs = dict(player.combat_state or {})
        cs["djinn_threshold"] = _djinn_t
        player.combat_state = cs
        await manager.broadcast(game.code, {
            "type": "djinn_threshold_set",
            "player_id": player.id,
            "threshold": _djinn_t,
            "roll": _d4,
        })

    # Boss 63 (Loyalty Management Trickster): player chooses to accept (+1L, threshold +1) or reject
    if round_start["deal_offer"]:
        await manager.send_to_player(game.code, player.user_id, {
            "type": "boss63_deal_offer",
            "player_id": player.id,
            "licenze_gain": 1,
            "threshold_penalty": 1,
        })
        _b63_resp = await open_reaction_window(game.code, player.id, timeout=15.0)
        if _b63_resp and _b63_resp.get("action") == "accept":
            player.licenze += 1
            threshold_bonus += 1
            await manager.broadcast(game.code, {"type": "boss63_deal_accepted", "player_id": player.id})
        else:
            await manager.broadcast(game.code, {"type": "boss63_deal_rejected", "player_id": player.id})

    # Boss 83 (Account Engagement Siren): player chooses to accept (skip roll, +2L, boss +1HP) or fight
    if round_start["siren_deal"]:
        await manager.send_to_player(game.code, player.user_id, {
            "type": "boss83_siren_deal",
            "player_id": player.id,
            "licenze_gain": 2,
            "boss_hp_cost": 1,
        })
        _b83_resp = await open_reaction_window(game.code, player.id, timeout=15.0)
        if _b83_resp and _b83_resp.get("action") == "accept":
            player.licenze += 2
            player.current_boss_hp = (player.current_boss_hp or 0) + 1
            await manager.broadcast(game.code, {"type": "boss83_siren_accepted", "player_id": player.id})
            db.commit(); db.refresh(game)
            await _broadcast_state(game, db)
            return  # skip roll this round
        else:
            await manager.broadcast(game.code, {"type": "boss83_siren_rejected", "player_id": player.id})

    # Boss 33 (Experience Cloud Illusion): player must have declared a card before rolling
    if engine.boss_card_declared_before_roll(boss.id):
        if not (player.combat_state or {}).get("declared_card_id"):
            await _error(game.code, user_id, "You must declare a card (declare_card) before rolling against this boss")
            return

    # ── Boss expires check ────────────────────────────────────────────────
    # Boss 48 (Scratch Org Mirage) / Boss 90 (Quick Action Marauder): auto-expire
    expire_rounds = engine.boss_expires_after_rounds(boss.id)
    if expire_rounds is not None and current_round > expire_rounds:
        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        player.current_boss_source = None
        game.current_phase = TurnPhase.action
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": ServerEvent.COMBAT_ENDED,
            "player_id": player.id,
            "boss_escaped": True,
        })
        await _broadcast_state(game, db)
        return

    # ── Roll dice ─────────────────────────────────────────────────────────
    # Boss 1 (worst_of_2) / Boss 39 (second_of_2 — keep only the second roll)
    roll_mode = engine.boss_roll_mode(boss.id, current_round)

    # Addon 32 (Apex Batch Processor): +2 to roll if last round was a hit
    _bp_bonus = 0
    if (player.combat_state or {}).get("batch_processor_bonus"):
        _bp_bonus = 2
        cs_bp = dict(player.combat_state)
        cs_bp.pop("batch_processor_bonus", None)
        player.combat_state = cs_bp

    # Addon 38 (Einstein AutoML): cumulative +1 per miss (resets on hit)
    _automl_bonus = (player.combat_state or {}).get("automl_miss_bonus", 0)

    # Addon 3 (Einstein Prediction): reroll flag set by use_addon
    _ep_reroll = (player.combat_state or {}).get("einstein_prediction_pre_reroll", False)
    if _ep_reroll:
        _cs_ep = dict(player.combat_state)
        _cs_ep.pop("einstein_prediction_pre_reroll", None)
        player.combat_state = _cs_ep

    # Addon 5 (Hyperforce Boost): roll twice, take best
    _addon5_active = has_addon(player, 5)

    if _ep_reroll or _addon5_active:
        # Roll twice (or more) and take best
        roll = max(engine.roll_d10(), engine.roll_d10())
        if roll_mode == "worst_of_2":
            roll = min(roll, engine.roll_d10())
        elif roll_mode == "second_of_2":
            roll = engine.roll_d10()
    else:
        roll = engine.roll_d10()
        if roll_mode == "worst_of_2":
            roll = min(roll, engine.roll_d10())
        elif roll_mode == "second_of_2":
            roll = engine.roll_d10()

    # Card 72 (Engagement Split): opponent forced a reroll — take second result
    if (player.combat_state or {}).get("forced_reroll_next"):
        cs = dict(player.combat_state)
        cs.pop("forced_reroll_next", None)
        player.combat_state = cs
        roll = engine.roll_d10()
        if roll_mode == "worst_of_2":
            roll = min(roll, engine.roll_d10())
        elif roll_mode == "second_of_2":
            roll = engine.roll_d10()

    # Card 105 (Message Transformation): auto-upgrade low rolls ≤ 3 to 6 (once per combat)
    if (player.combat_state or {}).get("message_transformation_active") and roll <= 3:
        roll = 6
        cs = dict(player.combat_state)
        cs.pop("message_transformation_active", None)
        player.combat_state = cs

    # Card 142 (Automotive Cloud): take the best of 2 rolls for N rounds
    if (player.combat_state or {}).get("best_of_2_until_round", 0) >= current_round:
        roll = max(roll, engine.roll_d10())

    # Card 171 (Copilot Studio): all numeric values +1 this round — apply to roll
    if (player.combat_state or {}).get("copilot_studio_boost_active"):
        roll = min(10, roll + 1)

    # Card 192 (Screen Flow): guided step-by-step — use 7 if roll < 7 (once per card play)
    if (player.combat_state or {}).get("screen_flow_active"):
        if roll < 7:
            roll = 7
        cs = dict(player.combat_state)
        cs.pop("screen_flow_active", None)
        player.combat_state = cs

    # Card 26 (Dice Optimizer) / Card 62 (DataWeave Script) / Card 104 (Flow Variable): force next roll
    _forced_roll = (player.combat_state or {}).get("next_roll_forced")
    if _forced_roll is not None:
        roll = _forced_roll
        cs = dict(player.combat_state)
        cs.pop("next_roll_forced", None)
        player.combat_state = cs
    else:
        # Card 29 (Chaos Mode): opponent flipped this roll (11 − roll)
        if (player.combat_state or {}).get("chaos_mode_next_roll"):
            roll = 11 - roll
            cs = dict(player.combat_state)
            cs.pop("chaos_mode_next_roll", None)
            player.combat_state = cs

    # Card 60 (Einstein STO): +1 to roll for timing optimization, capped at 10
    _einstein_bonus = (player.combat_state or {}).get("einstein_sto_next_roll_bonus", 0)
    if _einstein_bonus:
        roll = min(10, roll + _einstein_bonus)
        cs = dict(player.combat_state)
        cs.pop("einstein_sto_next_roll_bonus", None)
        player.combat_state = cs

    # Capture pre-bonus roll for Addon 4 check
    _raw_roll_for_addon4 = roll

    # Addon 1 (Trailhead Badge): +1 to every roll
    if has_addon(player, 1):
        roll = min(10, roll + 1)

    # Addon 2 (Lightning Component): +2 to first roll of each combat (combat_round is still 0 before increment)
    if has_addon(player, 2) and (player.combat_round or 0) == 0:
        roll = min(10, roll + 2)

    # Addon 77 (Formula Field): +1 to all dice rolls
    if has_addon(player, 77):
        roll = min(10, roll + 1)

    # Addon 81 (Boss Vulnerability Scan): +4 bonus to next roll (one-shot per combat)
    _cs81 = player.combat_state or {}
    if _cs81.get("vulnerability_scan_bonus"):
        roll = min(10, roll + _cs81["vulnerability_scan_bonus"])
        _cs81_new = dict(_cs81)
        del _cs81_new["vulnerability_scan_bonus"]
        player.combat_state = _cs81_new

    # Addon 115 (Future Method): next dice roll doubled (capped at 10)
    _cs115 = player.combat_state or {}
    if _cs115.get("future_method_active"):
        roll = min(roll * 2, 10)
        _cs115_new = dict(_cs115)
        del _cs115_new["future_method_active"]
        player.combat_state = _cs115_new

    # Addon 136 (Package Upgrade): each addon owned for ≥3 turns gives +1 to dice rolls (max +3)
    if has_addon(player, 136):
        _aq136 = (player.combat_state or {}).get("addon_acquired_turns", {})
        _bonus136 = 0
        for _pa136 in player.addons:
            _acq_turn136 = _aq136.get(str(_pa136.id), game.turn_number)
            if game.turn_number - _acq_turn136 >= 3:
                _bonus136 += 1
        roll = min(10, roll + min(_bonus136, 3))

    # Addon 142 (All or Nothing): apply +4 bonus from skipped round
    _aon_bonus = (player.combat_state or {}).get("all_or_nothing_bonus", 0)
    if _aon_bonus:
        roll = min(roll + _aon_bonus, 10)
        cs_aon = dict(player.combat_state)
        del cs_aon["all_or_nothing_bonus"]
        player.combat_state = cs_aon

    # Addon 144 (High Stakes): +3 if player has 0 certs AND 0 other addons
    if has_addon(player, 144):
        _other_addons144 = [pa for pa in player.addons if pa.card and pa.card.number != 144]
        if player.certificazioni == 0 and len(_other_addons144) == 0:
            roll = min(roll + 3, 10)

    # Addon 148 (Last Stand): +2 if flag set at turn start
    if has_addon(player, 148) and (player.combat_state or {}).get("last_stand_active"):
        roll = min(roll + 2, 10)

    # Addon 155 (Fast Track Program): cert bosses have dice threshold -1
    # (applied later in threshold calculation; see below)

    # Addon 156 (Trailhead Ranger): +1 per cert beyond the first if ≥2 certs
    if has_addon(player, 156) and player.certificazioni >= 2:
        roll = min(roll + (player.certificazioni - 1), 10)

    # Addon 160 (Graduation Day): +2 dice bonus for next turn after reaching 4 certs
    _grad_bonus = (player.combat_state or {}).get("graduation_day_dice_bonus", 0)
    if _grad_bonus:
        roll = min(roll + _grad_bonus, 10)
        cs_grad = dict(player.combat_state)
        del cs_grad["graduation_day_dice_bonus"]
        player.combat_state = cs_grad

    # Addon 167 (Evangelist Aura): dice bonus granted by a neighbor's boss defeat
    _eva_bonus167 = (player.combat_state or {}).get("evangelist_aura_dice_bonus", 0)
    if _eva_bonus167:
        roll = min(roll + _eva_bonus167, 10)
        cs_eva167 = dict(player.combat_state)
        del cs_eva167["evangelist_aura_dice_bonus"]
        player.combat_state = cs_eva167

    # Addon 200 (The Lost Trailbraizer): +1 to every dice roll
    if has_addon(player, 200):
        roll = min(roll + 1, 10)

    # Addon 4 (Apex Governor Override): original roll of 1 → round neutral (before addon bonuses)
    _addon4_override = has_addon(player, 4) and _raw_roll_for_addon4 == 1

    # Addon 32 (Apex Batch Processor): apply +2 bonus from previous hit
    if _bp_bonus:
        roll = min(10, roll + _bp_bonus)
    # Addon 38 (Einstein AutoML): apply cumulative miss bonus
    if _automl_bonus:
        roll = min(10, roll + _automl_bonus)

    # Boss 56 (Change Data Capture Lurker): track rolled numbers; duplicate → auto miss
    _lurker_miss = False
    if engine.boss_tracks_duplicate_rolls(boss.id):
        cs = dict(player.combat_state or {})
        _seen = cs.get("lurker_rolled_numbers", [])
        if roll in _seen:
            _lurker_miss = True
        else:
            _seen = _seen + [roll]
            cs["lurker_rolled_numbers"] = _seen
            player.combat_state = cs

    # Boss 67 (Developer Console Glitch): roll 1 or 2 → entire round is nullified
    round_nullified = engine.boss_nullifies_round_on_low_roll(boss.id) and roll <= 2

    # Addon 4 (Apex Governor Override): original roll of 1 (before bonuses) → round neutral
    if _addon4_override:
        round_nullified = True

    # ── Threshold calculation (needed to show preview to Lucky Roll window) ──
    # Boss 10, 12, 22, 37: dynamic threshold (now also passes combat_round for boss 22)
    # threshold_bonus from boss 63 deal (auto-accept raises threshold by 1 for this roll only)
    threshold = engine.boss_threshold(
        boss.id,
        boss.dice_threshold,
        player.current_boss_hp or 0,
        hand_count=len(player.hand),
        combat_round=current_round,
    ) + threshold_bonus
    # Card 13 (Debug Exploit): persistent threshold reduction for rest of combat
    threshold -= (player.combat_state or {}).get("boss_threshold_reduction", 0)
    # Card 151 (Hyperforce Migration): suppress boss threshold bonuses and boss ability for N rounds
    _hyperforce_until = (player.combat_state or {}).get("hyperforce_until_round", 0)
    _hyperforce_active = _hyperforce_until >= current_round
    # Card 220 (Grounding Data): freeze all threshold modifications for N turns
    _grounding_active = (player.combat_state or {}).get("grounding_data_until_turn", 0) >= game.turn_number
    # Card 15 (Scope Creep): opponent raised threshold for this roll only
    _scope_creep_until = (player.combat_state or {}).get("boss_threshold_increase_until_round", 0)
    if _scope_creep_until >= current_round and not _hyperforce_active and not _grounding_active:
        threshold += 2
    # Card 38 (Consulting Hours) / Card 91 (Guided Selling): threshold reduction for N rounds
    _consulting_until = (player.combat_state or {}).get("consulting_hours_until_round", 0)
    if _consulting_until >= current_round and not _grounding_active:
        threshold -= (player.combat_state or {}).get("consulting_hours_threshold_reduction", 2)
    # Card 96 (Review App): threshold -2 for round 1 only
    if (player.combat_state or {}).get("review_app_active") and current_round == 1:
        threshold -= 2
        cs = dict(player.combat_state)
        cs.pop("review_app_active", None)
        player.combat_state = cs
    # Addon 34 (SOQL Optimizer): reduce effective threshold by 1
    if has_addon(player, 34):
        threshold = max(1, threshold - 1)
    # Addon 155 (Fast Track Program): cert bosses have threshold -1
    if has_addon(player, 155) and boss.has_certification:
        threshold = max(1, threshold - 1)
    threshold = max(1, threshold)  # can't go below 1
    # Boss 58 (Prompt Builder Djinn): random threshold set this round overrides everything
    _djinn_t = (player.combat_state or {}).get("djinn_threshold")
    if _djinn_t is not None:
        threshold = _djinn_t
    # Card 281 (World's Most Innovative): override threshold to 1 for this combat
    if (player.combat_state or {}).get("boss_threshold_override_1"):
        threshold = 1

    # Card 203 (Sender Profile): threshold -2 for this round (boss doesn't recognize the sender)
    if (player.combat_state or {}).get("sender_profile_threshold_reduction"):
        threshold = max(1, threshold - (player.combat_state or {}).get("sender_profile_threshold_reduction", 0))
        cs = dict(player.combat_state)
        cs.pop("sender_profile_threshold_reduction", None)
        player.combat_state = cs

    # Card 136 (Service Forecast): use threshold as roll instead of the random result (guaranteed border hit)
    if (player.combat_state or {}).get("service_forecast_use_threshold"):
        roll = threshold
        cs = dict(player.combat_state)
        cs.pop("service_forecast_use_threshold", None)
        player.combat_state = cs

    # Card 98 (Pause Element): round_nullified override — consumes 1 round of the flag
    if (player.combat_state or {}).get("pause_element_rounds_remaining", 0) > 0:
        cs = dict(player.combat_state)
        cs["pause_element_rounds_remaining"] -= 1
        if cs["pause_element_rounds_remaining"] <= 0:
            cs.pop("pause_element_rounds_remaining", None)
        player.combat_state = cs
        round_nullified = True

    # Addon 192 (NullPointerException): if roll == 1, skip HP damage (neutral round)
    if roll == 1 and has_addon(player, 192):
        _null_192 = True
    else:
        _null_192 = False

    # Card 288 (NullPointerException): if roll == 1, nullify this round (one-shot)
    if (player.combat_state or {}).get("null_pointer_active") and roll == 1:
        cs = dict(player.combat_state)
        cs.pop("null_pointer_active", None)
        player.combat_state = cs
        round_nullified = True

    # Card 59 (Dynamic Content): auto-reroll once on a miss (player played this proactively)
    if (player.combat_state or {}).get("dynamic_content_reroll"):
        cs = dict(player.combat_state)
        cs.pop("dynamic_content_reroll", None)
        player.combat_state = cs
        if engine.resolve_combat_round(roll, threshold) != "hit":
            roll = engine.roll_d10()
            round_nullified = engine.boss_nullifies_round_on_low_roll(boss.id) and roll <= 2

    # Card 61 (Predictive Model): read and consume prediction — bonus applied later in hit branch
    _predictive_model_prediction = (player.combat_state or {}).get("predictive_model_prediction")
    if _predictive_model_prediction is not None:
        cs = dict(player.combat_state)
        cs.pop("predictive_model_prediction", None)
        player.combat_state = cs
    _predictive_bonus = (_predictive_model_prediction is not None and _predictive_model_prediction == roll)

    result = engine.resolve_combat_round(roll, threshold)
    if _lurker_miss:
        result = "miss"  # Boss 56: duplicate roll → forced miss

    # Addon 141 (Calculated Risk): apply bet outcome after roll
    _cs141 = player.combat_state or {}
    if _cs141.get("calculated_risk_active"):
        cs141_new = dict(_cs141)
        del cs141_new["calculated_risk_active"]
        player.combat_state = cs141_new
        if roll >= 8:
            player.licenze += 5
        elif roll <= 3:
            player.licenze = max(0, player.licenze - 2)

    # Boss 65 (Einstein Vision Stalker): if prediction matches roll direction → player -1L
    _stalker_pred = (player.combat_state or {}).get("stalker_prediction")
    if _stalker_pred:
        _pred_correct = (
            (_stalker_pred == "above" and roll > 5) or
            (_stalker_pred == "below" and roll < 5)
        )
        if _pred_correct:
            player.licenze = max(0, player.licenze - 1)
        cs = dict(player.combat_state)
        cs.pop("stalker_prediction", None)
        player.combat_state = cs

    player.combat_round += 1

    # Addon 40 (Salesforce Shield): every 3 rounds survived, recover 1 HP
    if has_addon(player, 40) and (player.combat_round or 0) % 3 == 0 and (player.combat_round or 0) > 0:
        player.hp = min(player.max_hp, player.hp + 1)

    # Role passive: Service Cloud Consultant — recover 1 HP after round 3 (once per combat)
    _scc_hp_recover = _engine_role.should_recover_hp_at_round(player, current_round)
    if _scc_hp_recover > 0:
        player.hp = min(player.max_hp, player.hp + _scc_hp_recover)
        _scc_cs = dict(player.combat_state or {})
        _scc_cs["service_cloud_hp_recovered"] = True
        player.combat_state = _scc_cs

    # ── La Pila: reazione multi-giocatore dopo il tiro ─────────────────────
    _pila_order = [p.id for p in game.players]
    _ap_idx = next((i for i, p in enumerate(game.players) if p.id == player.id), 0)
    _pila_order = _pila_order[_ap_idx:] + _pila_order[:_ap_idx]
    from app.websocket.stack_manager import open_stack as _open_stack
    roll, result = await _open_stack(
        game.code, _pila_order, roll, result, threshold, timeout=8.0
    )
    # Re-compute round_nullified in case force_reroll happened
    round_nullified = engine.boss_nullifies_round_on_low_roll(boss.id) and roll <= 2
    # ────────────────────────────────────────────────────────────────────────

    player_took_damage = False

    # Card 12 (Governor Limit Exploit): double boss damage per successful hit for N rounds
    _hit_damage = 2 if (player.combat_state or {}).get("double_damage_until_round", 0) >= current_round else 1
    # Card 61 (Predictive Model): exact prediction on hit → at least 2HP damage
    if _predictive_bonus and _hit_damage < 2:
        _hit_damage = 2
    # Role passive: Einstein Analytics Consultant — correct dice prediction doubles hit damage
    _einstein_pred = (player.combat_state or {}).get("einstein_prediction")
    _einstein_pred_correct = False
    if _einstein_pred is not None:
        _einstein_pred_correct = (_einstein_pred == roll) and (result == "hit")
        _cs_ein = dict(player.combat_state or {})
        _cs_ein.pop("einstein_prediction", None)  # consume regardless of correctness
        player.combat_state = _cs_ein
    if _einstein_pred_correct:
        _hit_damage *= 2
        await manager.broadcast(game.code, {
            "type": "einstein_prediction_correct",
            "player_id": player.id,
            "prediction": _einstein_pred,
            "roll": roll,
            "hit_damage": _hit_damage,
        })
    # Card 28 (Critical System): roll of exactly 10 deals 3 HP to boss (overrides all other modifiers)
    if (player.combat_state or {}).get("critical_system_until_round", 0) >= current_round and roll == 10:
        _hit_damage = 3
    # Card 127 (Omni-Channel): next hit deals +1 HP to boss (stacks with other bonuses unless critical_system)
    if (player.combat_state or {}).get("omni_channel_next_hit_bonus") and _hit_damage < 3:
        _hit_damage += 1
        cs = dict(player.combat_state)
        cs.pop("omni_channel_next_hit_bonus", None)
        player.combat_state = cs

    if round_nullified or _null_192:
        # No damage in either direction this round
        pass
    elif result == "hit":
        # Addon 31 (Critical Update Override): exact threshold hit deals 1 extra HP to boss
        if has_addon(player, 31) and roll == threshold:
            _hit_damage += 1
        # Boss 78 (Known Issues Ghost) / Boss 89 (Object Manager Juggernaut): immune to dice
        if not engine.boss_immune_to_dice(boss.id, current_round):
            # Boss 94 (Loyalty Cloud Warden): absorb hit with loyalty point instead of HP
            if engine.boss_loyalty_shield(boss.id) > 0 and player.combat_state:
                lp = player.combat_state.get("loyalty_points", 0)
                if lp > 0:
                    cs = dict(player.combat_state)
                    cs["loyalty_points"] = lp - 1
                    player.combat_state = cs
                    # Hit absorbed by loyalty — no boss HP damage this roll
                else:
                    player.current_boss_hp -= _hit_damage
                    if prediction == "hit":
                        player.current_boss_hp -= 1  # prediction bonus: always 1
            else:
                player.current_boss_hp -= _hit_damage
                # Double boss damage if prediction was "hit" and correct (boss 53)
                if prediction == "hit":
                    player.current_boss_hp -= 1  # prediction bonus: always 1
        # Addon 77 (Formula Field): +1 HP damage on hit
        if has_addon(player, 77):
            player.current_boss_hp -= 1
        # Card 148 (Loop Element): track hits dealt for damage scaling
        _cs_hit = dict(player.combat_state or {})
        _cs_hit["combat_hits_dealt"] = _cs_hit.get("combat_hits_dealt", 0) + 1
        player.combat_state = _cs_hit
        # Role passive: Platform Developer I/II / CTA — critical hit bonus boss damage
        _role_roll_result = _engine_role.on_roll_result(player, roll)
        if _role_roll_result["extra_boss_hp_damage"] > 0 and not engine.boss_immune_to_dice(boss.id, current_round):
            player.current_boss_hp = max(0, (player.current_boss_hp or 0) - _role_roll_result["extra_boss_hp_damage"])
        # Addon 32 (Apex Batch Processor): set bonus for next round on hit
        if has_addon(player, 32):
            cs32 = dict(player.combat_state or {})
            cs32["batch_processor_bonus"] = True
            player.combat_state = cs32
        # Addon 36 (Test Coverage Booster): roll of 10 → gain +1L
        if has_addon(player, 36) and roll == 10:
            player.licenze += 1
        # Addon 38 (Einstein AutoML): clear miss bonus on hit
        if has_addon(player, 38) and (player.combat_state or {}).get("automl_miss_bonus"):
            cs38h = dict(player.combat_state)
            cs38h.pop("automl_miss_bonus", None)
            player.combat_state = cs38h
        # Card 95 (Heroku CI): if boss HP ≤ 2 before this hit, finish the boss immediately
        if (player.combat_state or {}).get("heroku_ci_active") and (player.current_boss_hp or 0) <= 2:
            player.current_boss_hp = 0
            cs = dict(player.combat_state)
            cs.pop("heroku_ci_active", None)
            player.combat_state = cs
    else:
        # Card 30 (Force Field) / Card 55 (Try Scope): player immune to boss roll damage for 1 round
        _force_field_until = (player.combat_state or {}).get("force_field_until_round", 0)
        _try_scope_until = (player.combat_state or {}).get("try_scope_until_round", 0)
        # Card 58 (Entitlement Process): boss deals max 1 damage per round for N rounds
        _entitlement_until = (player.combat_state or {}).get("entitlement_process_until_round", 0)
        _entitlement_active = _entitlement_until >= current_round
        if _force_field_until >= current_round or _try_scope_until >= current_round:
            pass  # neutral round — no player damage
        # Card 103 (Transform Element): next miss → -1L instead of -1HP (one-time)
        elif (player.combat_state or {}).get("transform_element_active"):
            player.licenze = max(0, player.licenze - 1)
            cs = dict(player.combat_state)
            cs.pop("transform_element_active", None)
            player.combat_state = cs
        # Card 97 (Fault Path): on miss gain 1L instead of taking HP damage (3 uses)
        elif (player.combat_state or {}).get("fault_path_remaining", 0) > 0:
            player.licenze += 1
            _cs97 = dict(player.combat_state)
            _cs97["fault_path_remaining"] -= 1
            if _cs97["fault_path_remaining"] <= 0:
                _cs97.pop("fault_path_remaining", None)
            player.combat_state = _cs97
        # Boss 95 (Identity & Access Heretic): player damage redirected to random opponent
        elif engine.boss_redirects_damage_to_opponent(boss.id):
            opponents_redir = [p for p in game.players if p.id != player.id]
            if opponents_redir:
                target_redir = random.choice(opponents_redir)
                target_redir.hp = max(0, target_redir.hp - 1)
        else:
            _player_hp_damage = 1
            # Addon 58 (High Availability): if HP is at max, first 2 misses don't remove HP
            _skip_hp58 = False
            if has_addon(player, 58) and player.hp == player.max_hp:
                _ha_remaining = (player.combat_state or {}).get("ha_misses_remaining", 0)
                if _ha_remaining > 0:
                    _cs58m = dict(player.combat_state)
                    _cs58m["ha_misses_remaining"] = _ha_remaining - 1
                    if _cs58m["ha_misses_remaining"] <= 0:
                        _cs58m.pop("ha_misses_remaining", None)
                    player.combat_state = _cs58m
                    _skip_hp58 = True
            if _skip_hp58:
                _player_hp_damage = 0
            # Addon 22 (Service Level Agreement): cap boss damage to 1 HP per round
            # (already 1 by default; this guard ensures card bonuses don't exceed 1)
            if has_addon(player, 22):
                _player_hp_damage = min(_player_hp_damage, 1)
            # Card 130 (Queue-Based Routing): double damage on the designated round (2HP)
            if (player.combat_state or {}).get("queue_routing_double_damage_round") == current_round:
                _player_hp_damage = 2
                cs = dict(player.combat_state)
                cs.pop("queue_routing_double_damage_round", None)
                player.combat_state = cs
            # Card 132 (Escalation Rule): if taking ≥2HP, absorb half (floor)
            if _player_hp_damage >= 2 and (player.combat_state or {}).get("escalation_rule_active"):
                _player_hp_damage = _player_hp_damage - (_player_hp_damage // 2)
            # Card 204 (Delivery Profile): block HP damage for one miss round, then clear
            if _player_hp_damage > 0 and (player.combat_state or {}).get("delivery_profile_block_active"):
                _player_hp_damage = 0
                _cs_dp = dict(player.combat_state)
                _cs_dp.pop("delivery_profile_block_active", None)
                player.combat_state = _cs_dp
            # Card 153 (Environment Branch): redirect damage to left/right neighbours, skip own HP loss
            elif _player_hp_damage > 0 and (player.combat_state or {}).get("environment_branch_active"):
                _player_hp_damage = 0
                _cs_eb = dict(player.combat_state)
                _cs_eb.pop("environment_branch_active", None)
                player.combat_state = _cs_eb
                _all_players = list(game.players)
                _idx = next((i for i, p in enumerate(_all_players) if p.id == player.id), None)
                if _idx is not None and len(_all_players) > 1:
                    _left = _all_players[(_idx - 1) % len(_all_players)]
                    _right = _all_players[(_idx + 1) % len(_all_players)]
                    for _nb in (_left, _right):
                        if _nb.id != player.id:
                            _nb.hp = max(0, _nb.hp - 1)
                    await manager.broadcast(game.code, {
                        "type": "environment_branch_redirect",
                        "left_player_id": _left.id,
                        "right_player_id": _right.id,
                        "damage_each": 1,
                    })
            # Card 156 (Travel Time Calc): if roll exactly == threshold-1, skip damage
            elif _player_hp_damage > 0 and (player.combat_state or {}).get("travel_time_calc_active") and roll == threshold - 1:
                _player_hp_damage = 0
                _cs_tt = dict(player.combat_state)
                _cs_tt.pop("travel_time_calc_active", None)
                player.combat_state = _cs_tt
            # Addon 39 (Streaming API Buffer): first miss of combat absorbed — skip HP damage
            if _player_hp_damage > 0 and (player.combat_state or {}).get("buffer_active"):
                _cs39 = dict(player.combat_state)
                _cs39.pop("buffer_active", None)
                player.combat_state = _cs39
                _player_hp_damage = 0
            # Card 258 (Salesforce Tower): if damage would kill, survive at 1HP (once only)
            _new_hp = player.hp - _player_hp_damage
            if _new_hp <= 0 and (player.combat_state or {}).get("salesforce_tower_active"):
                player.hp = 1
                _cs_st = dict(player.combat_state)
                _cs_st.pop("salesforce_tower_active", None)
                player.combat_state = _cs_st
            else:
                player.hp = max(0, _new_hp)
            player_took_damage = True
            # Addon 135 (Hotfix): +1L per HP lost on miss
            if _player_hp_damage > 0 and has_addon(player, 135):
                player.licenze += _player_hp_damage
            # Addon 7 (Flow Automation): clear no_damage_this_combat flag when player takes HP damage
            if _player_hp_damage > 0 and (player.combat_state or {}).get("no_damage_this_combat"):
                _cs7_dmg = dict(player.combat_state)
                _cs7_dmg.pop("no_damage_this_combat", None)
                player.combat_state = _cs7_dmg
            if _player_hp_damage > 0:
                # Card 152 (Net Zero Commitment): +1L per HP lost
                if (player.combat_state or {}).get("net_zero_commitment_active"):
                    player.licenze += _player_hp_damage
                # Card 154 (Sustainability Cloud): accumulate HP lost for addon discount
                if (player.combat_state or {}).get("sustainability_discount_pending"):
                    _cs_sus = dict(player.combat_state)
                    _cs_sus["sustainability_hp_lost"] = _cs_sus.get("sustainability_hp_lost", 0) + _player_hp_damage
                    player.combat_state = _cs_sus
            # Card 133 (Contact Center Integration): on HP loss, draw 1 card
            if (player.combat_state or {}).get("contact_center_until_round", 0) >= current_round:
                from app.models.game import PlayerHandCard as _PHC133
                if game.action_deck:
                    db.add(_PHC133(player_id=player.id, action_card_id=game.action_deck.pop(0)))
            # Card 92 (Case Escalation): track boss hits for escalation bonus
            cs92 = dict(player.combat_state or {})
            cs92["combat_boss_hits_received"] = cs92.get("combat_boss_hits_received", 0) + 1
            player.combat_state = cs92

        miss_effect = engine.apply_boss_ability(
            boss.id, "after_miss",
            dice_result=roll,
            combat_round=current_round,
            current_hp=player.current_boss_hp or 0,
        )
        # Card 53 (AMPscript Block): boss ability reflected — extra_damage redirected as boss HP loss
        _ampscript_until = (player.combat_state or {}).get("ampscript_reflected_until_round", 0)
        if _ampscript_until >= current_round and miss_effect["extra_damage"] > 0:
            player.current_boss_hp = max(0, (player.current_boss_hp or 0) - 1)
            miss_effect = {**miss_effect, "extra_damage": 0}  # absorb the extra_damage
        # Card 151 (Hyperforce Migration): suppress boss after_miss ability
        if _hyperforce_active:
            miss_effect = {k: (0 if isinstance(v, int) else False) for k, v in miss_effect.items()}
        if miss_effect["extra_damage"] > 0 and not _entitlement_active:
            player.hp = max(0, player.hp - miss_effect["extra_damage"])
            # Double player damage if prediction was "miss" and correct (boss 53)
            if prediction == "miss":
                player.hp = max(0, player.hp - miss_effect["extra_damage"])
        if miss_effect["boss_heal"] > 0:
            player.current_boss_hp = min(
                boss.hp, (player.current_boss_hp or 0) + miss_effect["boss_heal"]
            )
        if miss_effect["aoe_all_players_hp_damage"] > 0:
            # Boss 40 (Net Zero Apocalypse): ALL players lose 1 HP on every miss
            for p_aoe in game.players:
                p_aoe.hp = max(0, p_aoe.hp - miss_effect["aoe_all_players_hp_damage"])

        # Boss 33 (Experience Cloud Illusion): consume declared card on miss
        if engine.boss_card_declared_before_roll(boss.id) and player.combat_state:
            declared_hc_id = player.combat_state.get("declared_hand_card_id")
            if declared_hc_id:
                from app.models.game import PlayerHandCard as _PHC33
                hc_33 = db.get(_PHC33, declared_hc_id)
                if hc_33 and hc_33.player_id == player.id:
                    game.action_discard = (game.action_discard or []) + [hc_33.action_card_id]
                    db.delete(hc_33)

    # Addon 86 (Critical Patch): +1L on miss
    if result == "miss" and has_addon(player, 86):
        player.licenze += 1

    # Addon 38 (Einstein AutoML): accumulate miss bonus; reset on hit
    if result == "miss" and has_addon(player, 38):
        cs38 = dict(player.combat_state or {})
        cs38["automl_miss_bonus"] = cs38.get("automl_miss_bonus", 0) + 1
        player.combat_state = cs38

    # Card 240 (Batch Scope): apply 1HP DOT per round while counter > 0
    if (player.combat_state or {}).get("batch_scope_dot_rounds", 0) > 0:
        player.current_boss_hp = max(0, (player.current_boss_hp or 0) - 1)
        _cs_bs = dict(player.combat_state)
        _cs_bs["batch_scope_dot_rounds"] = _cs_bs["batch_scope_dot_rounds"] - 1
        if _cs_bs["batch_scope_dot_rounds"] <= 0:
            _cs_bs.pop("batch_scope_dot_rounds", None)
        player.combat_state = _cs_bs


    # Card 169 (Model Builder): track total misses (not consecutive); after 3, force next roll = 10
    if result == "miss" and (player.combat_state or {}).get("model_builder_active"):
        _cs_mb = dict(player.combat_state)
        _cs_mb["model_builder_misses"] = _cs_mb.get("model_builder_misses", 0) + 1
        if _cs_mb["model_builder_misses"] >= 3:
            _cs_mb["next_roll_forced"] = 10
            _cs_mb.pop("model_builder_active", None)
            _cs_mb.pop("model_builder_misses", None)
        player.combat_state = _cs_mb

    # Boss 87 (Pub/Sub API Pestilence): 2 consecutive misses → boss recovers 1 HP
    _replay_threshold = engine.boss_recovers_on_consecutive_misses(boss.id)
    if _replay_threshold:
        _cs87 = dict(player.combat_state or {})
        if result == "miss":
            _cs87["pubsub_consecutive_misses"] = _cs87.get("pubsub_consecutive_misses", 0) + 1
            if _cs87["pubsub_consecutive_misses"] >= _replay_threshold:
                player.current_boss_hp = (player.current_boss_hp or 0) + 1
                _cs87["pubsub_consecutive_misses"] = 0
                await manager.broadcast(game.code, {
                    "type": "boss_hp_recovered",
                    "boss_id": boss.id,
                    "amount": 1,
                    "reason": "replay",
                })
        else:
            _cs87["pubsub_consecutive_misses"] = 0
        player.combat_state = _cs87

    # Boss 81 (Trailhead Jinx): miss → discard 1 random card from hand
    if result == "miss" and engine.boss_discard_on_miss(boss.id) and player.hand:
        import random as _random81
        _jinx_hc = _random81.choice(player.hand)
        db.delete(_jinx_hc)
        await manager.broadcast(game.code, {
            "type": "jinx_discard",
            "player_id": player.id,
            "card_id": _jinx_hc.action_card_id,
        })

    # Clear boss 33 declaration after every roll (hit or miss)
    if engine.boss_card_declared_before_roll(boss.id) and player.combat_state:
        cs = dict(player.combat_state)
        cs.pop("declared_card_id", None)
        cs.pop("declared_hand_card_id", None)
        player.combat_state = cs

    # Boss 55 / Boss 74: apply shadow copy's after_miss effects
    if copy_boss_id and result == "miss":
        copy_miss = engine.apply_boss_ability(
            copy_boss_id, "after_miss",
            dice_result=roll,
            combat_round=current_round,
            current_hp=player.current_boss_hp or 0,
        )
        if copy_miss["extra_damage"] > 0:
            player.hp = max(0, player.hp - copy_miss["extra_damage"])
        if copy_miss["boss_heal"] > 0:
            player.current_boss_hp = min(boss.hp, (player.current_boss_hp or 0) + copy_miss["boss_heal"])

    # Boss 5 (Sandbox Tyrant): random opponent gains 1 Licenza when player takes damage
    if player_took_damage:
        dmg_effect = engine.apply_boss_ability(boss.id, "on_player_damage")
        if dmg_effect["opponent_gains_licenza"] > 0:
            opponents = [p for p in game.players if p.id != player.id]
            if opponents:
                random.choice(opponents).licenze += dmg_effect["opponent_gains_licenza"]

    # ── on_round_end effects ──────────────────────────────────────────────
    round_end = engine.apply_boss_ability(
        boss.id, "on_round_end",
        combat_round=current_round,
        cards_played=player.cards_played_this_turn,
    )

    # Boss 11 (LWC Poltergeist): even rounds → random opponent takes 1 HP
    if round_end["aoe_hp_damage"] > 0:
        opponents = [p for p in game.players if p.id != player.id]
        if opponents:
            target = random.choice(opponents)
            target.hp = max(0, target.hp - round_end["aoe_hp_damage"])

    # Boss 27 (Marketing Cloud Banshee): every round ALL opponents (not combatant) lose 1 HP
    if round_end["aoe_all_hp_damage"] > 0:
        for p_aoe in [p for p in game.players if p.id != player.id]:
            p_aoe.hp = max(0, p_aoe.hp - round_end["aoe_all_hp_damage"])

    # Boss 50 (Health Cloud Plague) / Boss 40 (on_round_end variant): ALL players lose 1 HP
    if round_end["aoe_all_players_hp_damage"] > 0:
        for p_aoe in game.players:
            p_aoe.hp = max(0, p_aoe.hp - round_end["aoe_all_players_hp_damage"])

    # Boss 87 (Pub/Sub API Pestilence): ALL players lose 1 HP, not blockable by defensive cards
    if round_end["aoe_unblockable_hp_damage"] > 0:
        for p_aoe in game.players:
            p_aoe.hp = max(0, p_aoe.hp - round_end["aoe_unblockable_hp_damage"])

    # Boss 84 (Data Import Doomsayer): if fight runs longer than prediction, deal 1 extra HP per excess round
    if player.combat_state:
        dcap = player.combat_state.get("doomsayer_prediction_cap")
        if dcap is not None and current_round > dcap:
            player.hp = max(0, player.hp - 1)

    # Boss 55 / Boss 74: apply shadow copy's on_round_end effects
    if copy_boss_id:
        copy_re = engine.apply_boss_ability(
            copy_boss_id, "on_round_end",
            combat_round=current_round,
            cards_played=player.cards_played_this_turn,
        )
        if copy_re["aoe_hp_damage"] > 0:
            opponents_c = [p for p in game.players if p.id != player.id]
            if opponents_c:
                random.choice(opponents_c).hp = max(0, random.choice(opponents_c).hp - copy_re["aoe_hp_damage"])
        if copy_re["aoe_all_hp_damage"] > 0:
            for p_c in [p for p in game.players if p.id != player.id]:
                p_c.hp = max(0, p_c.hp - copy_re["aoe_all_hp_damage"])
        if copy_re["aoe_all_players_hp_damage"] > 0:
            for p_c in game.players:
                p_c.hp = max(0, p_c.hp - copy_re["aoe_all_players_hp_damage"])

    # Boss 73 (Streaming API Storm): every round a random opponent draws 1 extra card
    if round_end["opponent_draws_card"] > 0:
        opponents_draw = [p for p in game.players if p.id != player.id]
        if opponents_draw:
            target_draw = random.choice(opponents_draw)
            from app.models.game import PlayerHandCard as PHC_draw
            if game.action_deck:
                db.add(PHC_draw(player_id=target_draw.id, action_card_id=game.action_deck.pop(0)))
    # Card 23 (Disaster Recovery): survive fatal blow with 1 HP — played proactively before this roll
    if player.hp <= 0 and (player.combat_state or {}).get("disaster_recovery_ready"):
        player.hp = 1
        cs = dict(player.combat_state)
        cs.pop("disaster_recovery_ready", None)
        player.combat_state = cs

    # Card 56 (On Error Continue): survive death at cost of 3 Licenze
    if player.hp <= 0 and (player.combat_state or {}).get("on_error_continue_ready"):
        player.hp = 1
        player.licenze = max(0, player.licenze - 3)
        cs = dict(player.combat_state)
        cs.pop("on_error_continue_ready", None)
        player.combat_state = cs

    # Card 158 (Runtime Manager): cross-turn survival flag — survive fatal blow with 1 HP
    if player.hp <= 0 and (player.combat_state or {}).get("runtime_manager_ready"):
        player.hp = 1
        cs = dict(player.combat_state)
        cs.pop("runtime_manager_ready", None)
        player.combat_state = cs

    boss_defeated = player.current_boss_hp is not None and player.current_boss_hp <= 0
    player_died = player.hp <= 0

    # Card 76 (Milestone Action): watchers gain 1L per round the combatant survives
    if not player_died and not boss_defeated:
        for _watcher in game.players:
            if _watcher.id != player.id and (_watcher.combat_state or {}).get("milestone_action_remaining", 0) > 0:
                _ms = _watcher.combat_state["milestone_action_remaining"]
                _watcher.licenze += 1
                _wc = dict(_watcher.combat_state)
                if _ms <= 1:
                    _wc.pop("milestone_action_remaining", None)
                else:
                    _wc["milestone_action_remaining"] = _ms - 1
                _watcher.combat_state = _wc

    event = {
        "type": ServerEvent.DICE_ROLLED,
        "player_id": player.id,
        "roll": roll,
        "result": result,
        "boss_hp": player.current_boss_hp,
        "player_hp": player.hp,
    }

    if boss_defeated:
        # Pass copy_boss_id via a temporary attribute so the helper can access it
        player._copy_boss_id_for_defeat = copy_boss_id
        event["combat_ended"] = True
        event["boss_defeated"] = True
        event["reward_licenze"] = boss.reward_licenze
        event["certification_gained"] = boss.has_certification
        should_return = await _boss_defeat_sequence(player, game, db, boss)
        # Clean up temp attribute
        if hasattr(player, "_copy_boss_id_for_defeat"):
            del player._copy_boss_id_for_defeat
        if should_return:
            return
        # Normal defeat (no instant win, no revive) — fall through to commit+broadcast
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, event)
        await _broadcast_state(game, db)
        return

    elif player_died:
        prevented = await _player_death_sequence(player, game, db, boss)
        if prevented:
            return  # addon 56/59 saved the player — already committed+broadcast
        # Player died — commit current state then notify
        event["combat_ended"] = True
        event["player_died"] = True
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, event)
        await manager.broadcast(game.code, {
            "type": ServerEvent.PLAYER_DIED,
            "player_id": player.id,
        })
        # Ask the dying player to choose which card + addon to lose
        db.refresh(player)
        if player.hand or player.addons:
            from app.models.card import ActionCard as _AC_dc, AddonCard as _ADC_dc
            _dc_hand = []
            for hc in player.hand:
                c = db.get(_AC_dc, hc.action_card_id)
                if c:
                    _dc_hand.append({
                        "hand_card_id": hc.id,
                        "card_id": c.id,
                        "name": c.name,
                        "card_type": c.card_type,
                        "rarity": c.rarity,
                    })
            _dc_addons = []
            for pa in player.addons:
                a = db.get(_ADC_dc, pa.addon_id)
                if a:
                    _dc_addons.append({
                        "player_addon_id": pa.id,
                        "addon_id": a.id,
                        "name": a.name,
                        "effect": a.effect,
                        "is_tapped": pa.is_tapped,
                    })
            await manager.send_to_player(game.code, player.user_id, {
                "type": "death_penalty_choice_required",
                "hand": _dc_hand,
                "addons": _dc_addons,
            })
        await _broadcast_state(game, db)
        return

    db.commit()
    db.refresh(game)
    await manager.broadcast(game.code, event)
    await _broadcast_state(game, db)
