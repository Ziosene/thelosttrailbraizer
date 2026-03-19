"""
Addon handlers: buy addon and use addon.
"""
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.models.card import AddonCard, BossCard
from app.game import engine
from app.game.engine_addons import has_addon as _has_addon_addon


async def _handle_buy_addon(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Cannot buy addon now")
        return
    # Addon 111 (Quick Deploy): allow buying addons during combat phase too
    _player_111 = _get_player(game, user_id)
    _allow_combat_buy = _player_111 and _has_addon_addon(_player_111, 111)
    if game.current_phase not in (TurnPhase.action,) and not (game.current_phase == TurnPhase.combat and _allow_combat_buy):
        await _error(game.code, user_id, "Cannot buy addon now")
        return

    player = _get_player(game, user_id)
    _fomo_bypass = player and (player.combat_state or {}).get("fomo_bypass_turn", False)
    if not player or (not _is_player_turn(game, player) and not _fomo_bypass):
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
    # Addon 139 (Unmanaged Package): market costs +2L for all opponents of the player with this addon
    for _p139 in game.players:
        if _p139.id != player.id and _has_addon_addon(_p139, 139):
            cost += 2
            break  # one player with addon 139 is enough
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
    # Addon 80 (Field Dependency): if ≥3 addons owned, -2L on addon cost
    if _has_addon_addon(player, 80) and len(player.addons) >= 3:
        cost = max(0, cost - 2)

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

    # Addon 124 (Bulk API): check once-per-game bulk purchase slots
    _cs_buy124 = player.combat_state or {}
    _bulk_remaining = _cs_buy124.get("bulk_api_purchases_remaining", 0)
    if _bulk_remaining > 0:
        # Allow extra purchase, decrement counter
        _cs_new_buy124 = dict(_cs_buy124)
        _cs_new_buy124["bulk_api_purchases_remaining"] -= 1
        player.combat_state = _cs_new_buy124
    else:
        # Normal: check once-per-turn limit (not blocking for now — game uses bought_addon_this_turn
        # purely for information; actual enforcement done below if needed)
        pass

    # Bought addons are tracked as owned by player; market slot gets refilled
    if source == "market_1":
        game.addon_market_1 = game.addon_deck_1.pop(0) if game.addon_deck_1 else None
    elif source == "market_2":
        game.addon_market_2 = game.addon_deck_2.pop(0) if game.addon_deck_2 else None
    # deck_1 / deck_2: card already popped above, nothing else to do

    from app.models.game import PlayerAddon
    db.add(PlayerAddon(player_id=player.id, addon_id=addon_id))

    # Addon 11 (Revenue Intelligence): other players with this addon earn +1L on each addon purchase
    for _other11 in game.players:
        if _other11.id != player.id and _has_addon_addon(_other11, 11):
            _other11.licenze += 1

    # Addon 12 (CPQ Engine): buying this addon sets next purchase to 5L
    if addon.number == 12:
        _cs12 = dict(player.combat_state or {})
        _cs12["next_addon_price_fixed"] = 5
        player.combat_state = _cs12

    # Addon 58 (High Availability): initialize 2 miss-absorb charges when acquired
    if addon.number == 58:
        _cs58_buy = dict(player.combat_state or {})
        _cs58_buy["ha_misses_remaining"] = 2
        player.combat_state = _cs58_buy

    # Card 160 (Storefront Reference): mark that this player bought an addon this turn
    _cs_bat = dict(player.combat_state or {})
    _cs_bat["bought_addon_this_turn"] = True
    player.combat_state = _cs_bat

    # TODO: triggherare gli addon passivi con trigger "quando acquisti un addon" (sia il nuovo che quelli già posseduti).
    # Alcuni addon esistenti danno bonus al momento dell'acquisto di un nuovo addon.
    # Va chiamata trigger_passive_addons(event="on_addon_bought", player, game, new_addon=addon, db).

    # Flush so we can reference the new PlayerAddon id for addon 92
    db.flush()
    from app.models.game import PlayerAddon as _PA_bought
    new_pa = db.query(_PA_bought).filter(
        _PA_bought.player_id == player.id,
        _PA_bought.addon_id == addon_id,
    ).order_by(_PA_bought.id.desc()).first()

    # Track addon acquisition turn for addon 133 (Winter Release) and 136 (Package Upgrade)
    # Always record acquisition turn in buyer's combat_state so future addons are covered
    if new_pa:
        _cs_acq = dict(player.combat_state or {})
        _aq_turns = dict(_cs_acq.get("addon_acquired_turns", {}))
        _aq_turns[str(new_pa.id)] = game.turn_number
        _cs_acq["addon_acquired_turns"] = _aq_turns
        player.combat_state = _cs_acq

    # Addon 151 (Certification Path): when this addon is bought, set pending flag for first cert
    if addon.number == 151:
        cs151_buy = dict(player.combat_state or {})
        cs151_buy["cert_path_double_pending"] = True
        player.combat_state = cs151_buy

    # Addon 92 (Beta Feature): offer to reject just-bought addon and draw another
    if _has_addon_addon(player, 92) and new_pa:
        cs92 = dict(player.combat_state or {})
        cs92["beta_feature_pending_pa_id"] = new_pa.id
        cs92["beta_feature_pending_addon_id"] = addon_id
        player.combat_state = cs92
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "beta_feature_option",
            "addon_card_id": addon_id,
            "message": "You can reject this addon and draw another",
        })
        await _broadcast_state(game, db)
        return

    # Addon 110 (Go-Live Celebration): all players gain 1L on any addon purchase
    for _p110 in game.players:
        if _has_addon_addon(_p110, 110):
            _cs110 = _p110.combat_state or {}
            _first110 = not _cs110.get("go_live_bought_this_turn")
            for _all110 in game.players:
                _all110.licenze += 1
            if player.id == _p110.id and _first110:
                player.licenze += 2  # extra 2 (already got 1 from loop above, total 3)
            _cs110_new = dict(_cs110)
            _cs110_new["go_live_bought_this_turn"] = True
            _p110.combat_state = _cs110_new
            break

    # Addon 147 (FOMO Trigger): when any opponent buys an addon, others with 147 can buy one immediately
    for _p147 in game.players:
        if _p147.id != player.id and _has_addon_addon(_p147, 147):
            cs147 = dict(_p147.combat_state or {})
            cs147["fomo_trigger_pending"] = True
            _p147.combat_state = cs147

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

    # Addon 150 (Wildcards): skip tap check if wildcards active
    _wildcards_active = (player.combat_state or {}).get("wildcards_active", False)
    if pa.is_tapped and not _wildcards_active:
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

    # Addon 150 (Wildcards): don't tap addons when wildcards active
    if not _wildcards_active:
        pa.is_tapped = True

    # Addon 72 (Process Builder Chain): track active addon usage; gain +2L on second use
    if _has_addon_addon(player, 72) and addon.addon_type.value == "Attivo":
        _cs72 = dict(player.combat_state or {})
        _cs72["addons_used_this_turn"] = _cs72.get("addons_used_this_turn", 0) + 1
        if _cs72["addons_used_this_turn"] == 2:
            player.licenze += 2
        player.combat_state = _cs72

    # Addon 73 (Trigger Handler): other players with this addon gain +1L when any active addon is used
    for _other73 in game.players:
        if _other73.id != player.id and _has_addon_addon(_other73, 73):
            _other73.licenze += 1

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

    # ── Active addon effects (1-20) ──────────────────────────────────────────

    # Addon 3 (Einstein Prediction): reroll next dice roll (flag consumed in roll.py)
    if addon.number == 3:
        if not player.is_in_combat:
            await _error(game.code, user_id, "Einstein Prediction can only be used during combat")
            pa.is_tapped = False
            return
        _cs3 = dict(player.combat_state or {})
        _cs3["einstein_prediction_pre_reroll"] = True
        player.combat_state = _cs3

    # Addon 9 (Debug Mode): once per game, send boss back to bottom of deck
    elif addon.number == 9:
        _cs9 = player.combat_state or {}
        if _cs9.get("debug_mode_used"):
            await _error(game.code, user_id, "Debug Mode already used this game")
            pa.is_tapped = False
            return
        if not player.is_in_combat or not player.current_boss_id:
            await _error(game.code, user_id, "Debug Mode can only be used when in combat (right after drawing a boss)")
            pa.is_tapped = False
            return
        boss_id_9 = player.current_boss_id
        source_9 = player.current_boss_source
        if source_9 in ("deck_1", "market_1"):
            game.boss_deck_1 = (game.boss_deck_1 or []) + [boss_id_9]
        else:
            game.boss_deck_2 = (game.boss_deck_2 or []) + [boss_id_9]
        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        player.current_boss_source = None
        player.combat_round = None
        from app.models.game import TurnPhase as _TP9
        game.current_phase = _TP9.action
        cs9_new = dict(_cs9)
        cs9_new["debug_mode_used"] = True
        player.combat_state = cs9_new

    # Addon 13 (AppExchange Marketplace): once per game, peek 3 addons from deck and pick 1
    elif addon.number == 13:
        _cs13 = player.combat_state or {}
        if _cs13.get("appexchange_used"):
            await _error(game.code, user_id, "AppExchange Marketplace already used this game")
            pa.is_tapped = False
            return
        choices_13 = []
        _deck13_1 = list(game.addon_deck_1 or [])
        _deck13_2 = list(game.addon_deck_2 or [])
        for _ in range(3):
            if _deck13_1:
                choices_13.append(_deck13_1.pop(0))
            elif _deck13_2:
                choices_13.append(_deck13_2.pop(0))
        if not choices_13:
            await _error(game.code, user_id, "No addons available in decks")
            pa.is_tapped = False
            return
        game.addon_deck_1 = _deck13_1
        game.addon_deck_2 = _deck13_2
        cs13_new = dict(_cs13)
        cs13_new["appexchange_pending"] = choices_13
        cs13_new["appexchange_used"] = True
        player.combat_state = cs13_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "appexchange_choices",
            "player_id": player.id,
            "addon_ids": choices_13,
        })
        await _broadcast_state(game, db)
        return  # don't broadcast addon_used yet — wait for pick

    # Addon 18 (Field History Tracking): recover last discarded card to hand
    elif addon.number == 18:
        _cs18 = player.combat_state or {}
        _last_id18 = _cs18.get("last_discarded_card_id")
        if not _last_id18:
            await _error(game.code, user_id, "No discarded card to recover")
            pa.is_tapped = False
            return
        _discard18 = list(game.action_discard or [])
        if _last_id18 in _discard18:
            _discard18.remove(_last_id18)
            game.action_discard = _discard18
            from app.models.game import PlayerHandCard as _PHC18
            db.add(_PHC18(player_id=player.id, action_card_id=_last_id18))
        cs18_new = dict(_cs18)
        cs18_new.pop("last_discarded_card_id", None)
        player.combat_state = cs18_new

    # Addon 24 (Einstein Next Best Action): once per combat, skip a round — neutral
    elif addon.number == 24:
        cs24 = player.combat_state or {}
        if cs24.get("einstein_nba_used"):
            await _error(game.code, user_id, "Einstein Next Best Action already used this combat")
            pa.is_tapped = False
            return
        if not player.is_in_combat:
            await _error(game.code, user_id, "Can only use during combat")
            pa.is_tapped = False
            return
        cs24_new = dict(cs24)
        cs24_new["einstein_nba_used"] = True
        cs24_new["skip_next_round_neutral"] = True
        player.combat_state = cs24_new

    # Addon 26 (Slack Connect): once per turn, pass 1 card from hand to any player
    elif addon.number == 26:
        target_id26 = data.get("target_player_id")
        hand_card_id26 = data.get("hand_card_id")
        target26 = next((p for p in game.players if p.id == target_id26), None)
        if not target26 or target26.id == player.id:
            await _error(game.code, user_id, "Invalid target player")
            pa.is_tapped = False
            return
        from app.models.game import PlayerHandCard as _PHC26
        hc26 = db.get(_PHC26, hand_card_id26)
        if not hc26 or hc26.player_id != player.id:
            await _error(game.code, user_id, "Card not in your hand")
            pa.is_tapped = False
            return
        hc26.player_id = target26.id

    # Addon 29 (Einstein Copilot): once per game, roll 3 dice — for each ≥8, gain 1 cert (max 2)
    elif addon.number == 29:
        cs29 = player.combat_state or {}
        if cs29.get("einstein_copilot_used"):
            await _error(game.code, user_id, "Einstein Copilot already used this game")
            pa.is_tapped = False
            return
        rolls29 = [engine.roll_d10() for _ in range(3)]
        certs_gained = min(2, sum(1 for r in rolls29 if r >= 8))
        player.certificazioni += certs_gained
        cs29_new = dict(cs29)
        cs29_new["einstein_copilot_used"] = True
        player.combat_state = cs29_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "einstein_copilot_result",
            "player_id": player.id,
            "rolls": rolls29,
            "certs_gained": certs_gained,
        })
        await _broadcast_state(game, db)
        return

    # Addon 33 (Governor Limit Bypass): once per combat, roll 3 dice — hits deal separate damage
    elif addon.number == 33:
        cs33 = player.combat_state or {}
        if cs33.get("governor_bypass_used"):
            await _error(game.code, user_id, "Governor Limit Bypass already used this combat")
            pa.is_tapped = False
            return
        if not player.is_in_combat or not player.current_boss_id:
            await _error(game.code, user_id, "Can only use during combat")
            pa.is_tapped = False
            return
        boss33 = db.get(BossCard, player.current_boss_id)
        if not boss33:
            pa.is_tapped = False
            return
        threshold33 = boss33.dice_threshold
        rolls33 = [engine.roll_d10() for _ in range(3)]
        hits33 = sum(1 for r in rolls33 if r >= threshold33)
        boss_hp_lost33 = 0
        if hits33 > 0:
            player.current_boss_hp = max(0, (player.current_boss_hp or 0) - hits33)
            boss_hp_lost33 = hits33
        cs33_new = dict(cs33)
        cs33_new["governor_bypass_used"] = True
        player.combat_state = cs33_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "governor_bypass_result",
            "player_id": player.id,
            "rolls": rolls33,
            "hits": hits33,
            "boss_hp_lost": boss_hp_lost33,
        })
        # If boss is defeated, set a flag — roll.py will handle on next roll, or handle here
        if (player.current_boss_hp or 0) <= 0:
            from app.websocket.handlers.combat.roll import _boss_defeat_sequence as _bds33
            boss33_fresh = db.get(BossCard, player.current_boss_id)
            if boss33_fresh:
                await _bds33(player, game, db, boss33_fresh)
        db.commit()
        db.refresh(game)
        await _broadcast_state(game, db)
        return

    # Addon 37 (Deployment Pipeline): once per turn, allow 1 extra action card play
    elif addon.number == 37:
        cs37 = dict(player.combat_state or {})
        cs37["deployment_pipeline_extra_card"] = True
        player.combat_state = cs37

    # Addon 19 (Chatter Feed): show your hand to a target and request a card
    elif addon.number == 19:
        _target19_id = data.get("target_player_id")
        _target19 = next((p for p in game.players if p.id == _target19_id), None)
        if not _target19 or _target19.id == player.id:
            await _error(game.code, user_id, "Invalid target for Chatter Feed")
            pa.is_tapped = False
            return
        _cs19_req = dict(player.combat_state or {})
        _cs19_req["chatter_feed_pending_from_id"] = player.id
        player.combat_state = _cs19_req
        _cs19_tgt = dict(_target19.combat_state or {})
        _cs19_tgt["chatter_feed_pending_requester_id"] = player.id
        _target19.combat_state = _cs19_tgt
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, _target19.user_id, {
            "type": "chatter_feed_request",
            "requester_id": player.id,
            "requester_hand": [
                {"id": hc19.id, "action_card_id": hc19.action_card_id}
                for hc19 in player.hand
            ],
        })
        await _broadcast_state(game, db)
        return  # wait for chatter_feed_respond

    # Addon 45 (CPQ Advanced): once per game, set next addon price to 0
    elif addon.number == 45:
        _cs45 = player.combat_state or {}
        if _cs45.get("cpq_advanced_used"):
            await _error(game.code, user_id, "CPQ Advanced already used this game")
            pa.is_tapped = False
            return
        _cs45_new = dict(_cs45)
        _cs45_new["cpq_advanced_used"] = True
        _cs45_new["next_addon_price_fixed"] = 0
        player.combat_state = _cs45_new

    # Addon 49 (Metadata API): look at top 3 cards of action deck and reorder them
    elif addon.number == 49:
        _deck49 = game.action_deck_1 or game.action_deck_2
        _choices49 = (game.action_deck_1 or [])[:3]
        if not _choices49:
            await _error(game.code, user_id, "No cards in deck")
            pa.is_tapped = False
            return
        _cs49 = dict(player.combat_state or {})
        _cs49["metadata_api_pending"] = list(_choices49)
        player.combat_state = _cs49
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "metadata_api_peek",
            "player_id": player.id,
            "card_ids": list(_choices49),
        })
        await _broadcast_state(game, db)
        return  # wait for metadata_api_reorder

    # Addon 50 (Tooling API): once per game, recover up to 2 cards from discard to hand
    elif addon.number == 50:
        _cs50 = player.combat_state or {}
        if _cs50.get("tooling_api_used"):
            await _error(game.code, user_id, "Tooling API already used this game")
            pa.is_tapped = False
            return
        _discard50 = list(game.action_discard or [])
        if not _discard50:
            await _error(game.code, user_id, "Discard pile is empty")
            pa.is_tapped = False
            return
        _recover50 = _discard50[-2:] if len(_discard50) >= 2 else _discard50[:]
        game.action_discard = _discard50[:-len(_recover50)]
        from app.models.game import PlayerHandCard as _PHC50
        for _cid50 in _recover50:
            db.add(_PHC50(player_id=player.id, action_card_id=_cid50))
        _cs50_new = dict(_cs50)
        _cs50_new["tooling_api_used"] = True
        player.combat_state = _cs50_new

    # Addon 51 (Change Set): discard up to 3 cards from hand and draw the same number
    elif addon.number == 51:
        _discard_ids51 = data.get("hand_card_ids", [])
        if not _discard_ids51 or len(_discard_ids51) > 3:
            await _error(game.code, user_id, "Provide 1-3 hand card IDs")
            pa.is_tapped = False
            return
        from app.models.game import PlayerHandCard as _PHC51
        _to_discard51 = []
        for _hcid51 in _discard_ids51:
            _hc51 = db.get(_PHC51, _hcid51)
            if not _hc51 or _hc51.player_id != player.id:
                await _error(game.code, user_id, "Card not in your hand")
                pa.is_tapped = False
                return
            _to_discard51.append(_hc51)
        _count51 = len(_to_discard51)
        for _hc51 in _to_discard51:
            game.action_discard = (game.action_discard or []) + [_hc51.action_card_id]
            db.delete(_hc51)
        for _ in range(_count51):
            if game.action_deck_1:
                _new_card51 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _new_card51 = game.action_deck_2.pop(0)
            else:
                break
            db.add(_PHC51(player_id=player.id, action_card_id=_new_card51))

    # Addon 53 (Version Control): once per game, recover last played card from discard to hand
    elif addon.number == 53:
        _cs53 = player.combat_state or {}
        if _cs53.get("version_control_used"):
            await _error(game.code, user_id, "Version Control already used this game")
            pa.is_tapped = False
            return
        _last_id53 = _cs53.get("last_discarded_card_id")
        if not _last_id53:
            await _error(game.code, user_id, "No card to recover")
            pa.is_tapped = False
            return
        if _last_id53 in (game.action_discard or []):
            _discard53 = list(game.action_discard)
            _discard53.remove(_last_id53)
            game.action_discard = _discard53
            from app.models.game import PlayerHandCard as _PHC53
            db.add(_PHC53(player_id=player.id, action_card_id=_last_id53))
        _cs53_new = dict(_cs53)
        _cs53_new["version_control_used"] = True
        _cs53_new.pop("last_discarded_card_id", None)
        player.combat_state = _cs53_new

    # Addon 55 (Data Loader Pro): once per game, draw 5 action cards
    elif addon.number == 55:
        _cs55 = player.combat_state or {}
        if _cs55.get("data_loader_used"):
            await _error(game.code, user_id, "Data Loader Pro already used this game")
            pa.is_tapped = False
            return
        from app.models.game import PlayerHandCard as _PHC55
        _drawn55 = 0
        for _ in range(5):
            if game.action_deck_1:
                _cid55 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _cid55 = game.action_deck_2.pop(0)
            else:
                break
            db.add(_PHC55(player_id=player.id, action_card_id=_cid55))
            _drawn55 += 1
        _cs55_new = dict(_cs55)
        _cs55_new["data_loader_used"] = True
        player.combat_state = _cs55_new

    # Addon 62 (Field Audit Trail): once per turn, look at a target player's full hand
    elif addon.number == 62:
        _target_id62 = data.get("target_player_id")
        _target62 = next((p for p in game.players if p.id == _target_id62), None)
        if not _target62 or _target62.id == player.id:
            await _error(game.code, user_id, "Invalid target for Field Audit Trail")
            pa.is_tapped = False
            return
        _hand62 = [{"id": hc.id, "action_card_id": hc.action_card_id} for hc in _target62.hand]
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "field_audit_trail_result",
            "target_player_id": _target62.id,
            "hand": _hand62,
        })
        await _broadcast_state(game, db)
        return

    # Addon 63 (Sharing Rules): once per turn, peek at opponent's hand and copy one card
    elif addon.number == 63:
        _target_id63 = data.get("target_player_id")
        _target63 = next((p for p in game.players if p.id == _target_id63), None)
        if not _target63 or _target63.id == player.id:
            await _error(game.code, user_id, "Invalid target for Sharing Rules")
            pa.is_tapped = False
            return
        _cs63 = dict(player.combat_state or {})
        _cs63["sharing_rules_pending_target_id"] = _target63.id
        player.combat_state = _cs63
        _hand63 = [{"id": hc.id, "action_card_id": hc.action_card_id} for hc in _target63.hand]
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "sharing_rules_peek",
            "target_player_id": _target63.id,
            "hand": _hand63,
        })
        await _broadcast_state(game, db)
        return  # wait for sharing_rules_pick

    # Addon 64 (Role Hierarchy): SKIP — seniority comparison system not fully implemented for cross-player ranking
    # TODO: implement when seniority ordering/ranking between players is available

    # Addon 66 (Trust Layer): once per game, protect from opponent cards for 1 turn
    elif addon.number == 66:
        _cs66 = player.combat_state or {}
        if _cs66.get("trust_layer_used"):
            await _error(game.code, user_id, "Trust Layer already used this game")
            pa.is_tapped = False
            return
        _cs66_new = dict(_cs66)
        _cs66_new["trust_layer_used"] = True
        _cs66_new["trust_layer_active"] = True
        player.combat_state = _cs66_new

    # Addon 67 (Connected App Token): once per game, tap an opponent's addon for 1 turn
    elif addon.number == 67:
        _cs67 = player.combat_state or {}
        if _cs67.get("connected_app_used"):
            await _error(game.code, user_id, "Connected App Token already used this game")
            pa.is_tapped = False
            return
        _target_id67 = data.get("target_player_id")
        _target_pa_id67 = data.get("target_addon_id")
        _target67 = next((p for p in game.players if p.id == _target_id67), None)
        if not _target67 or _target67.id == player.id:
            await _error(game.code, user_id, "Invalid target for Connected App Token")
            pa.is_tapped = False
            return
        from app.models.game import PlayerAddon as _PA67
        _target_pa67 = db.get(_PA67, _target_pa_id67)
        if not _target_pa67 or _target_pa67.player_id != _target67.id:
            await _error(game.code, user_id, "Addon not owned by target")
            pa.is_tapped = False
            return
        # Addon 138 (Managed Package): target's addons are protected
        if _has_addon_addon(_target67, 138):
            await _error(game.code, user_id, "Target's addons are protected by Managed Package")
            pa.is_tapped = False
            return
        _target_pa67.is_tapped = True
        _cs67_new = dict(_cs67)
        _cs67_new["connected_app_used"] = True
        player.combat_state = _cs67_new

    # Addon 74 (Before/After Save Hook): discard 1 card and draw 1 new one (treat as Attivo)
    elif addon.number == 74:
        target_hc_id74 = data.get("hand_card_id")
        if not target_hc_id74:
            await _error(game.code, user_id, "Provide hand_card_id to discard")
            pa.is_tapped = False
            return
        from app.models.game import PlayerHandCard as _PHC74
        hc74 = db.get(_PHC74, target_hc_id74)
        if not hc74 or hc74.player_id != player.id:
            await _error(game.code, user_id, "Card not in your hand")
            pa.is_tapped = False
            return
        game.action_discard = (game.action_discard or []) + [hc74.action_card_id]
        db.delete(hc74)
        _new74 = None
        if game.action_deck_1:
            _new74 = game.action_deck_1.pop(0)
        elif game.action_deck_2:
            _new74 = game.action_deck_2.pop(0)
        if _new74 is not None:
            db.add(_PHC74(player_id=player.id, action_card_id=_new74))

    # Addon 81 (Boss Vulnerability Scan): once per combat, next dice roll has +4 bonus
    elif addon.number == 81:
        cs81 = player.combat_state or {}
        if cs81.get("vulnerability_scan_used"):
            await _error(game.code, user_id, "Boss Vulnerability Scan already used this combat")
            pa.is_tapped = False
            return
        if not player.is_in_combat:
            await _error(game.code, user_id, "Must be in combat to use Boss Vulnerability Scan")
            pa.is_tapped = False
            return
        cs81_new = dict(cs81)
        cs81_new["vulnerability_scan_used"] = True
        cs81_new["vulnerability_scan_bonus"] = 4
        player.combat_state = cs81_new

    # Addon 82 (Deployment Freeze): once per game, send current boss back to bottom of deck
    elif addon.number == 82:
        cs82 = player.combat_state or {}
        if cs82.get("deployment_freeze_used"):
            await _error(game.code, user_id, "Deployment Freeze already used this game")
            pa.is_tapped = False
            return
        if not player.is_in_combat or not player.current_boss_id:
            await _error(game.code, user_id, "Must be in active combat to use Deployment Freeze")
            pa.is_tapped = False
            return
        boss_id82 = player.current_boss_id
        source82 = player.current_boss_source
        if source82 and "2" in str(source82):
            game.boss_deck_2 = (game.boss_deck_2 or []) + [boss_id82]
        else:
            game.boss_deck_1 = (game.boss_deck_1 or []) + [boss_id82]
        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        player.current_boss_source = None
        player.combat_round = None
        cs82_new = dict(cs82)
        cs82_new["deployment_freeze_used"] = True
        player.combat_state = cs82_new
        from app.models.game import TurnPhase as _TP82
        game.current_phase = _TP82.action

    # Addon 85 (Instance Refresh): once per game, send just-drawn boss back to bottom of deck
    elif addon.number == 85:
        cs85 = player.combat_state or {}
        if cs85.get("instance_refresh_used"):
            await _error(game.code, user_id, "Instance Refresh already used this game")
            pa.is_tapped = False
            return
        if not player.is_in_combat or not player.current_boss_id:
            await _error(game.code, user_id, "Must be in active combat to use Instance Refresh")
            pa.is_tapped = False
            return
        boss_id85 = player.current_boss_id
        source85 = player.current_boss_source
        if source85 and "2" in str(source85):
            game.boss_deck_2 = (game.boss_deck_2 or []) + [boss_id85]
        else:
            game.boss_deck_1 = (game.boss_deck_1 or []) + [boss_id85]
        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        player.current_boss_source = None
        player.combat_round = None
        cs85_new = dict(cs85)
        cs85_new["instance_refresh_used"] = True
        player.combat_state = cs85_new
        from app.models.game import TurnPhase as _TP85
        game.current_phase = _TP85.action

    # Addon 88 (Mass Update Override): once per game, deal 2 HP damage to any boss in active combat
    elif addon.number == 88:
        cs88 = player.combat_state or {}
        if cs88.get("mass_update_used"):
            await _error(game.code, user_id, "Mass Update Override already used this game")
            pa.is_tapped = False
            return
        target_id88 = data.get("target_player_id", player.id)
        target88 = next((p for p in game.players if p.id == target_id88), None)
        if not target88 or not target88.is_in_combat:
            await _error(game.code, user_id, "Target not in combat")
            pa.is_tapped = False
            return
        target88.current_boss_hp = max(0, (target88.current_boss_hp or 0) - 2)
        cs88_new = dict(cs88)
        cs88_new["mass_update_used"] = True
        player.combat_state = cs88_new
        # If boss is defeated, let next roll resolve it (hp is 0)

    # Addon 89 (Data Migration Tool): once per game, swap one of your addons with an opponent's
    elif addon.number == 89:
        cs89 = player.combat_state or {}
        if cs89.get("data_migration_used"):
            await _error(game.code, user_id, "Data Migration Tool already used")
            pa.is_tapped = False
            return
        my_pa_id89 = data.get("my_addon_id")
        their_pa_id89 = data.get("target_addon_id")
        from app.models.game import PlayerAddon as _PA89
        my_pa89 = db.get(_PA89, my_pa_id89)
        their_pa89 = db.get(_PA89, their_pa_id89)
        if not my_pa89 or my_pa89.player_id != player.id:
            await _error(game.code, user_id, "Invalid your addon")
            pa.is_tapped = False
            return
        if not their_pa89 or their_pa89.player_id == player.id:
            await _error(game.code, user_id, "Invalid opponent addon")
            pa.is_tapped = False
            return
        # Addon 138 (Managed Package): target's addons are protected
        _their_player89 = next((p for p in game.players if p.id == their_pa89.player_id), None)
        if _their_player89 and _has_addon_addon(_their_player89, 138):
            await _error(game.code, user_id, "Target's addons are protected by Managed Package")
            pa.is_tapped = False
            return
        their_old_player_id = their_pa89.player_id
        my_pa89.player_id = their_old_player_id
        their_pa89.player_id = player.id
        cs89_new = dict(cs89)
        cs89_new["data_migration_used"] = True
        player.combat_state = cs89_new

    # Addon 90 (Org Split): once per game, give half HP (floor) to opponent to weaken them
    elif addon.number == 90:
        cs90 = player.combat_state or {}
        if cs90.get("org_split_used"):
            await _error(game.code, user_id, "Org Split already used")
            pa.is_tapped = False
            return
        target_id90 = data.get("target_player_id")
        target90 = next((p for p in game.players if p.id == target_id90), None)
        if not target90 or target90.id == player.id:
            await _error(game.code, user_id, "Invalid target for Org Split")
            pa.is_tapped = False
            return
        hp_transfer90 = player.hp // 2
        if hp_transfer90 <= 0:
            await _error(game.code, user_id, "Not enough HP to split")
            pa.is_tapped = False
            return
        player.hp -= hp_transfer90
        target90.hp = max(0, target90.hp - hp_transfer90)
        cs90_new = dict(cs90)
        cs90_new["org_split_used"] = True
        player.combat_state = cs90_new

    # Addon 91 (Free Trial): borrow a market addon for 1 full turn, then return it
    elif addon.number == 91:
        cs91 = player.combat_state or {}
        if cs91.get("free_trial_used"):
            await _error(game.code, user_id, "Free Trial already used")
            pa.is_tapped = False
            return
        target_addon_id91 = data.get("target_addon_id")
        market91 = []
        if game.addon_market_1:
            market91.append(game.addon_market_1)
        if game.addon_market_2:
            market91.append(game.addon_market_2)
        if target_addon_id91 not in market91:
            await _error(game.code, user_id, "Addon not in market")
            pa.is_tapped = False
            return
        from app.models.game import PlayerAddon as _PA91
        temp_pa91 = _PA91(player_id=player.id, addon_id=target_addon_id91, is_tapped=False)
        db.add(temp_pa91)
        db.flush()
        cs91_new = dict(cs91)
        cs91_new["free_trial_used"] = True
        cs91_new["free_trial_borrowed_pa_id"] = temp_pa91.id
        cs91_new["free_trial_borrowed_addon_id"] = target_addon_id91
        player.combat_state = cs91_new

    # Addon 93 (Pilot Program): once per game, choose an addon from graveyard
    elif addon.number == 93:
        cs93 = player.combat_state or {}
        if cs93.get("pilot_program_used"):
            await _error(game.code, user_id, "Pilot Program already used")
            pa.is_tapped = False
            return
        discard93 = list(game.addon_graveyard or [])
        if not discard93:
            await _error(game.code, user_id, "Addon graveyard is empty")
            pa.is_tapped = False
            return
        cs93_new = dict(cs93)
        cs93_new["pilot_program_used"] = True
        cs93_new["pilot_program_pending"] = True
        player.combat_state = cs93_new
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "pilot_program_options",
            "addon_card_ids": discard93,
        })
        await _broadcast_state(game, db)
        return

    # Addon 95 (Sprint Review): once per game, swap one of your addons with an opponent's
    elif addon.number == 95:
        cs95 = player.combat_state or {}
        if cs95.get("sprint_review_used"):
            await _error(game.code, user_id, "Sprint Review already used")
            pa.is_tapped = False
            return
        my_pa_id95 = data.get("my_addon_id")
        their_pa_id95 = data.get("target_addon_id")
        from app.models.game import PlayerAddon as _PA95
        my_pa95 = db.get(_PA95, my_pa_id95)
        their_pa95 = db.get(_PA95, their_pa_id95)
        if not my_pa95 or my_pa95.player_id != player.id:
            await _error(game.code, user_id, "Invalid your addon")
            pa.is_tapped = False
            return
        if not their_pa95 or their_pa95.player_id == player.id:
            await _error(game.code, user_id, "Invalid opponent addon")
            pa.is_tapped = False
            return
        # Addon 138 (Managed Package): target's addons are protected
        _their_player95 = next((p for p in game.players if p.id == their_pa95.player_id), None)
        if _their_player95 and _has_addon_addon(_their_player95, 138):
            await _error(game.code, user_id, "Target's addons are protected by Managed Package")
            pa.is_tapped = False
            return
        their_old_player_id = their_pa95.player_id
        my_pa95.player_id = their_old_player_id
        their_pa95.player_id = player.id
        cs95_new = dict(cs95)
        cs95_new["sprint_review_used"] = True
        player.combat_state = cs95_new

    # Addon 99 (Retrospective): once per game, discard 2 cards from target opponent's hand
    elif addon.number == 99:
        cs99 = player.combat_state or {}
        if cs99.get("retrospective_used"):
            await _error(game.code, user_id, "Retrospective already used")
            pa.is_tapped = False
            return
        target_id99 = data.get("target_player_id")
        target99 = next((p for p in game.players if p.id == target_id99), None)
        if not target99 or target99.id == player.id:
            await _error(game.code, user_id, "Invalid target")
            pa.is_tapped = False
            return
        from app.models.game import PlayerHandCard as _PHC99
        hand99 = list(target99.hand)
        discard_count99 = min(2, len(hand99))
        if discard_count99 == 0:
            await _error(game.code, user_id, "Target has no cards")
            pa.is_tapped = False
            return
        import random as _random99
        to_discard99 = _random99.sample(hand99, discard_count99)
        for hc99 in to_discard99:
            game.action_discard = (game.action_discard or []) + [hc99.action_card_id]
            db.delete(hc99)
        cs99_new = dict(cs99)
        cs99_new["retrospective_used"] = True
        player.combat_state = cs99_new

    # Addon 101 (Org-Wide Sharing): once per turn, a player gains +1L
    elif addon.number == 101:
        target_id101 = data.get("target_player_id", player.id)
        target101 = next((p for p in game.players if p.id == target_id101), None)
        if not target101:
            await _error(game.code, user_id, "Invalid target")
            pa.is_tapped = False
            return
        target101.licenze += 1

    # Addon 102 (Custom Permission): TODO pending role/seniority system
    elif addon.number == 102:
        # TODO: implement when role and seniority system is complete
        # Effect: use the passive ability of a character with lower seniority than yours
        await _error(game.code, user_id, "Custom Permission not yet implemented (pending role system)")
        pa.is_tapped = False
        return

    # Addon 104 (User Story): once per game, draw 3 cards and gain 3L
    elif addon.number == 104:
        cs104 = player.combat_state or {}
        if cs104.get("user_story_used"):
            await _error(game.code, user_id, "User Story already used")
            pa.is_tapped = False
            return
        from app.models.game import PlayerHandCard as _PHC104
        for _ in range(3):
            if game.action_deck_1:
                cid104 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                cid104 = game.action_deck_2.pop(0)
            else:
                break
            db.add(_PHC104(player_id=player.id, action_card_id=cid104))
        player.licenze += 3
        cs104_new = dict(cs104)
        cs104_new["user_story_used"] = True
        player.combat_state = cs104_new

    # Addon 108 (Architecture Review): once per game, return up to 2 addons to deck, gain 8L each
    elif addon.number == 108:
        cs108 = player.combat_state or {}
        if cs108.get("architecture_review_used"):
            await _error(game.code, user_id, "Architecture Review already used")
            pa.is_tapped = False
            return
        pa_ids108 = data.get("addon_ids", [])
        if not pa_ids108 or len(pa_ids108) > 2:
            await _error(game.code, user_id, "Provide 1-2 addon IDs to return")
            pa.is_tapped = False
            return
        from app.models.game import PlayerAddon as _PA108
        returned108 = 0
        for pa_id108 in pa_ids108:
            pa108 = db.get(_PA108, pa_id108)
            if not pa108 or pa108.player_id != player.id or pa108.id == pa.id:
                continue
            game.addon_deck_1 = (game.addon_deck_1 or []) + [pa108.addon_id]
            db.delete(pa108)
            player.licenze += 8
            returned108 += 1
        if returned108 == 0:
            await _error(game.code, user_id, "No valid addons to return")
            pa.is_tapped = False
            return
        cs108_new = dict(cs108)
        cs108_new["architecture_review_used"] = True
        player.combat_state = cs108_new

    # Addon 109 (Proof of Concept): once per turn, play 1 card without using a slot
    elif addon.number == 109:
        cs109 = dict(player.combat_state or {})
        if cs109.get("proof_of_concept_used_this_turn"):
            await _error(game.code, user_id, "Proof of Concept already used this turn")
            pa.is_tapped = False
            return
        cs109["proof_of_concept_active"] = True
        cs109["proof_of_concept_used_this_turn"] = True
        player.combat_state = cs109

    # ── Active addon effects (111-140) ──────────────────────────────────────

    # Addon 115 (Future Method): next dice roll is doubled (capped at 10)
    elif addon.number == 115:
        if not player.is_in_combat:
            await _error(game.code, user_id, "Must be in combat to use Future Method")
            pa.is_tapped = False
            return
        cs115 = dict(player.combat_state or {})
        if cs115.get("future_method_active"):
            await _error(game.code, user_id, "Future Method already active")
            pa.is_tapped = False
            return
        cs115["future_method_active"] = True
        player.combat_state = cs115

    # Addon 119 (Queueable Job): once per game, buy any market addon for free
    elif addon.number == 119:
        cs119 = player.combat_state or {}
        if cs119.get("queueable_job_used"):
            await _error(game.code, user_id, "Queueable Job already used this game")
            pa.is_tapped = False
            return
        target_addon_id119 = data.get("target_addon_id")
        market119 = []
        if game.addon_market_1:
            market119.append(game.addon_market_1)
        if game.addon_market_2:
            market119.append(game.addon_market_2)
        if target_addon_id119 not in market119:
            await _error(game.code, user_id, "Addon not in market")
            pa.is_tapped = False
            return
        if game.addon_market_1 == target_addon_id119:
            game.addon_market_1 = game.addon_deck_1.pop(0) if game.addon_deck_1 else (game.addon_deck_2.pop(0) if game.addon_deck_2 else None)
        elif game.addon_market_2 == target_addon_id119:
            game.addon_market_2 = game.addon_deck_1.pop(0) if game.addon_deck_1 else (game.addon_deck_2.pop(0) if game.addon_deck_2 else None)
        from app.models.game import PlayerAddon as _PA119
        db.add(_PA119(player_id=player.id, addon_id=target_addon_id119, is_tapped=False))
        cs119_new = dict(cs119)
        cs119_new["queueable_job_used"] = True
        player.combat_state = cs119_new

    # Addon 120 (Scheduled Flow): declare 2-4 turns; when they expire, gain that many L
    elif addon.number == 120:
        declared120 = data.get("turns_declared")
        if declared120 not in (2, 3, 4):
            await _error(game.code, user_id, "Declare 2, 3 or 4 turns")
            pa.is_tapped = False
            return
        cs120 = dict(player.combat_state or {})
        if cs120.get("scheduled_flow_countdown") is not None:
            await _error(game.code, user_id, "Scheduled Flow already running")
            pa.is_tapped = False
            return
        cs120["scheduled_flow_countdown"] = declared120
        cs120["scheduled_flow_reward"] = declared120
        player.combat_state = cs120

    # Addon 121 (Mass Email): play 1 economic card — effect applies to you AND 1 other player
    elif addon.number == 121:
        target_id121 = data.get("target_player_id")
        hand_card_id121 = data.get("hand_card_id")
        target121 = next((p for p in game.players if p.id == target_id121), None)
        if not target121 or target121.id == player.id:
            await _error(game.code, user_id, "Invalid target for Mass Email")
            pa.is_tapped = False
            return
        from app.models.game import PlayerHandCard as _PHC121
        hc121 = db.get(_PHC121, hand_card_id121)
        if not hc121 or hc121.player_id != player.id:
            await _error(game.code, user_id, "Card not in hand")
            pa.is_tapped = False
            return
        from app.models.card import ActionCard as _AC121
        card121 = db.get(_AC121, hc121.action_card_id)
        if not card121 or card121.card_type != "Economica":
            await _error(game.code, user_id, "Must be an economic card")
            pa.is_tapped = False
            return
        from app.game.engine_cards import apply_action_card_effect as _apply121
        _apply121(card121, player, game, db)
        _apply121(card121, target121, game, db)
        game.action_discard = (game.action_discard or []) + [hc121.action_card_id]
        db.delete(hc121)

    # Addon 122 (Broadcast Message): once per game, all opponents discard 1 card
    elif addon.number == 122:
        cs122 = player.combat_state or {}
        if cs122.get("broadcast_used"):
            await _error(game.code, user_id, "Broadcast Message already used this game")
            pa.is_tapped = False
            return
        import random as _r122
        from app.models.game import PlayerHandCard as _PHC122
        for _p122 in game.players:
            if _p122.id == player.id:
                continue
            _hand122 = list(_p122.hand)
            if _hand122:
                _discard122 = _r122.choice(_hand122)
                game.action_discard = (game.action_discard or []) + [_discard122.action_card_id]
                db.delete(_discard122)
        cs122_new = dict(cs122)
        cs122_new["broadcast_used"] = True
        player.combat_state = cs122_new

    # Addon 123 (Global Action): once per game, all opponents lose 2L
    elif addon.number == 123:
        cs123 = player.combat_state or {}
        if cs123.get("global_action_used"):
            await _error(game.code, user_id, "Global Action already used this game")
            pa.is_tapped = False
            return
        for _p123 in game.players:
            if _p123.id != player.id:
                _p123.licenze = max(0, _p123.licenze - 2)
        cs123_new = dict(cs123)
        cs123_new["global_action_used"] = True
        player.combat_state = cs123_new

    # Addon 124 (Bulk API): once per game, buy up to 3 addons in one turn ignoring 1-per-turn limit
    elif addon.number == 124:
        cs124 = player.combat_state or {}
        if cs124.get("bulk_api_used"):
            await _error(game.code, user_id, "Bulk API already used this game")
            pa.is_tapped = False
            return
        cs124_new = dict(cs124)
        cs124_new["bulk_api_used"] = True
        cs124_new["bulk_api_purchases_remaining"] = 3
        player.combat_state = cs124_new

    # Addon 127 (Sharing Set): once per game, redistribute all players' L equally (floor)
    elif addon.number == 127:
        cs127 = player.combat_state or {}
        if cs127.get("sharing_set_used"):
            await _error(game.code, user_id, "Sharing Set already used this game")
            pa.is_tapped = False
            return
        total127 = sum(p.licenze for p in game.players)
        per_player127 = total127 // len(game.players)
        for _p127 in game.players:
            _p127.licenze = per_player127
        cs127_new = dict(cs127)
        cs127_new["sharing_set_used"] = True
        player.combat_state = cs127_new

    # Addon 129 (Junction Object): once per turn, untap one of your tapped addons
    elif addon.number == 129:
        target_pa_id129 = data.get("target_addon_id")
        from app.models.game import PlayerAddon as _PA129
        target_pa129 = db.get(_PA129, target_pa_id129)
        if not target_pa129 or target_pa129.player_id != player.id:
            await _error(game.code, user_id, "Invalid addon for Junction Object")
            pa.is_tapped = False
            return
        if not target_pa129.is_tapped:
            await _error(game.code, user_id, "Addon is not tapped")
            pa.is_tapped = False
            return
        if target_pa129.id == pa.id:
            await _error(game.code, user_id, "Cannot untap itself")
            pa.is_tapped = False
            return
        target_pa129.is_tapped = False

    # Addon 130 (External Object): once per game, choose addon from graveyard and acquire by paying cost
    elif addon.number == 130:
        cs130 = player.combat_state or {}
        if cs130.get("external_object_used"):
            await _error(game.code, user_id, "External Object already used this game")
            pa.is_tapped = False
            return
        graveyard130 = list(game.addon_graveyard or [])
        if not graveyard130:
            await _error(game.code, user_id, "Addon graveyard is empty")
            pa.is_tapped = False
            return
        cs130_new = dict(cs130)
        cs130_new["external_object_used"] = True
        cs130_new["external_object_pending"] = True
        player.combat_state = cs130_new
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "external_object_options",
            "addon_card_ids": graveyard130,
        })
        await _broadcast_state(game, db)
        return

    # Addon 134 (Major Release): once per game, roll dice: ≥6 → +3L; ≤5 → draw 2 cards
    elif addon.number == 134:
        cs134 = player.combat_state or {}
        if cs134.get("major_release_used"):
            await _error(game.code, user_id, "Major Release already used this game")
            pa.is_tapped = False
            return
        roll134 = engine.roll_d10()
        cs134_new = dict(cs134)
        cs134_new["major_release_used"] = True
        player.combat_state = cs134_new
        if roll134 >= 6:
            player.licenze += 3
        else:
            from app.models.game import PlayerHandCard as _PHC134
            for _ in range(2):
                if game.action_deck_1:
                    cid134 = game.action_deck_1.pop(0)
                elif game.action_deck_2:
                    cid134 = game.action_deck_2.pop(0)
                else:
                    break
                db.add(_PHC134(player_id=player.id, action_card_id=cid134))
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "major_release_roll",
            "player_id": player.id,
            "roll": roll134,
        })
        await _broadcast_state(game, db)
        return

    # Addon 140 (OmniScript): once per game, roll 2 dice, gain L equal to sum (max 20)
    elif addon.number == 140:
        cs140 = player.combat_state or {}
        if cs140.get("omniscript_used"):
            await _error(game.code, user_id, "OmniScript already used this game")
            pa.is_tapped = False
            return
        r1_140 = engine.roll_d10()
        r2_140 = engine.roll_d10()
        gain140 = min(r1_140 + r2_140, 20)
        player.licenze += gain140
        cs140_new = dict(cs140)
        cs140_new["omniscript_used"] = True
        player.combat_state = cs140_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "omniscript_roll",
            "player_id": player.id,
            "roll_1": r1_140,
            "roll_2": r2_140,
            "gain": gain140,
        })
        await _broadcast_state(game, db)
        return

    # ── Active addon effects (141-160) ──────────────────────────────────────

    # Addon 141 (Calculated Risk): before rolling, declare a bet; ≥8 → +5L; ≤3 → -2L
    elif addon.number == 141:
        if not player.is_in_combat:
            await _error(game.code, user_id, "Must be in combat to use Calculated Risk")
            pa.is_tapped = False
            return
        cs141 = dict(player.combat_state or {})
        if cs141.get("calculated_risk_active"):
            await _error(game.code, user_id, "Calculated Risk already active this combat")
            pa.is_tapped = False
            return
        cs141["calculated_risk_active"] = True
        player.combat_state = cs141

    # Addon 142 (All or Nothing): skip this dice round, gain +4 to next roll
    elif addon.number == 142:
        if not player.is_in_combat:
            await _error(game.code, user_id, "Must be in combat to use All or Nothing")
            pa.is_tapped = False
            return
        cs142 = dict(player.combat_state or {})
        if cs142.get("all_or_nothing_pending"):
            await _error(game.code, user_id, "All or Nothing already charging")
            pa.is_tapped = False
            return
        cs142["all_or_nothing_pending"] = True
        player.combat_state = cs142
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {"type": "all_or_nothing_charging", "player_id": player.id})
        await _broadcast_state(game, db)
        return

    # Addon 143 (Double or Nothing): handled in _boss_defeat_sequence — passive trigger
    # (no manual use effect needed here; the addon is Attivo but triggers on boss defeat)

    # Addon 146 (Bet the Farm): once per game, dice duel with opponent — higher steals 3L
    elif addon.number == 146:
        cs146 = player.combat_state or {}
        if cs146.get("bet_farm_used"):
            await _error(game.code, user_id, "Bet the Farm already used this game")
            pa.is_tapped = False
            return
        target_id146 = data.get("target_player_id")
        target146 = next((p for p in game.players if p.id == target_id146), None)
        if not target146 or target146.id == player.id:
            await _error(game.code, user_id, "Invalid target for Bet the Farm")
            pa.is_tapped = False
            return
        roll_p146 = engine.roll_d10()
        roll_t146 = engine.roll_d10()
        if roll_p146 > roll_t146:
            stolen146 = min(3, target146.licenze)
            target146.licenze -= stolen146
            player.licenze += stolen146
            winner_id146 = player.id
        elif roll_t146 > roll_p146:
            stolen146 = min(3, player.licenze)
            player.licenze -= stolen146
            target146.licenze += stolen146
            winner_id146 = target146.id
        else:
            stolen146 = 0
            winner_id146 = None  # tie
        cs146_new = dict(cs146)
        cs146_new["bet_farm_used"] = True
        player.combat_state = cs146_new
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "bet_farm_result",
            "player_id": player.id,
            "target_id": target146.id,
            "player_roll": roll_p146,
            "target_roll": roll_t146,
            "winner_id": winner_id146,
            "licenze_stolen": stolen146,
        })
        await _broadcast_state(game, db)
        return

    # Addon 150 (Wildcards): for 1 full turn, play cards without limit and use all addons without limit
    elif addon.number == 150:
        cs150 = player.combat_state or {}
        if cs150.get("wildcards_used"):
            await _error(game.code, user_id, "Wildcards already used this game")
            pa.is_tapped = False
            return
        cs150_new = dict(cs150)
        cs150_new["wildcards_used"] = True
        cs150_new["wildcards_active"] = True
        player.combat_state = cs150_new
        # With wildcards active, don't tap this addon (it stays available)
        pa.is_tapped = False

    # Addon 153 (Certification Theft Ring): steal 1 cert from opponent; roll ≤3 → fail and lose 3L
    elif addon.number == 153:
        cs153 = player.combat_state or {}
        if cs153.get("cert_theft_used"):
            await _error(game.code, user_id, "Certification Theft Ring already used this game")
            pa.is_tapped = False
            return
        target_id153 = data.get("target_player_id")
        target153 = next((p for p in game.players if p.id == target_id153), None)
        if not target153 or target153.id == player.id:
            await _error(game.code, user_id, "Invalid target for Certification Theft Ring")
            pa.is_tapped = False
            return
        # Addon 157 (Portfolio Defense): immune to cert theft during own turn
        if _has_addon_addon(target153, 157):
            _is_target_turn153 = (
                bool(game.turn_order) and
                game.turn_order[game.current_turn_index] == target153.id
            )
            if _is_target_turn153:
                await _error(game.code, user_id, "Target is protected by Portfolio Defense during their turn")
                pa.is_tapped = False
                return
        roll153 = engine.roll_d10()
        cs153_new = dict(cs153)
        cs153_new["cert_theft_used"] = True
        player.combat_state = cs153_new
        if roll153 <= 3:
            player.licenze = max(0, player.licenze - 3)
            success153 = False
        else:
            if target153.certificazioni > 0:
                # Addon 154 (Recertification): target gains 5L when losing a cert
                if _has_addon_addon(target153, 154):
                    target153.licenze += 5
                target153.certificazioni -= 1
                player.certificazioni += 1
            success153 = True
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "cert_theft_result",
            "player_id": player.id,
            "target_id": target153.id,
            "roll": roll153,
            "success": success153,
        })
        await _broadcast_state(game, db)
        return

    # Addon 158 (Credential Vault): roll dice; if 10, gain 1 cert
    elif addon.number == 158:
        cs158 = player.combat_state or {}
        if cs158.get("cred_vault_used"):
            await _error(game.code, user_id, "Credential Vault already used this game")
            pa.is_tapped = False
            return
        roll158 = engine.roll_d10()
        cs158_new = dict(cs158)
        cs158_new["cred_vault_used"] = True
        player.combat_state = cs158_new
        if roll158 == 10:
            player.certificazioni += 1
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "credential_vault_roll",
            "player_id": player.id,
            "roll": roll158,
            "success": roll158 == 10,
        })
        await _broadcast_state(game, db)
        return

    # Addon 159 (Final Exam): dice duel with opponent; winner steals 1 cert from loser
    elif addon.number == 159:
        cs159 = player.combat_state or {}
        if cs159.get("final_exam_used"):
            await _error(game.code, user_id, "Final Exam already used this game")
            pa.is_tapped = False
            return
        target_id159 = data.get("target_player_id")
        target159 = next((p for p in game.players if p.id == target_id159), None)
        if not target159 or target159.id == player.id:
            await _error(game.code, user_id, "Invalid target for Final Exam")
            pa.is_tapped = False
            return
        roll_p159 = engine.roll_d10()
        roll_t159 = engine.roll_d10()
        cs159_new = dict(cs159)
        cs159_new["final_exam_used"] = True
        player.combat_state = cs159_new
        if roll_p159 > roll_t159:
            if target159.certificazioni > 0:
                if _has_addon_addon(target159, 154):  # Recertification
                    target159.licenze += 5
                target159.certificazioni -= 1
                player.certificazioni += 1
        elif roll_t159 > roll_p159:
            if player.certificazioni > 0:
                if _has_addon_addon(player, 154):  # Recertification
                    player.licenze += 5
                player.certificazioni -= 1
                target159.certificazioni += 1
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "final_exam_result",
            "player_id": player.id,
            "target_id": target159.id,
            "player_roll": roll_p159,
            "target_roll": roll_t159,
        })
        await _broadcast_state(game, db)
        return

    # ── Active addon effects (161-180) ──────────────────────────────────────

    # Addon 164 (Cross-Training): use passive ability of another player for 1 full turn
    elif addon.number == 164:
        # TODO: implement when role passive ability system is ready
        await _error(game.code, user_id, "Cross-Training: role system not yet implemented")
        pa.is_tapped = False
        return

    # Addon 165 (Skill Transfer): swap roles with an opponent for 2 turns
    elif addon.number == 165:
        # TODO: implement when role swap system is ready
        await _error(game.code, user_id, "Skill Transfer: role system not yet implemented")
        pa.is_tapped = False
        return

    # Addon 166 (Parallel Career): gain certifications × 3 Licenze
    elif addon.number == 166:
        cs166 = player.combat_state or {}
        if cs166.get("parallel_career_used"):
            await _error(game.code, user_id, "Parallel Career already used this game")
            pa.is_tapped = False
            return
        gain166 = player.certificazioni * 3
        player.licenze += gain166
        cs166_new = dict(cs166)
        cs166_new["parallel_career_used"] = True
        player.combat_state = cs166_new

    # Addon 169 (Performance Review): compare boss defeats with target
    elif addon.number == 169:
        cs169 = player.combat_state or {}
        if cs169.get("perf_review_used"):
            await _error(game.code, user_id, "Performance Review already used this game")
            pa.is_tapped = False
            return
        target_id169 = data.get("target_player_id")
        target169 = next((p for p in game.players if p.id == target_id169), None)
        if not target169 or target169.id == player.id:
            await _error(game.code, user_id, "Invalid target for Performance Review")
            pa.is_tapped = False
            return
        _my_defeats169 = player.bosses_defeated or (player.combat_state or {}).get("boss_defeats_count", 0)
        _their_defeats169 = target169.bosses_defeated or (target169.combat_state or {}).get("boss_defeats_count", 0)
        cs169_new = dict(cs169)
        cs169_new["perf_review_used"] = True
        player.combat_state = cs169_new
        if _their_defeats169 > _my_defeats169:
            player.licenze += 3
            outcome169 = "licenze"
        elif _my_defeats169 > _their_defeats169:
            cs169_new["perf_review_cert_bonus"] = True  # score bonus, not actual cert
            player.combat_state = cs169_new
            outcome169 = "cert_bonus"
        else:
            outcome169 = "tie"
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": "perf_review_result",
            "player_id": player.id,
            "target_id": target169.id,
            "outcome": outcome169,
        })
        await _broadcast_state(game, db)
        return

    # Addon 170 (Promotion): increase seniority by 1 level for 5 turns
    elif addon.number == 170:
        cs170 = player.combat_state or {}
        if cs170.get("promotion_used"):
            await _error(game.code, user_id, "Promotion already used this game")
            pa.is_tapped = False
            return
        from app.models.game import Seniority as _Sen170, SENIORITY_HP as _HP170
        _SENIORITY_LIST170 = [
            _Sen170.junior, _Sen170.experienced, _Sen170.senior, _Sen170.evangelist,
        ]
        cs170_new = dict(cs170)
        cs170_new["promotion_used"] = True
        cs170_new["promotion_turns_remaining"] = 5
        cs170_new["promotion_original_seniority"] = player.seniority.value if player.seniority else None
        # Temporarily increase seniority
        try:
            _cur_idx170 = _SENIORITY_LIST170.index(player.seniority)
            if _cur_idx170 < len(_SENIORITY_LIST170) - 1:
                _new_seniority170 = _SENIORITY_LIST170[_cur_idx170 + 1]
                player.seniority = _new_seniority170
                player.max_hp = _HP170[_new_seniority170]
                player.hp = min(player.hp + 1, player.max_hp)
        except (ValueError, TypeError):
            pass
        player.combat_state = cs170_new

    # Addon 171 (Mazzo Corrotto): each opponent loses 1L per card in hand (max 5L per opponent)
    elif addon.number == 171:
        cs171 = player.combat_state or {}
        if cs171.get("mazzo_corrotto_used"):
            await _error(game.code, user_id, "Mazzo Corrotto already used this game")
            pa.is_tapped = False
            return
        for _p171 in game.players:
            if _p171.id == player.id:
                continue
            _hand_count171 = len(list(_p171.hand))
            _loss171 = min(_hand_count171, 5)
            _p171.licenze = max(0, _p171.licenze - _loss171)
        cs171_new = dict(cs171)
        cs171_new["mazzo_corrotto_used"] = True
        player.combat_state = cs171_new

    # Addon 172 (Deck Shuffle): shuffle the shared action deck (once per turn)
    elif addon.number == 172:
        import random as _r172
        if game.action_deck_1:
            _deck172_1 = list(game.action_deck_1)
            _r172.shuffle(_deck172_1)
            game.action_deck_1 = _deck172_1
        if game.action_deck_2:
            _deck172_2 = list(game.action_deck_2)
            _r172.shuffle(_deck172_2)
            game.action_deck_2 = _deck172_2

    # Addon 173 (Card Graveyard): passive — allow manual peek at action discard pile
    elif addon.number == 173:
        # This is a passive — no activation needed; allow manual "peek" action
        discard173 = list(game.action_discard or [])
        db.commit()
        db.refresh(game)
        await manager.send_to_player(game.code, player.user_id, {
            "type": "card_graveyard_view",
            "discard_pile": discard173,
        })
        pa.is_tapped = False  # passive, don't tap
        return

    # Addon 174 (Recycle Bin): put up to 2 cards from discard back to bottom of main deck
    elif addon.number == 174:
        card_ids174 = data.get("card_ids", [])
        if not card_ids174 or len(card_ids174) > 2:
            await _error(game.code, user_id, "Provide 1-2 card IDs from discard")
            pa.is_tapped = False
            return
        discard174 = list(game.action_discard or [])
        for cid174 in card_ids174:
            if cid174 not in discard174:
                await _error(game.code, user_id, f"Card {cid174} not in discard")
                pa.is_tapped = False
                return
            discard174.remove(cid174)
            if game.action_deck_1 is not None:
                game.action_deck_1 = game.action_deck_1 + [cid174]
            else:
                game.action_deck_2 = (game.action_deck_2 or []) + [cid174]
        game.action_discard = discard174

    # Addon 175 (Boss Reshuffle): reshuffle the boss deck completely
    elif addon.number == 175:
        cs175 = player.combat_state or {}
        if cs175.get("boss_reshuffle_used"):
            await _error(game.code, user_id, "Boss Reshuffle already used this game")
            pa.is_tapped = False
            return
        import random as _r175
        if game.boss_deck_1:
            _deck175_1 = list(game.boss_deck_1)
            _r175.shuffle(_deck175_1)
            game.boss_deck_1 = _deck175_1
        if game.boss_deck_2:
            _deck175_2 = list(game.boss_deck_2)
            _r175.shuffle(_deck175_2)
            game.boss_deck_2 = _deck175_2
        cs175_new = dict(cs175)
        cs175_new["boss_reshuffle_used"] = True
        player.combat_state = cs175_new

    # Addon 176 (Mazzo Infetto): target opponent discards entire hand and draws the same number
    elif addon.number == 176:
        cs176 = player.combat_state or {}
        if cs176.get("mazzo_infetto_used"):
            await _error(game.code, user_id, "Mazzo Infetto already used this game")
            pa.is_tapped = False
            return
        target_id176 = data.get("target_player_id")
        target176 = next((p for p in game.players if p.id == target_id176), None)
        if not target176 or target176.id == player.id:
            await _error(game.code, user_id, "Invalid target for Mazzo Infetto")
            pa.is_tapped = False
            return
        from app.models.game import PlayerHandCard as _PHC176
        _hand176 = list(target176.hand)
        _count176 = len(_hand176)
        for hc176 in _hand176:
            game.action_discard = (game.action_discard or []) + [hc176.action_card_id]
            db.delete(hc176)
        for _ in range(_count176):
            if game.action_deck_1:
                _cid176 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _cid176 = game.action_deck_2.pop(0)
            else:
                break
            db.add(_PHC176(player_id=target176.id, action_card_id=_cid176))
        cs176_new = dict(cs176)
        cs176_new["mazzo_infetto_used"] = True
        player.combat_state = cs176_new

    # Addon 178 (Cold Cache): current boss loses 3HP
    elif addon.number == 178:
        cs178 = player.combat_state or {}
        if cs178.get("cold_cache_used"):
            await _error(game.code, user_id, "Cold Cache already used this game")
            pa.is_tapped = False
            return
        if not player.is_in_combat or player.current_boss_hp is None:
            await _error(game.code, user_id, "Not in combat")
            pa.is_tapped = False
            return
        player.current_boss_hp = max(0, player.current_boss_hp - 3)
        cs178_new = dict(cs178)
        cs178_new["cold_cache_used"] = True
        player.combat_state = cs178_new
        if player.current_boss_hp <= 0:
            from app.models.card import BossCard as _BC178
            boss178 = db.get(_BC178, player.current_boss_id)
            if boss178:
                from app.websocket.handlers.combat.roll import _boss_defeat_sequence as _bds178
                db.commit()
                db.refresh(game)
                await _bds178(player, game, db, boss178)
                return

    # Addon 179 (Hot Reload): discard entire hand, draw same number of cards
    elif addon.number == 179:
        from app.models.game import PlayerHandCard as _PHC179
        _hand179 = list(player.hand)
        _count179 = len(_hand179)
        if _count179 == 0:
            await _error(game.code, user_id, "Hand is empty")
            pa.is_tapped = False
            return
        for hc179 in _hand179:
            game.action_discard = (game.action_discard or []) + [hc179.action_card_id]
            db.delete(hc179)
        for _ in range(_count179):
            if game.action_deck_1:
                _cid179 = game.action_deck_1.pop(0)
            elif game.action_deck_2:
                _cid179 = game.action_deck_2.pop(0)
            else:
                break
            db.add(_PHC179(player_id=player.id, action_card_id=_cid179))

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_USED,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name, "effect": addon.effect},
    })
    await _broadcast_state(game, db)


