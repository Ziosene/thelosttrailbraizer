"""
Combat start handler: _handle_start_combat
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
from app.game.engine_addons import has_addon as _has_addon_start
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

    if player.hp == 0:
        await _error(game.code, user_id, "Non puoi combattere: sei morto questo turno")
        return

    # Regola base: un solo combattimento per turno
    # Carte/addon possono concedere combattimenti extra impostando extra_combat_remaining > 0
    _cs_pre = player.combat_state or {}
    if _cs_pre.get("fought_this_turn"):
        _extra = _cs_pre.get("extra_combat_remaining", 0)
        if _extra <= 0:
            await _error(game.code, user_id, "Hai già combattuto questo turno")
            return
        # Consuma un combattimento extra
        _cs_new = dict(_cs_pre)
        _cs_new["extra_combat_remaining"] = _extra - 1
        player.combat_state = _cs_new

    # Addon 191 (404 Not Found): cannot start combat while active
    if (player.combat_state or {}).get('not_found_active'):
        await _error(game.code, user_id, "Cannot start combat while 404 Not Found is active")
        return

    # Card 74 (Routing Configuration): if player has routing_assigned_boss_id, must fight that boss
    _cs_routing = player.combat_state or {}
    _routing_boss_id = _cs_routing.get("routing_assigned_boss_id")
    if _routing_boss_id:
        # Force boss_id and skip normal source logic
        boss = db.get(BossCard, _routing_boss_id)
        if not boss:
            await _error(game.code, user_id, "Routed boss not found in DB")
            return
        # Remove from whatever deck it's still in (or market)
        _found_in_deck = False
        for _deck_attr in ("boss_deck_1", "boss_deck_2"):
            _deck = list(getattr(game, _deck_attr) or [])
            if _routing_boss_id in _deck:
                _deck.remove(_routing_boss_id)
                setattr(game, _deck_attr, _deck)
                _found_in_deck = True
                break
        # Mark routing as consumed
        _cs_routing_new = dict(_cs_routing)
        _cs_routing_new.pop("routing_assigned_boss_id", None)
        _cs_routing_new.pop("routing_assigned", None)
        player.combat_state = _cs_routing_new
        player.is_in_combat = True
        player.current_boss_id = _routing_boss_id
        player.current_boss_hp = boss.hp
        player.current_boss_source = data.get("source", "deck_1")
        db.commit()
        db.refresh(game)
        from app.websocket.connection_manager import manager as _mgr_routing
        await _mgr_routing.broadcast(game.code, {
            "type": "combat_started",
            "player_id": user_id,
            "boss_id": _routing_boss_id,
            "boss_name": boss.name,
            "boss_hp": boss.hp,
            "routed": True,
        })
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

    # Addon 83 (Sandbox Preview): peek dice threshold of next boss before drawing
    if _has_addon_start(player, 83) and source in ("deck_1", "deck_2"):
        _peek_deck83 = (game.boss_deck_1 if source == "deck_1" else game.boss_deck_2) or []
        # Note: boss_id already popped above for deck sources; peek at current boss_id
        from app.models.card import BossCard as _Boss83
        _peek_boss83 = db.get(_Boss83, boss_id)
        if _peek_boss83:
            await manager.broadcast(game.code, {
                "type": "sandbox_preview",
                "player_id": player.id,
                "boss_threshold": _peek_boss83.dice_threshold,
            })

    # Addon 60 (Release Notes): if boss drawn from deck, peek stats before deciding to fight
    _boss_drawn_from_deck60 = source in ("deck_1", "deck_2")
    if _has_addon_start(player, 60) and _boss_drawn_from_deck60:
        cs60 = dict(player.combat_state or {})
        cs60["release_notes_pending_boss_id"] = boss_id
        cs60["release_notes_pending_source"] = source
        player.combat_state = cs60
        # Return boss to top of its deck
        if source == "deck_1":
            game.boss_deck_1 = [boss_id] + (game.boss_deck_1 or [])
        else:
            game.boss_deck_2 = [boss_id] + (game.boss_deck_2 or [])
        player.is_in_combat = False
        player.current_boss_id = None
        game.current_phase = TurnPhase.action
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "release_notes_peek",
            "player_id": player.id,
            "boss_id": boss.id,
            "boss_name": boss.name,
            "boss_hp": boss.hp,
            "boss_threshold": boss.dice_threshold,
            "boss_effect": boss.effect,
        })
        await _broadcast_state(game, db)
        return

    player.is_in_combat = True
    player.current_boss_id = boss_id
    player.current_boss_source = source
    player.current_boss_hp = boss.hp
    player.combat_round = 0

    # Addon 84 (Governor Limit Enforcer): boss HP is capped at 4
    if _has_addon_start(player, 84):
        player.current_boss_hp = min(player.current_boss_hp, 4)

    # Addon 197 (The Lost Trailblazer Fragment): sole holder vs Omega boss gets -3HP
    if _has_addon_start(player, 197):
        _others197 = [p for p in game.players if p.id != player.id and _has_addon_start(p, 197)]
        if not _others197:
            _boss197 = db.get(BossCard, player.current_boss_id) if player.current_boss_id else None
            if _boss197 and ('omega' in (_boss197.name or '').lower() or 'lost trailblazer' in (_boss197.name or '').lower()):
                player.current_boss_hp = max(1, (player.current_boss_hp or 0) - 3)
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
    _new_cs = {**_persist_cs, "fought_this_turn": True}
    # Addon 7 (Flow Automation): track no-damage combat for bonus on defeat
    if _has_addon_start(player, 7):
        _new_cs["no_damage_this_combat"] = True
    # Addon 39 (Streaming API Buffer): first miss of combat absorbed by buffer
    if _has_addon_start(player, 39):
        _new_cs["buffer_active"] = True
    player.combat_state = _new_cs
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

    # Boss 91 (List View Usurper): hide combatant's hand for the whole fight
    if start_effect["hand_hidden_in_combat"]:
        cs = dict(player.combat_state or {})
        cs["hand_hidden_in_combat"] = True
        player.combat_state = cs
        await manager.send_to_player(game.code, player.user_id, {
            "type": "hand_hidden",
            "player_id": player.id,
            "reason": "list_view_usurper",
        })

    # Boss 94 (Loyalty Cloud Warden): initialise loyalty points shield (blocks first 3 hits)
    if engine.boss_loyalty_shield(boss_id) > 0:
        cs = dict(player.combat_state or {})
        cs["loyalty_points"] = engine.boss_loyalty_shield(boss_id)
        player.combat_state = cs

    # Boss 86 (Record Type Ravager): player declares Offensiva or Difensiva — only that type allowed
    if start_effect["force_card_type_declaration"]:
        await manager.send_to_player(game.code, player.user_id, {
            "type": "boss86_declaration_required",
            "player_id": player.id,
            "options": ["Offensiva", "Difensiva"],
        })
        _b86_resp = await open_reaction_window(game.code, player.id, timeout=20.0)
        _b86_declared = None
        if _b86_resp and _b86_resp.get("action") == "declare":
            _b86_declared = _b86_resp.get("card_type")
            if _b86_declared not in ("Offensiva", "Difensiva"):
                _b86_declared = None
        cs_b86 = dict(player.combat_state or {})
        cs_b86["allowed_card_type"] = _b86_declared  # None = no restriction (timed out)
        player.combat_state = cs_b86
        await manager.broadcast(game.code, {
            "type": "boss86_declaration_made",
            "player_id": player.id,
            "declared_type": _b86_declared,
        })

    # Boss 53 (Einstein Discovery Oracle): ask combatant to predict fight duration in rounds
    if start_effect["request_round_prediction"]:
        await manager.send_to_player(game.code, player.user_id, {
            "type": "oracle_prediction_request",
            "player_id": player.id,
            "timeout_ms": 15000,
        })
        pred_response = await open_reaction_window(game.code, player.id, timeout=15.0)
        if pred_response and pred_response.get("action") == "predict":
            predicted = pred_response.get("rounds")
            if isinstance(predicted, int) and predicted > 0:
                cs = dict(player.combat_state or {})
                cs["oracle_predicted_rounds"] = predicted
                player.combat_state = cs

    # Addon 145 (Risk Matrix): before each combat, roll a "risk die"
    if _has_addon_start(player, 145):
        _risk_roll145 = engine.roll_d10()
        cs145 = dict(player.combat_state or {})
        if _risk_roll145 >= 7:
            cs145["risk_matrix_reward"] = True  # gain L per boss base HP at defeat
        elif _risk_roll145 <= 3:
            player.licenze = max(0, player.licenze - 1)
        player.combat_state = cs145
        await manager.broadcast(game.code, {
            "type": "risk_matrix_roll",
            "player_id": player.id,
            "roll": _risk_roll145,
        })

    # Addon 52 (Scratch Org): draw 1 extra action card at start of each combat
    if _has_addon_start(player, 52):
        from app.models.game import PlayerHandCard as _PHC52
        _extra52 = None
        if game.action_deck_1:
            _extra52 = game.action_deck_1.pop(0)
        elif game.action_deck_2:
            _extra52 = game.action_deck_2.pop(0)
        if _extra52 is not None:
            db.add(_PHC52(player_id=player.id, action_card_id=_extra52))

    # Addon 114 (Event Bus): when any player draws a boss, all players with addon 114 draw 1 action card
    from app.models.game import PlayerHandCard as _PHC114
    for _p114 in game.players:
        if _has_addon_start(_p114, 114):
            _cid114 = None
            if game.action_deck_1:
                _cid114 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _cid114 = game.action_deck_2.pop(0)
            if _cid114:
                db.add(_PHC114(player_id=_p114.id, action_card_id=_cid114))

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.COMBAT_STARTED,
        "player_id": player.id,
        "boss": {"id": boss.id, "name": boss.name, "hp": boss.hp, "threshold": boss.dice_threshold},
        "boss_effect": {k: v for k, v in start_effect.items() if v},
    })
    await _broadcast_state(game, db)
