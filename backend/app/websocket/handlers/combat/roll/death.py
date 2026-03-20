"""Player death sequence handler."""
import random
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.game_helpers import _broadcast_state
from app.models.game import GameSession, TurnPhase
from app.game import engine
from app.game.engine_addons import has_addon, get_addon_pa


async def _player_death_sequence(player, game, db, boss) -> None:
    """Handle player death sequence after a combat roll."""

    # Addon 56 (Backup & Restore): cancel death once per game — full HP, reset combat
    if has_addon(player, 56):
        _cs56 = player.combat_state or {}
        if not _cs56.get("backup_restore_used"):
            _cs56_new = dict(_cs56)
            _cs56_new["backup_restore_used"] = True
            player.combat_state = _cs56_new
            player.hp = player.max_hp
            player.is_in_combat = False
            player.current_boss_id = None
            player.current_boss_hp = None
            player.current_boss_source = None
            player.combat_round = None
            game.current_phase = TurnPhase.action
            db.commit()
            db.refresh(game)
            await manager.broadcast(game.code, {"type": "backup_restore_triggered", "player_id": player.id})
            await _broadcast_state(game, db)
            return  # skip all death logic

    # Addon 59 (Incident Management): on death, roll d10 — if ≥8 survive at 1 HP
    if has_addon(player, 59):
        _survival_roll59 = engine.roll_d10()
        if _survival_roll59 >= 8:
            player.hp = 1
            player.is_in_combat = False
            player.current_boss_id = None
            player.current_boss_hp = None
            player.current_boss_source = None
            player.combat_round = None
            game.current_phase = TurnPhase.action
            db.commit()
            db.refresh(game)
            await manager.broadcast(game.code, {
                "type": "incident_management_survival",
                "player_id": player.id,
                "roll": _survival_roll59,
            })
            await _broadcast_state(game, db)
            return  # survived, skip death

    # Addon 116 (Platform Event): when any player dies, all OTHER players with addon 116 gain 2L
    for _p116 in game.players:
        if _p116.id != player.id and has_addon(_p116, 116):
            _p116.licenze += 2

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
    # Addon 57 (Disaster Recovery): on death, don't lose card
    if "card" in penalty["lost"] and not has_addon(player, 57):
        lost_card_id = penalty["lost"]["card"]
        hc_to_remove = next((hc for hc in player.hand if hc.action_card_id == lost_card_id), None)
        if hc_to_remove:
            game.action_discard = (game.action_discard or []) + [lost_card_id]
            db.delete(hc_to_remove)

    # Addon 132 (Summer Release): when any of player's addons go to graveyard on death, draw 1 card (max 3)
    if has_addon(player, 132):
        _addons_count132 = len(player.addons)
        if _addons_count132 > 0:
            for _ in range(min(_addons_count132, 3)):
                if game.action_deck_1:
                    _cid132 = game.action_deck_1.pop(0)
                elif game.action_deck_2:
                    _cid132 = game.action_deck_2.pop(0)
                else:
                    break
                from app.models.game import PlayerHandCard as _PHC132
                db.add(_PHC132(player_id=player.id, action_card_id=_cid132))

    # Remove lost addon
    # Addon 23 (Field Service Mobile): if dying outside own turn, skip addon loss
    _is_own_turn23 = (
        bool(game.turn_order) and
        game.turn_order[game.current_turn_index] == player.id
    )
    _skip_addon_loss23 = has_addon(player, 23) and not _is_own_turn23
    if "addon" in penalty["lost"] and not _skip_addon_loss23:
        lost_addon_id = penalty["lost"]["addon"]
        pa_to_remove = next((pa for pa in player.addons if pa.addon_id == lost_addon_id), None)
        if pa_to_remove:
            # Addon 200 (The Lost Trailbraizer): skip graveyard (already deleted above)
            if not (pa_to_remove.card and pa_to_remove.card.number == 200):
                game.addon_graveyard = (game.addon_graveyard or []) + [lost_addon_id]
                db.delete(pa_to_remove)

    player.licenze = penalty["licenze"]
    player.hp = player.max_hp  # respawn with full HP

    # Boss 91 (List View Usurper): clear hand_hidden_in_combat on player death
    if player.combat_state and player.combat_state.get("hand_hidden_in_combat"):
        _cs91d = dict(player.combat_state)
        _cs91d.pop("hand_hidden_in_combat", None)
        player.combat_state = _cs91d

    # Addon 81 (Boss Vulnerability Scan): clear per-combat used flag on player death
    if player.combat_state and player.combat_state.get("vulnerability_scan_used"):
        _cs81d = dict(player.combat_state)
        _cs81d.pop("vulnerability_scan_used", None)
        player.combat_state = _cs81d

    # Boss 31 (AppExchange Parasite): on player death the locked addon is ALSO discarded
    # (in addition to the normal death-penalty addon). GDD option B.
    if player.combat_state and player.combat_state.get("locked_addon_id"):
        _locked_pa_id = player.combat_state["locked_addon_id"]
        from app.models.game import PlayerAddon as _PA31
        _pa31 = db.get(_PA31, _locked_pa_id)
        if _pa31 and _pa31.player_id == player.id:
            game.addon_graveyard = (game.addon_graveyard or []) + [_pa31.addon_id]
            db.delete(_pa31)
        _cs31 = dict(player.combat_state)
        _cs31.pop("locked_addon_id", None)
        player.combat_state = _cs31

    # Addon 200 (The Lost Trailbraizer): vanishes forever on death — delete permanently before graveyard loop
    _pa200_death = get_addon_pa(player, 200)
    if _pa200_death:
        db.delete(_pa200_death)
        db.flush()

    # GDD §6: tutti gli AddOn rimanenti si tappano alla morte
    # Card 84 (Renewal Opportunity): first addon is spared if player paid 5L proactively
    _renewal = (player.combat_state or {}).get("renewal_protected", False)
    _first_addon_spared = False
    for pa_death in list(player.addons):
        # Addon 200 (The Lost Trailbraizer): already deleted above, skip
        if pa_death.card and pa_death.card.number == 200:
            continue
        if _renewal and not _first_addon_spared:
            _first_addon_spared = True
            continue  # protect this one addon from tapping
        pa_death.is_tapped = True
    if _renewal:
        cs_ren = dict(player.combat_state)
        cs_ren.pop("renewal_protected", None)
        player.combat_state = cs_ren

    # Addon 7 (Flow Automation): clean up no_damage_this_combat flag on death
    if (player.combat_state or {}).get("no_damage_this_combat"):
        _cs7_death = dict(player.combat_state)
        _cs7_death.pop("no_damage_this_combat", None)
        player.combat_state = _cs7_death

    # Addon 141 (Calculated Risk): clear flag on player death
    if (player.combat_state or {}).get("calculated_risk_active"):
        _cs141_death = dict(player.combat_state)
        _cs141_death.pop("calculated_risk_active", None)
        player.combat_state = _cs141_death

    # Addon 152 (Superbadge Grind): reset streak on death
    if has_addon(player, 152):
        cs152d = dict(player.combat_state or {})
        cs152d["superbadge_grind_streak"] = 0
        player.combat_state = cs152d

    # Addon 154 (Recertification): cert loss on death not implemented (certs not reduced on death in GDD)
    # Recertification trigger on cert theft is handled in addon.py addon 153

    # Addon 48 (Net Zero Tracker): reset turn counter on death
    if has_addon(player, 48):
        _cs48d = dict(player.combat_state or {})
        _cs48d["net_zero_turns"] = 0
        player.combat_state = _cs48d

    # Addon 105 (Epic Feature): reset boss-defeat streak on death
    if has_addon(player, 105):
        _cs105d = dict(player.combat_state or {})
        _cs105d["epic_feature_streak"] = 0
        player.combat_state = _cs105d

    # Addon 52 (Scratch Org): trim excess cards at end of combat (player death)
    if has_addon(player, 52):
        db.flush()
        hand52d = list(player.hand)
        while len(hand52d) > engine.MAX_HAND_SIZE:
            excess52d = hand52d.pop()
            game.action_discard = (game.action_discard or []) + [excess52d.action_card_id]
            db.delete(excess52d)

    # Addon 6 (Sandbox Shield): first death no licenze loss
    _cs6 = player.combat_state or {}
    if has_addon(player, 6) and not _cs6.get("sandbox_shield_used"):
        # Revert the licenze penalty — set licenze back (penalty was already deducted by engine)
        player.licenze = penalty["licenze"] + penalty["lost"].get("licenza", 0)
        cs6_new = dict(_cs6)
        cs6_new["sandbox_shield_used"] = True
        player.combat_state = cs6_new

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

    return penalty