async def _handle_fomo_buy_addon(game, user_id: int, data: dict, db):
    """Handle out-of-turn addon purchase triggered by Addon 147 (FOMO Trigger)."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    player = _get_player(game, user_id)
    if not player:
        return
    cs_fomo = player.combat_state or {}
    if not cs_fomo.get("fomo_trigger_pending"):
        await _error(game.code, user_id, "No FOMO trigger active")
        return
    # Clear FOMO pending flag and set bypass flag to skip turn ownership check
    cs_fomo_new = dict(cs_fomo)
    del cs_fomo_new["fomo_trigger_pending"]
    cs_fomo_new["fomo_bypass_turn"] = True
    player.combat_state = cs_fomo_new
    db.commit()
    # Delegate to normal buy logic with bypass flag set
    await _handle_buy_addon(game, user_id, data, db)
    # Clean up bypass flag
    cs_after = dict(player.combat_state or {})
    cs_after.pop("fomo_bypass_turn", None)
    player.combat_state = cs_after
    db.commit()


async def _handle_appexchange_pick(game, user_id: int, data: dict, db):
    """Handle the player picking one addon from AppExchange Marketplace choices."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    pending = list(cs.get("appexchange_pending") or [])
    if not pending:
        await _error(game.code, user_id, "No AppExchange choice pending")
        return
    chosen_id = data.get("addon_id")
    if chosen_id not in pending:
        await _error(game.code, user_id, "Invalid addon choice")
        return
    from app.models.game import PlayerAddon as _PAex
    db.add(_PAex(player_id=player.id, addon_id=chosen_id))
    # Return unchosen addons to front of deck_1
    for aid in pending:
        if aid != chosen_id:
            game.addon_deck_1 = [aid] + (game.addon_deck_1 or [])
    cs_new = dict(cs)
    cs_new.pop("appexchange_pending", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_BOUGHT,
        "player_id": player.id,
        "addon": {"id": chosen_id},
        "source": "appexchange",
    })
    await _broadcast_state(game, db)


