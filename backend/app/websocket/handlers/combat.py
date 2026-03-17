"""
Combat phase handlers: start combat, roll dice, retreat, card/type declaration.
"""
import random
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state, _send_hand_state, _apply_elo,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.models.card import ActionCard, BossCard, AddonCard
from app.game import engine
from app.websocket.reaction_manager import open_reaction_window


async def _handle_start_combat(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.action:
        await _error(game.code, user_id, "Cannot start combat now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if player.is_in_combat:
        await _error(game.code, user_id, "Already in combat")
        return

    # source: "market_1" | "market_2" | "deck_1" | "deck_2"
    source = data.get("source", "market_1")
    if source not in ("market_1", "market_2", "deck_1", "deck_2"):
        await _error(game.code, user_id, "Invalid source (market_1/market_2/deck_1/deck_2)")
        return

    if source == "market_1":
        if not game.boss_market_1:
            await _error(game.code, user_id, "No boss in market slot 1")
            return
        boss_id = game.boss_market_1
    elif source == "market_2":
        if not game.boss_market_2:
            await _error(game.code, user_id, "No boss in market slot 2")
            return
        boss_id = game.boss_market_2
    elif source == "deck_1":
        if not game.boss_deck_1:
            await _error(game.code, user_id, "Boss deck 1 is empty")
            return
        boss_id = game.boss_deck_1.pop(0)
    else:  # deck_2
        if not game.boss_deck_2:
            await _error(game.code, user_id, "Boss deck 2 is empty")
            return
        boss_id = game.boss_deck_2.pop(0)

    boss = db.get(BossCard, boss_id)
    if not boss:
        await _error(game.code, user_id, "Boss not found")
        return

    player.is_in_combat = True
    player.current_boss_id = boss_id
    player.current_boss_source = source
    player.current_boss_hp = boss.hp
    player.combat_round = 0
    # Reset per-combat state; preserve cross-turn flags set by action cards
    _old_cs = player.combat_state or {}
    _persist_cs = {
        k: _old_cs[k] for k in (
            "object_store_licenze", "drip_program_remaining",
            "next_addon_price_fixed", "next_addon_price_discount",
            "next_boss_ability_disabled",   # Card 182 (Interaction Studio): cross-turn flag
            "runtime_manager_ready",        # Card 158 (Runtime Manager): cross-turn survival flag
        ) if k in _old_cs
    }
    player.combat_state = {**_persist_cs, "fought_this_turn": True}
    game.current_phase = TurnPhase.combat

    # Card 182 (Interaction Studio): next boss ability disabled — consume the flag
    _next_boss_ability_disabled = bool((player.combat_state or {}).get("next_boss_ability_disabled"))
    if _next_boss_ability_disabled:
        cs = dict(player.combat_state)
        cs.pop("next_boss_ability_disabled", None)
        player.combat_state = cs

    # Boss 68 (Schema Builder Monstrosity): boss HP increases by 1 for each addon the combatant owns
    if engine.apply_boss_ability(boss_id, "on_combat_start")["bonus_hp_per_player_addon"]:
        player.current_boss_hp = boss.hp + len(player.addons)

    start_effect = engine.apply_boss_ability(boss_id, "on_combat_start")
    if _next_boss_ability_disabled:
        # Neutralize all boss on_combat_start effects
        start_effect = {k: (0 if isinstance(v, int) else False) for k, v in start_effect.items()}

    # Boss 7 (SOQL Vampire) / Boss 61 (Nonprofit Cloud Blight): steal licenze at combat start
    if start_effect["steal_licenze"] > 0:
        player.licenze = max(0, player.licenze - start_effect["steal_licenze"])

    # Boss 2 (Haunted Debug Log): player discards N random cards
    if start_effect["discard_cards"] > 0:
        hand_cards = list(player.hand)
        n_discard = min(start_effect["discard_cards"], len(hand_cards))
        to_discard = random.sample(hand_cards, n_discard)
        for hc in to_discard:
            game.action_discard = (game.action_discard or []) + [hc.action_card_id]
            db.delete(hc)

    # Boss 23 (Tableau Wraith): reveal combatant's hand to all opponents
    if start_effect["reveal_hand"]:
        db.refresh(player)
        hand_reveal = []
        for hc_r in player.hand:
            c_r = db.get(ActionCard, hc_r.action_card_id)
            if c_r:
                hand_reveal.append({"id": c_r.id, "name": c_r.name})
        opponents_uids = [p.user_id for p in game.players if p.id != player.id]
        for opp_uid in opponents_uids:
            await manager.send_to_player(game.code, opp_uid, {
                "type": "hand_revealed",
                "player_id": player.id,
                "hand": hand_reveal,
            })

    # Boss 36 (SOSL Shade): one opponent peeks and discards 1 card from combatant's hand
    if start_effect["opponent_discards_from_hand"] > 0:
        hand_cards_s = list(player.hand)
        to_remove = random.sample(hand_cards_s, min(start_effect["opponent_discards_from_hand"], len(hand_cards_s)))
        for hc_r in to_remove:
            game.action_discard = (game.action_discard or []) + [hc_r.action_card_id]
            db.delete(hc_r)

    # Boss 44 (SSO Doppelganger): random opponent gains 2 licenze at combat start
    if start_effect["opponent_gains_licenza"] > 0:
        opponents = [p for p in game.players if p.id != player.id]
        if opponents:
            random.choice(opponents).licenze += start_effect["opponent_gains_licenza"]

    # Boss 51 (Financial Services Fiend): pay N licenze or take 1 HP per missing licenza
    if start_effect["entry_fee_licenze"] > 0:
        fee = start_effect["entry_fee_licenze"]
        paid = min(fee, player.licenze)
        player.licenze -= paid
        unpaid = fee - paid
        if unpaid > 0:
            player.hp = max(0, player.hp - unpaid)

    # Boss 54 (Workbench Tinkerer): insert N corrupted sentinel cards into combatant's action deck
    # Corrupted cards use negative boss_id as sentinel (e.g. -54); handler checks on draw
    if start_effect["corrupt_deck_cards"] > 0:
        sentinels = [-boss_id] * start_effect["corrupt_deck_cards"]
        if game.action_deck_1:
            insert_pos = random.randint(0, len(game.action_deck_1))
            for s in sentinels:
                game.action_deck_1.insert(random.randint(0, len(game.action_deck_1)), s)

    # Boss 62 (Education Cloud Inquisitor): roll d10 pre-combat — ≥7 +1HP, ≤3 -1HP
    if start_effect["exam_roll"]:
        exam = engine.roll_d10()
        if exam >= 7:
            player.hp = min(player.max_hp, player.hp + 1)
        elif exam <= 3:
            player.hp = max(0, player.hp - 1)

    # Boss 71 (Data Loader Annihilator): remove N random cards from EVERY player's hand
    if start_effect["aoe_discard_all_hands"] > 0:
        for p_aoe in game.players:
            p_hand = list(p_aoe.hand)
            n_rm = min(start_effect["aoe_discard_all_hands"], len(p_hand))
            for hc_rm in random.sample(p_hand, n_rm):
                game.action_discard = (game.action_discard or []) + [hc_rm.action_card_id]
                db.delete(hc_rm)

    # Boss 76 (Sandbox Refresh Catastrophe): discard combatant's entire hand and draw N new cards
    if start_effect["refresh_hand"] > 0:
        for hc_rh in list(player.hand):
            game.action_discard = (game.action_discard or []) + [hc_rh.action_card_id]
            db.delete(hc_rh)
        db.flush()
        from app.models.game import PlayerHandCard
        for _ in range(start_effect["refresh_hand"]):
            if game.action_deck_1:
                db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            elif game.action_deck_2:
                db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))

    # Boss 80 (Certification Exam Executioner): roll 5 × d10; ≥8 → +1HP +2L; ≤4 → -1HP
    if start_effect["certification_exam_rolls"] > 0:
        for _ in range(start_effect["certification_exam_rolls"]):
            r = engine.roll_d10()
            if r >= 8:
                player.hp = min(player.max_hp, player.hp + 1)
                player.licenze += 2
            elif r <= 4:
                player.hp = max(0, player.hp - 1)

    # Boss 88 (Report Builder Omen): reveal next 3 boss cards to all players
    if start_effect["reveal_next_bosses"] > 0:
        preview_ids = (game.boss_deck_1 or [])[:start_effect["reveal_next_bosses"]]
        preview_cards = []
        for bid in preview_ids:
            bc = db.get(BossCard, bid)
            if bc:
                preview_cards.append({"id": bc.id, "name": bc.name, "hp": bc.hp})
        await manager.broadcast(game.code, {
            "type": "boss_preview",
            "player_id": player.id,
            "next_bosses": preview_cards,
        })

    # Boss 92 (Einstein Copilot Seraph): draw 2 extra cards at combat start; each costs 1 HP
    if start_effect["draw_bonus_cards"] > 0:
        from app.models.game import PlayerHandCard as PHC_seraph
        hp_cost_per_draw = engine.boss_draw_costs_hp(boss_id)
        for _ in range(start_effect["draw_bonus_cards"]):
            src = game.action_deck_1 if game.action_deck_1 else game.action_deck_2
            if src:
                db.add(PHC_seraph(player_id=player.id, action_card_id=src.pop(0)))
                if hp_cost_per_draw > 0:
                    player.hp = max(0, player.hp - hp_cost_per_draw)

    # Boss 97 (myTrailhead Defiler): permanently destroy 1 random addon (not recovered on win)
    if start_effect["permanently_destroy_addon"] > 0:
        addons_list = list(player.addons)
        if addons_list:
            pa_destroy = random.choice(addons_list)
            game.addon_graveyard = (game.addon_graveyard or []) + [pa_destroy.addon_id]
            db.delete(pa_destroy)

    # Boss 98 (Dreamforce Aftermath Cataclysm): pool all hands, shuffle, redistribute
    if start_effect["shuffle_all_hands"]:
        from app.models.game import PlayerHandCard as PHC_chaos
        all_players = list(game.players)
        hand_counts = {p.id: len(p.hand) for p in all_players}
        pool = []
        for p_ch in all_players:
            for hc_ch in list(p_ch.hand):
                pool.append(hc_ch.action_card_id)
                db.delete(hc_ch)
        db.flush()
        random.shuffle(pool)
        idx = 0
        for p_ch in all_players:
            for _ in range(hand_counts[p_ch.id]):
                if idx < len(pool):
                    db.add(PHC_chaos(player_id=p_ch.id, action_card_id=pool[idx]))
                    idx += 1

    # Boss 31 (AppExchange Parasite): lock 1 random untapped addon for the fight
    if start_effect["lock_addon"] > 0:
        untapped = [pa for pa in player.addons if not pa.is_tapped]
        if untapped:
            pa_lock = random.choice(untapped)
            pa_lock.is_tapped = True
            cs = dict(player.combat_state or {})
            cs["locked_addon_id"] = pa_lock.id
            player.combat_state = cs

    # Boss 82 (Customer 360 Gorgon): petrify 2 random hand cards (cannot be played this fight)
    if start_effect["petrify_cards"] > 0:
        hand_cards_pet = list(player.hand)
        n_pet = min(start_effect["petrify_cards"], len(hand_cards_pet))
        petrified = [hc.action_card_id for hc in random.sample(hand_cards_pet, n_pet)]
        cs = dict(player.combat_state or {})
        cs["petrified_card_ids"] = petrified
        player.combat_state = cs
        await manager.broadcast(game.code, {
            "type": "cards_petrified",
            "player_id": player.id,
            "count": n_pet,
        })

    # Boss 84 (Data Import Doomsayer): predict fight duration; exceed prediction → extra HP per round
    if start_effect["doomsayer_prediction_roll"]:
        pred_roll = engine.roll_d10()
        if pred_roll <= 4:
            prediction_cap = 2
        elif pred_roll <= 7:
            prediction_cap = 4
        else:
            prediction_cap = 6
        cs = dict(player.combat_state or {})
        cs["doomsayer_prediction_cap"] = prediction_cap
        player.combat_state = cs
        await manager.broadcast(game.code, {
            "type": "boss_doomsayer_prediction",
            "player_id": player.id,
            "prediction_cap": prediction_cap,
        })

    # Boss 91 (List View Usurper): steal 1 random untapped addon; return it on defeat
    # Note: applying the stolen addon's effect against the player requires apply_addon_effect —
    # deferred until that system is implemented. Theft and return are fully tracked.
    if start_effect["steal_and_use_addon"]:
        untapped_91 = [pa for pa in player.addons if not pa.is_tapped]
        if untapped_91:
            pa_steal = random.choice(untapped_91)
            cs = dict(player.combat_state or {})
            cs["stolen_addon_id"] = pa_steal.addon_id
            player.combat_state = cs
            db.delete(pa_steal)
            await manager.broadcast(game.code, {
                "type": "addon_stolen_by_boss",
                "player_id": player.id,
                "boss_id": boss_id,
            })

    # Boss 94 (Loyalty Cloud Warden): initialise loyalty points shield (blocks first 3 hits)
    if engine.boss_loyalty_shield(boss_id) > 0:
        cs = dict(player.combat_state or {})
        cs["loyalty_points"] = engine.boss_loyalty_shield(boss_id)
        player.combat_state = cs

    # Boss 86 (Record Type Ravager): prompt combatant to declare card type before fighting
    if start_effect["force_card_type_declaration"]:
        await manager.send_to_player(game.code, player.user_id, {
            "type": "card_type_declaration_required",
            "player_id": player.id,
            "options": ["Offensiva", "Difensiva"],
        })

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.COMBAT_STARTED,
        "player_id": player.id,
        "boss": {"id": boss.id, "name": boss.name, "hp": boss.hp, "threshold": boss.dice_threshold},
        "boss_effect": {k: v for k, v in start_effect.items() if v},
    })
    await _broadcast_state(game, db)


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
    if round_start["licenza_drain"] > 0:
        player.licenze = max(0, player.licenze - round_start["licenza_drain"])

    # Boss 13 (Flow Builder Gone Rogue): discard 1 card or take 1 HP
    if round_start["force_discard_or_damage"] > 0:
        hand_cards = list(player.hand)
        if hand_cards:
            hc = random.choice(hand_cards)
            game.action_discard = (game.action_discard or []) + [hc.action_card_id]
            db.delete(hc)
        else:
            player.hp = max(0, player.hp - round_start["force_discard_or_damage"])

    # Boss 42 (Revenue Cloud Devourer): drain 1 licenza; if 0 licenze → drain 1 HP
    if round_start["licenza_or_hp_drain"] > 0:
        n = round_start["licenza_or_hp_drain"]
        if player.licenze >= n:
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

    # Boss 93 (Subscription Management Tormentor): pay 1 licenza or take 2 HP
    if round_start["subscription_drain"] > 0:
        n_sub = round_start["subscription_drain"]
        if player.licenze >= n_sub:
            player.licenze -= n_sub
        else:
            player.hp = max(0, player.hp - 2 * n_sub)

    # Boss 100 (Omega): apply last legendary boss's on_round_start effects in parallel
    if engine.boss_is_omega(boss.id) and game.last_defeated_legendary_boss_id:
        omega_rs = engine.apply_boss_ability(
            game.last_defeated_legendary_boss_id, "on_round_start",
            combat_round=current_round,
            cards_played=player.cards_played_this_turn,
        )
        if omega_rs["licenza_drain"] > 0:
            player.licenze = max(0, player.licenze - omega_rs["licenza_drain"])
        if omega_rs["licenza_or_hp_drain"] > 0:
            n = omega_rs["licenza_or_hp_drain"]
            if player.licenze >= n:
                player.licenze -= n
            else:
                player.hp = max(0, player.hp - n)
        if omega_rs["subscription_drain"] > 0:
            ns = omega_rs["subscription_drain"]
            if player.licenze >= ns:
                player.licenze -= ns
            else:
                player.hp = max(0, player.hp - 2 * ns)

    # Boss 55 / Boss 74: apply shadow copy's on_round_start effects
    if copy_boss_id:
        copy_rs = engine.apply_boss_ability(
            copy_boss_id, "on_round_start",
            combat_round=current_round,
            cards_played=player.cards_played_this_turn,
        )
        if copy_rs["licenza_drain"] > 0:
            player.licenze = max(0, player.licenze - copy_rs["licenza_drain"])
        if copy_rs["licenza_or_hp_drain"] > 0:
            n = copy_rs["licenza_or_hp_drain"]
            if player.licenze >= n:
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
            ns = copy_rs["subscription_drain"]
            if player.licenze >= ns:
                player.licenze -= ns
            else:
                player.hp = max(0, player.hp - 2 * ns)

    # Boss 45 (Agentforce Rebellion): hijack 1 random untapped addon — tap it (boss "uses" it)
    # Full inverted-effect application deferred until apply_addon_effect is implemented.
    threshold_bonus = 0
    if round_start["hijack_addon"]:
        untapped_45 = [pa for pa in player.addons if not pa.is_tapped]
        if untapped_45:
            pa_hijack = random.choice(untapped_45)
            pa_hijack.is_tapped = True
            hijacked_addon = db.get(AddonCard, pa_hijack.addon_id)
            await manager.broadcast(game.code, {
                "type": "addon_hijacked_by_boss",
                "player_id": player.id,
                "addon": {"id": hijacked_addon.id, "name": hijacked_addon.name} if hijacked_addon else {},
            })

    # Boss 63 (Loyalty Management Trickster): auto-accept deal — +1 Licenza, threshold +1 this roll
    if round_start["deal_offer"]:
        player.licenze += 1
        threshold_bonus += 1
        await manager.broadcast(game.code, {
            "type": "boss_deal_auto_accepted",
            "player_id": player.id,
            "gained_licenze": 1,
            "threshold_penalty": 1,
        })

    # Boss 83 (Account Engagement Siren): auto-reject siren deal — no HP trade this round
    if round_start["siren_deal"]:
        await manager.broadcast(game.code, {
            "type": "boss_siren_deal_rejected",
            "player_id": player.id,
        })

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

    # Boss 67 (Developer Console Glitch): roll 1 or 2 → entire round is nullified
    round_nullified = engine.boss_nullifies_round_on_low_roll(boss.id) and roll <= 2

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
    threshold = max(1, threshold)  # can't go below 1
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

    # ── Card 27 (Lucky Roll): post-roll reaction window ───────────────────────
    # The player sees the roll result before deciding. Open a window only if:
    #   1. Card 27 is in hand, AND
    #   2. Player still has card budget (cards_played_this_turn < max).
    # Card 26 (Dice Optimizer) already fixed the roll — Lucky Roll cannot override a forced roll.
    if _forced_roll is None:
        _max_cards_lr = (
            engine.boss_max_cards_per_turn(player.current_boss_id, engine.MAX_CARDS_PER_TURN)
            if player.current_boss_id else engine.MAX_CARDS_PER_TURN
        )
        _has_budget = player.cards_played_this_turn < _max_cards_lr
        if _has_budget:
            # Check if player has Lucky Roll (card 27) in hand
            from app.models.card import ActionCard as _AC27
            _lucky_roll_hc = next(
                (hc for hc in player.hand if db.get(_AC27, hc.action_card_id) and
                 db.get(_AC27, hc.action_card_id).number == 27),
                None,
            )
            if _lucky_roll_hc:
                _preview_result = engine.resolve_combat_round(roll, threshold)
                await manager.send_to_player(game.code, user_id, {
                    "type": ServerEvent.REACTION_WINDOW_OPEN,
                    "reason": "lucky_roll",
                    "pending_roll": roll,
                    "pending_result": _preview_result,
                    "threshold": threshold,
                    "timeout_ms": 8000,
                })
                _lr_response = await open_reaction_window(game.code, player.id, timeout=8.0)
                await manager.send_to_player(game.code, user_id, {
                    "type": ServerEvent.REACTION_WINDOW_CLOSED,
                })
                if _lr_response and _lr_response.get("action") == "play":
                    _lr_rhc_id = _lr_response.get("hand_card_id")
                    from app.models.game import PlayerHandCard as _LRPHC
                    _lr_hc = db.get(_LRPHC, _lr_rhc_id)
                    if _lr_hc and _lr_hc.player_id == player.id:
                        _lr_card = db.get(ActionCard, _lr_hc.action_card_id)
                        if _lr_card and _lr_card.number == 27:
                            # Consume Lucky Roll card
                            game.action_discard = (game.action_discard or []) + [_lr_hc.action_card_id]
                            db.delete(_lr_hc)
                            player.cards_played_this_turn += 1
                            # Re-roll: take the new result regardless of whether it's better
                            roll = engine.roll_d10()
                            round_nullified = engine.boss_nullifies_round_on_low_roll(boss.id) and roll <= 2
                            await manager.broadcast(game.code, {
                                "type": ServerEvent.LUCKY_ROLL_USED,
                                "player_id": player.id,
                                "new_roll": roll,
                            })

    # Card 98 (Pause Element): round_nullified override — consumes 1 round of the flag
    if (player.combat_state or {}).get("pause_element_rounds_remaining", 0) > 0:
        cs = dict(player.combat_state)
        cs["pause_element_rounds_remaining"] -= 1
        if cs["pause_element_rounds_remaining"] <= 0:
            cs.pop("pause_element_rounds_remaining", None)
        player.combat_state = cs
        round_nullified = True

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
    player.combat_round += 1

    player_took_damage = False

    # Card 12 (Governor Limit Exploit): double boss damage per successful hit for N rounds
    _hit_damage = 2 if (player.combat_state or {}).get("double_damage_until_round", 0) >= current_round else 1
    # Card 61 (Predictive Model): exact prediction on hit → at least 2HP damage
    if _predictive_bonus and _hit_damage < 2:
        _hit_damage = 2
    # Card 28 (Critical System): roll of exactly 10 deals 3 HP to boss (overrides all other modifiers)
    if (player.combat_state or {}).get("critical_system_until_round", 0) >= current_round and roll == 10:
        _hit_damage = 3
    # Card 127 (Omni-Channel): next hit deals +1 HP to boss (stacks with other bonuses unless critical_system)
    if (player.combat_state or {}).get("omni_channel_next_hit_bonus") and _hit_damage < 3:
        _hit_damage += 1
        cs = dict(player.combat_state)
        cs.pop("omni_channel_next_hit_bonus", None)
        player.combat_state = cs

    if round_nullified:
        # No damage in either direction this round
        pass
    elif result == "hit":
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
        # Card 148 (Loop Element): track hits dealt for damage scaling
        _cs_hit = dict(player.combat_state or {})
        _cs_hit["combat_hits_dealt"] = _cs_hit.get("combat_hits_dealt", 0) + 1
        player.combat_state = _cs_hit
        # Card 169 (Model Builder): reset consecutive miss counter on hit
        if (player.combat_state or {}).get("model_builder_active"):
            _cs_mb_hit = dict(player.combat_state)
            _cs_mb_hit["consecutive_misses"] = 0
            player.combat_state = _cs_mb_hit
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
        # Card 97 (Fault Path): on miss gain 1L instead of taking HP damage (for whole combat)
        elif (player.combat_state or {}).get("fault_path_active"):
            player.licenze += 1
        # Boss 95 (Identity & Access Heretic): player damage redirected to random opponent
        elif engine.boss_redirects_damage_to_opponent(boss.id):
            opponents_redir = [p for p in game.players if p.id != player.id]
            if opponents_redir:
                target_redir = random.choice(opponents_redir)
                target_redir.hp = max(0, target_redir.hp - 1)
        else:
            _player_hp_damage = 1
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
            # Card 153 (Environment Branch): skip HP damage once, then clear
            elif _player_hp_damage > 0 and (player.combat_state or {}).get("environment_branch_active"):
                _player_hp_damage = 0
                _cs_eb = dict(player.combat_state)
                _cs_eb.pop("environment_branch_active", None)
                player.combat_state = _cs_eb
            # Card 156 (Travel Time Calc): if roll exactly == threshold-1, skip damage
            elif _player_hp_damage > 0 and (player.combat_state or {}).get("travel_time_calc_active") and roll == threshold - 1:
                _player_hp_damage = 0
                _cs_tt = dict(player.combat_state)
                _cs_tt.pop("travel_time_calc_active", None)
                player.combat_state = _cs_tt
            # Card 258 (Salesforce Tower): HP cannot drop below 1 this turn
            if (player.combat_state or {}).get("salesforce_tower_active"):
                player.hp = max(1, player.hp - _player_hp_damage)
            else:
                player.hp = max(0, player.hp - _player_hp_damage)
            player_took_damage = True
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
                if game.action_deck_1:
                    db.add(_PHC133(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
                elif game.action_deck_2:
                    db.add(_PHC133(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
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

    # Card 240 (Batch Scope): apply 1HP DOT per round while counter > 0
    if (player.combat_state or {}).get("batch_scope_dot_rounds", 0) > 0:
        player.current_boss_hp = max(0, (player.current_boss_hp or 0) - 1)
        _cs_bs = dict(player.combat_state)
        _cs_bs["batch_scope_dot_rounds"] = _cs_bs["batch_scope_dot_rounds"] - 1
        if _cs_bs["batch_scope_dot_rounds"] <= 0:
            _cs_bs.pop("batch_scope_dot_rounds", None)
        player.combat_state = _cs_bs

    # Card 191 (Autolaunched Flow): if player HP just dropped below 2, trigger auto-shot on boss
    if (player.combat_state or {}).get("autolaunched_flow_ready") and player.hp < 2:
        player.current_boss_hp = max(0, (player.current_boss_hp or 0) - 1)
        _cs_af = dict(player.combat_state)
        _cs_af.pop("autolaunched_flow_ready", None)
        player.combat_state = _cs_af

    # Card 169 (Model Builder): track consecutive misses; after 3, force next roll = 10
    if result == "miss" and (player.combat_state or {}).get("model_builder_active"):
        _cs_mb = dict(player.combat_state)
        _cs_mb["consecutive_misses"] = _cs_mb.get("consecutive_misses", 0) + 1
        if _cs_mb["consecutive_misses"] >= 3:
            _cs_mb["next_roll_forced"] = 10
            _cs_mb["consecutive_misses"] = 0
        player.combat_state = _cs_mb

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
            if game.action_deck_1:
                db.add(PHC_draw(player_id=target_draw.id, action_card_id=game.action_deck_1.pop(0)))
            elif game.action_deck_2:
                db.add(PHC_draw(player_id=target_draw.id, action_card_id=game.action_deck_2.pop(0)))

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
                return  # combat continues — boss revived, skip all reward steps

        # Boss 34 (Batch Apex Necromancer): first defeat re-inserts boss into deck — no rewards
        if defeated_effect["boss_revive_to_deck"] > 0:
            cs = dict(player.combat_state or {})
            if not cs.get("necromancer_resurrected", False):
                cs["necromancer_resurrected"] = True
                player.combat_state = cs
                if player.current_boss_source in ("deck_1", "market_1"):
                    game.boss_deck_1 = (game.boss_deck_1 or []) + [boss.id]
                else:
                    game.boss_deck_2 = (game.boss_deck_2 or []) + [boss.id]
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
                return  # combat ended — boss re-inserted, no rewards

        # Step 2: award Licenze reward
        player.licenze += boss.reward_licenze
        # Card 262 (World Tour Event): bonus +2L on boss defeat if event active; first combatant +1L extra
        if (player.combat_state or {}).get("world_tour_event_active"):
            player.licenze += 2
            if (player.combat_state or {}).get("world_tour_event_first_bonus"):
                player.licenze += 1
                _cs_wte = dict(player.combat_state)
                _cs_wte.pop("world_tour_event_first_bonus", None)
                player.combat_state = _cs_wte

        # Card 273 (Trailhead Quest): +5L if no cards played this turn
        if (player.combat_state or {}).get("trailhead_quest_active") and player.cards_played_this_turn == 0:
            player.licenze += 5
            _cs_tq = dict(player.combat_state)
            _cs_tq.pop("trailhead_quest_active", None)
            _cs_tq.pop("trailhead_quest_cards_played", None)
            player.combat_state = _cs_tq
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

        # Step 3: award Certification (if cert boss)
        if boss.has_certification:
            player.certificazioni += 1

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
            game.status = GameStatus.finished
            game.winner_id = player.id
            from datetime import datetime, timezone
            game.finished_at = datetime.now(timezone.utc)
            _apply_elo(game, player.id, db)
            db.commit()
            await manager.broadcast(game.code, {"type": ServerEvent.GAME_OVER, "winner_id": player.id})
            await _broadcast_state(game, db)
            return
        # Boss 31 (AppExchange Parasite): unlock locked addon (untap it)
        # Boss 91 (List View Usurper): return stolen addon to player's possession
        if defeated_effect["unlock_locked_addon"] and player.combat_state:
            cs = player.combat_state
            locked_pa_id = cs.get("locked_addon_id")
            stolen_addon_id = cs.get("stolen_addon_id")
            if locked_pa_id:
                from app.models.game import PlayerAddon as _PA
                pa_unlock = db.get(_PA, locked_pa_id)
                if pa_unlock and pa_unlock.player_id == player.id:
                    pa_unlock.is_tapped = False
            if stolen_addon_id:
                from app.models.game import PlayerAddon as _PA2
                db.add(_PA2(player_id=player.id, addon_id=stolen_addon_id))
        # Boss 82 (Customer 360 Gorgon): clear petrified cards on defeat
        if player.combat_state and player.combat_state.get("petrified_card_ids"):
            cs = dict(player.combat_state)
            cs.pop("petrified_card_ids", None)
            player.combat_state = cs
        # Card 139 (Prospect Lifecycle): boss defeat lifts the addon purchase block
        if player.combat_state and player.combat_state.get("addons_blocked_until_boss_defeat"):
            cs = dict(player.combat_state)
            cs.pop("addons_blocked_until_boss_defeat", None)
            player.combat_state = cs
        # Boss 55 / Boss 74: also apply shadow copy's on_boss_defeated effects
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
            game.boss_market_1 = game.boss_deck_1.pop(0) if game.boss_deck_1 else None
        elif source == "market_2":
            game.boss_market_2 = game.boss_deck_2.pop(0) if game.boss_deck_2 else None

        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        player.current_boss_source = None
        game.current_phase = TurnPhase.action

        event["combat_ended"] = True
        event["boss_defeated"] = True
        event["reward_licenze"] = boss.reward_licenze
        event["certification_gained"] = boss.has_certification

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
            return

    elif player_died:
        # Apply death penalty
        hand_ids = [hc.action_card_id for hc in player.hand]
        addon_ids = [pa.addon_id for pa in player.addons]
        penalty = engine.apply_death_penalty(hand_ids, player.licenze, addon_ids)

        # Boss 14 (Great Data Reaper): death costs 2 Licenze instead of 1
        extra_licenza_loss = engine.boss_death_licenze_penalty(boss.id) - engine.DEATH_LOSE_LICENZE
        if extra_licenza_loss > 0:
            penalty["licenze"] = max(0, penalty["licenze"] - extra_licenza_loss)
            penalty["lost"]["licenza"] = penalty["lost"].get("licenza", 0) + extra_licenza_loss

        # Boss 57 (Named Credentials Thief): lost licenze go to the opponent with most certs
        if engine.boss_death_licenze_to_top_cert(boss.id):
            licenza_lost = penalty["lost"].get("licenza", 0)
            if licenza_lost > 0:
                opponents_cert = [p for p in game.players if p.id != player.id]
                if opponents_cert:
                    top = max(opponents_cert, key=lambda p: p.certificazioni)
                    top.licenze += licenza_lost

        # Boss 66 (Deploy to Production Nemesis): death costs 2 addons instead of 1
        addons_to_lose = engine.boss_death_addon_penalty(boss.id)
        if addons_to_lose > engine.DEATH_LOSE_ADDONS:
            # Lose extra addons beyond the one already in penalty["lost"]
            extra_addons = addons_to_lose - engine.DEATH_LOSE_ADDONS
            remaining_addons = [pa for pa in player.addons if pa.addon_id != penalty["lost"].get("addon")]
            for pa_extra in random.sample(remaining_addons, min(extra_addons, len(remaining_addons))):
                game.addon_graveyard = (game.addon_graveyard or []) + [pa_extra.addon_id]
                db.delete(pa_extra)

        # Remove lost card from hand
        if "card" in penalty["lost"]:
            lost_card_id = penalty["lost"]["card"]
            hc_to_remove = next((hc for hc in player.hand if hc.action_card_id == lost_card_id), None)
            if hc_to_remove:
                game.action_discard = (game.action_discard or []) + [lost_card_id]
                db.delete(hc_to_remove)

        # Remove lost addon
        if "addon" in penalty["lost"]:
            lost_addon_id = penalty["lost"]["addon"]
            pa_to_remove = next((pa for pa in player.addons if pa.addon_id == lost_addon_id), None)
            if pa_to_remove:
                game.addon_graveyard = (game.addon_graveyard or []) + [lost_addon_id]
                db.delete(pa_to_remove)

        player.licenze = penalty["licenze"]
        player.hp = player.max_hp  # respawn with full HP

        # GDD §6: tutti gli AddOn rimanenti si tappano alla morte
        # Card 84 (Renewal Opportunity): first addon is spared if player paid 5L proactively
        _renewal = (player.combat_state or {}).get("renewal_protected", False)
        _first_addon_spared = False
        for pa_death in player.addons:
            if _renewal and not _first_addon_spared:
                _first_addon_spared = True
                continue  # protect this one addon from tapping
            pa_death.is_tapped = True
        if _renewal:
            cs_ren = dict(player.combat_state)
            cs_ren.pop("renewal_protected", None)
            player.combat_state = cs_ren

        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        # Boss goes back to top of the deck it came from (market bosses stay in market)
        source = player.current_boss_source
        if source == "deck_1":
            game.boss_deck_1 = [boss.id] + (game.boss_deck_1 or [])
        elif source == "deck_2":
            game.boss_deck_2 = [boss.id] + (game.boss_deck_2 or [])
        # market_1 / market_2: boss stays in market, nothing to do
        player.current_boss_source = None
        game.current_phase = TurnPhase.action

        event["combat_ended"] = True
        event["player_died"] = True
        event["penalty"] = penalty["lost"]

        await manager.broadcast(game.code, event)
        await manager.broadcast(game.code, {
            "type": ServerEvent.PLAYER_DIED,
            "player_id": player.id,
            "lost": penalty["lost"],
        })
        db.commit()
        db.refresh(game)
        db.refresh(player)
        await _broadcast_state(game, db)
        await _send_hand_state(game.code, player, db)
        return

    db.commit()
    db.refresh(game)
    await manager.broadcast(game.code, event)
    await _broadcast_state(game, db)


async def _handle_retreat(game: GameSession, user_id: int, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.combat:
        await _error(game.code, user_id, "Not in combat")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player) or not player.is_in_combat:
        await _error(game.code, user_id, "Not your combat")
        return

    # Boss 66 (Deploy to Production Nemesis): retreat is permanently blocked
    if engine.boss_blocks_retreat(player.current_boss_id):
        await _error(game.code, user_id, "Retreat blocked by boss ability")
        return

    boss_id = player.current_boss_id
    source = player.current_boss_source
    # Boss goes back to its origin: deck → top of that deck; market → back to its market slot
    if source == "deck_1":
        game.boss_deck_1 = [boss_id] + (game.boss_deck_1 or [])
    elif source == "deck_2":
        game.boss_deck_2 = [boss_id] + (game.boss_deck_2 or [])
    elif source == "market_1":
        game.boss_market_1 = boss_id
    elif source == "market_2":
        game.boss_market_2 = boss_id
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
        "retreated": True,
    })
    await _broadcast_state(game, db)


async def _handle_declare_card(game: GameSession, user_id: int, data: dict, db: Session):
    """Boss 33 (Experience Cloud Illusion): player declares which hand card they'll play
    BEFORE rolling the dice.  If the roll is a miss, the declared card is consumed.
    Must be sent after start_combat and before roll_dice each round."""
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.combat:
        await _error(game.code, user_id, "Not in combat phase")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player) or not player.is_in_combat:
        await _error(game.code, user_id, "Not your combat")
        return

    if not engine.boss_card_declared_before_roll(player.current_boss_id):
        await _error(game.code, user_id, "Current boss does not require card declaration")
        return

    hand_card_id = data.get("hand_card_id")
    from app.models.game import PlayerHandCard
    hc = db.get(PlayerHandCard, hand_card_id)
    if not hc or hc.player_id != player.id:
        await _error(game.code, user_id, "Card not in hand")
        return

    cs = dict(player.combat_state or {})
    cs["declared_card_id"] = hc.action_card_id
    cs["declared_hand_card_id"] = hc.id
    player.combat_state = cs
    db.commit()

    card = db.get(ActionCard, hc.action_card_id)
    await manager.broadcast(game.code, {
        "type": "card_declared_before_roll",
        "player_id": player.id,
        "card": {"id": card.id, "name": card.name} if card else {},
    })


async def _handle_declare_card_type(game: GameSession, user_id: int, data: dict, db: Session):
    """Boss 86 (Record Type Ravager): player declares which card type they'll use
    for the rest of this combat (Offensiva or Difensiva).  Only cards of that type
    may be played until the boss is defeated or player dies/retreats."""
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.combat:
        await _error(game.code, user_id, "Not in combat phase")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player) or not player.is_in_combat:
        await _error(game.code, user_id, "Not your combat")
        return

    boss = db.get(BossCard, player.current_boss_id)
    if not boss or boss.id != 86:
        await _error(game.code, user_id, "Current boss does not require card type declaration")
        return

    card_type = data.get("card_type")
    if card_type not in ("Offensiva", "Difensiva"):
        await _error(game.code, user_id, "card_type must be 'Offensiva' or 'Difensiva'")
        return

    cs = dict(player.combat_state or {})
    cs["allowed_card_type"] = card_type
    player.combat_state = cs
    db.commit()

    await manager.send_to_player(game.code, user_id, {
        "type": "card_type_declared",
        "player_id": player.id,
        "allowed_card_type": card_type,
    })