async def _handle_chatter_feed_respond(game, user_id: int, data: dict, db):
    """Handle the target responding to a Chatter Feed card request."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    responder = _get_player(game, user_id)
    if not responder:
        return
    cs_resp = responder.combat_state or {}
    requester_id = cs_resp.get("chatter_feed_pending_requester_id")
    if not requester_id:
        await _error(game.code, user_id, "No Chatter Feed request pending")
        return
    requester19 = next((p for p in game.players if p.id == requester_id), None)
    if not requester19:
        return
    hand_card_id19 = data.get("hand_card_id")
    from app.models.game import PlayerHandCard as _PHC19r
    hc19r = db.get(_PHC19r, hand_card_id19)
    if not hc19r or hc19r.player_id != responder.id:
        await _error(game.code, user_id, "Card not in your hand")
        return
    # Transfer card to requester
    hc19r.player_id = requester19.id
    # Clear flags
    cs_resp_new = dict(cs_resp)
    cs_resp_new.pop("chatter_feed_pending_requester_id", None)
    responder.combat_state = cs_resp_new
    cs_req19 = dict(requester19.combat_state or {})
    cs_req19.pop("chatter_feed_pending_from_id", None)
    requester19.combat_state = cs_req19
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_metadata_api_reorder(game, user_id: int, data: dict, db):
    """Handle Addon 49 (Metadata API): client sends reordered card_ids for top of deck."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    pending49 = list(cs.get("metadata_api_pending") or [])
    if not pending49:
        await _error(game.code, user_id, "No Metadata API reorder pending")
        return
    reordered = data.get("card_ids", [])
    if sorted(reordered) != sorted(pending49):
        await _error(game.code, user_id, "card_ids must be a permutation of the peeked cards")
        return
    n49 = len(reordered)
    # Replace first N cards in action_deck_1 with reordered list
    if game.action_deck_1 and len(game.action_deck_1) >= n49:
        game.action_deck_1 = list(reordered) + game.action_deck_1[n49:]
    elif game.action_deck_1:
        game.action_deck_1 = list(reordered) + game.action_deck_1[len(game.action_deck_1):]
    cs_new = dict(cs)
    cs_new.pop("metadata_api_pending", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_release_notes_confirm(game, user_id: int, data: dict, db):
    """Handle Addon 60 (Release Notes): player decides to fight or skip the peeked boss."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    from app.websocket.handlers.combat.start import _handle_start_combat
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    _pending_boss60 = cs.get("release_notes_pending_boss_id")
    _pending_source60 = cs.get("release_notes_pending_source")
    if not _pending_boss60 or not _pending_source60:
        await _error(game.code, user_id, "No Release Notes decision pending")
        return
    decision = data.get("decision")  # "fight" or "skip"
    cs_new = dict(cs)
    cs_new.pop("release_notes_pending_boss_id", None)
    cs_new.pop("release_notes_pending_source", None)
    player.combat_state = cs_new
    if decision == "fight":
        # Re-delegate to start_combat with the same source; boss is still at top of deck
        db.commit()
        db.refresh(game)
        await _handle_start_combat(game, user_id, {"source": _pending_source60}, db)
    else:
        # skip: leave boss at top of deck, do nothing
        db.commit()
        db.refresh(game)
        await _broadcast_state(game, db)


async def _handle_sharing_rules_pick(game, user_id: int, data: dict, db):
    """Handle Addon 63 (Sharing Rules): player picks a card to copy from target's hand."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    _pending_target63 = cs.get("sharing_rules_pending_target_id")
    if not _pending_target63:
        await _error(game.code, user_id, "No Sharing Rules pick pending")
        return
    action_card_id63 = data.get("action_card_id")
    # Verify target still has this card
    target63 = next((p for p in game.players if p.id == _pending_target63), None)
    if not target63:
        await _error(game.code, user_id, "Target player not found")
        return
    _has_card = any(hc.action_card_id == action_card_id63 for hc in target63.hand)
    if not _has_card:
        await _error(game.code, user_id, "Target no longer has that card")
        return
    from app.models.game import PlayerHandCard as _PHC63
    db.add(_PHC63(player_id=player.id, action_card_id=action_card_id63))
    cs_new = dict(cs)
    cs_new.pop("sharing_rules_pending_target_id", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_beta_feature_reject(game, user_id: int, data: dict, db):
    """Handle Addon 92 (Beta Feature): reject just-bought addon and draw another from deck."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    pending_pa_id = cs.get("beta_feature_pending_pa_id")
    pending_addon_id = cs.get("beta_feature_pending_addon_id")
    if not pending_pa_id:
        await _error(game.code, user_id, "No Beta Feature rejection pending")
        return
    from app.models.game import PlayerAddon as _PA92r
    pa92 = db.get(_PA92r, pending_pa_id)
    if pa92 and pa92.player_id == player.id:
        # Return rejected addon to top of deck_1
        game.addon_deck_1 = [pending_addon_id] + (game.addon_deck_1 or [])
        db.delete(pa92)
    # Draw next addon from deck as replacement
    next_addon_id = None
    if game.addon_deck_1:
        addon_deck92 = list(game.addon_deck_1)
        next_addon_id = addon_deck92.pop(0)
        game.addon_deck_1 = addon_deck92
    elif game.addon_deck_2:
        addon_deck92b = list(game.addon_deck_2)
        next_addon_id = addon_deck92b.pop(0)
        game.addon_deck_2 = addon_deck92b
    if next_addon_id:
        from app.models.game import PlayerAddon as _PA92n
        db.add(_PA92n(player_id=player.id, addon_id=next_addon_id, is_tapped=False))
    cs_new = dict(cs)
    cs_new.pop("beta_feature_pending_pa_id", None)
    cs_new.pop("beta_feature_pending_addon_id", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_beta_feature_keep(game, user_id: int, data: dict, db):
    """Handle Addon 92 (Beta Feature): keep the just-bought addon."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    if not cs.get("beta_feature_pending_pa_id"):
        await _error(game.code, user_id, "No Beta Feature choice pending")
        return
    cs_new = dict(cs)
    cs_new.pop("beta_feature_pending_pa_id", None)
    cs_new.pop("beta_feature_pending_addon_id", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_pilot_program_pick(game, user_id: int, data: dict, db):
    """Handle Addon 93 (Pilot Program): player picks an addon from the graveyard."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    if not cs.get("pilot_program_pending"):
        await _error(game.code, user_id, "No Pilot Program pick pending")
        return
    addon_card_id93 = data.get("addon_card_id")
    graveyard93 = list(game.addon_graveyard or [])
    if addon_card_id93 not in graveyard93:
        await _error(game.code, user_id, "Addon not in graveyard")
        return
    graveyard93.remove(addon_card_id93)
    game.addon_graveyard = graveyard93
    from app.models.game import PlayerAddon as _PA93p
    db.add(_PA93p(player_id=player.id, addon_id=addon_card_id93, is_tapped=False))
    cs_new = dict(cs)
    cs_new.pop("pilot_program_pending", None)
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_acceptance_criteria_choose(game, user_id: int, data: dict, db):
    """Handle Addon 98 (Acceptance Criteria): choose licenze or 2 cards after boss defeat.
    NOTE: This is only called if the non-simplified flow is used.
    The simplified flow (see roll.py) always gives 2 cards and skips licenze.
    """
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    pending_reward = cs.get("acceptance_criteria_pending_reward")
    if pending_reward is None:
        await _error(game.code, user_id, "No Acceptance Criteria choice pending")
        return
    choice = data.get("choice")
    cs_new = dict(cs)
    cs_new.pop("acceptance_criteria_pending_reward", None)
    if choice == "licenze":
        player.licenze += pending_reward
    else:
        # Draw 2 action cards
        from app.models.game import PlayerHandCard as _PHC98
        for _ in range(2):
            if game.action_deck_1:
                db.add(_PHC98(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            elif game.action_deck_2:
                db.add(_PHC98(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
    player.combat_state = cs_new
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_external_object_pick(game, user_id: int, data: dict, db):
    """Handle Addon 130 (External Object): pick addon from graveyard paying its normal cost."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    player = _get_player(game, user_id)
    if not player:
        return
    cs = player.combat_state or {}
    if not cs.get("external_object_pending"):
        await _error(game.code, user_id, "No External Object pick pending")
        return
    addon_card_id130 = data.get("addon_card_id")
    graveyard130 = list(game.addon_graveyard or [])
    if addon_card_id130 not in graveyard130:
        await _error(game.code, user_id, "Addon not in graveyard")
        return
    from app.models.card import AddonCard as _AC130
    ac130 = db.get(_AC130, addon_card_id130)
    if not ac130:
        await _error(game.code, user_id, "Addon card not found")
        return
    cost130 = ac130.cost
    if player.licenze < cost130:
        await _error(game.code, user_id, f"Need {cost130}L to acquire this addon (have {player.licenze}L)")
        return
    player.licenze -= cost130
    graveyard130.remove(addon_card_id130)
    game.addon_graveyard = graveyard130
    from app.models.game import PlayerAddon as _PA130
    db.add(_PA130(player_id=player.id, addon_id=addon_card_id130, is_tapped=False))
    cs_new130 = dict(cs)
    cs_new130.pop("external_object_pending", None)
    player.combat_state = cs_new130
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)


async def _handle_batch_schedule_card(game, user_id: int, data: dict, db):
    """Handle Addon 113 (Batch Apex Scheduler): schedule a card for next turn."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    from app.game.engine_addons import has_addon as _has_addon_bs
    player = _get_player(game, user_id)
    if not player:
        return
    if not _has_addon_bs(player, 113):
        await _error(game.code, user_id, "You don't have Batch Apex Scheduler")
        return
    hand_card_id113 = data.get("hand_card_id")
    from app.models.game import PlayerHandCard as _PHC113
    hc113 = db.get(_PHC113, hand_card_id113)
    if not hc113 or hc113.player_id != player.id:
        await _error(game.code, user_id, "Card not in hand")
        return
    cs113 = dict(player.combat_state or {})
    if cs113.get("batch_scheduled_card_id"):
        await _error(game.code, user_id, "Already have a scheduled card")
        return
    cs113["batch_scheduled_card_id"] = hc113.action_card_id
    player.combat_state = cs113
    db.delete(hc113)
    db.commit()
    db.refresh(game)
    await manager.send_to_player(game.code, player.user_id, {
        "type": "batch_schedule_confirmed",
        "scheduled_card_id": cs113["batch_scheduled_card_id"],
    })
    await _broadcast_state(game, db)


async def _handle_territory_set(game, user_id: int, data: dict, db):
    """Handle Addon 126 (Territory Management): set territory target player."""
    from app.websocket.game_helpers import _get_player, _error, _broadcast_state
    from app.game.engine_addons import has_addon as _has_addon_ts
    player = _get_player(game, user_id)
    if not player:
        return
    if not _has_addon_ts(player, 126):
        await _error(game.code, user_id, "You don't have Territory Management")
        return
    target_id126 = data.get("target_player_id")
    target126 = next((p for p in game.players if p.id == target_id126), None)
    if not target126 or target126.id == player.id:
        await _error(game.code, user_id, "Invalid target")
        return
    cs126 = dict(player.combat_state or {})
    cs126["territory_player_id"] = target_id126
    player.combat_state = cs126
    db.commit()
    db.refresh(game)
    await _broadcast_state(game, db)
