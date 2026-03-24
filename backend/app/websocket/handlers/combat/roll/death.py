"""Player death sequence handler."""
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.game_helpers import _broadcast_state
from app.models.game import GameSession, TurnPhase
from app.game import engine
from app.game.engine_addons import has_addon, get_addon_pa


async def _player_death_sequence(player, game, db, boss) -> bool:
    """
    Handle player death after a combat roll.

    Returns True if death was PREVENTED (addon 56/59 saved the player — already committed+broadcast).
    Returns False if death HAPPENED — dice.py must commit + broadcast.
    """

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
            return True

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
            return True

    # ── Death confirmed ────────────────────────────────────────────────────

    # Addon 116 (Platform Event): all OTHER players with addon 116 gain 2L
    for _p116 in game.players:
        if _p116.id != player.id and has_addon(_p116, 116):
            _p116.licenze += 2

    # ── Licenza penalty ────────────────────────────────────────────────────
    _licenze_loss = engine.DEATH_LOSE_LICENZE  # default 1

    # Boss 14 (Great Data Reaper): death costs 2 Licenze
    _extra_l = engine.boss_death_licenze_penalty(boss.id) - engine.DEATH_LOSE_LICENZE
    if _extra_l > 0:
        _licenze_loss += _extra_l

    # Addon 6 (Sandbox Shield): first death no licenza loss
    _cs6 = player.combat_state or {}
    if has_addon(player, 6) and not _cs6.get("sandbox_shield_used"):
        _licenze_loss = 0
        cs6_new = dict(_cs6)
        cs6_new["sandbox_shield_used"] = True
        player.combat_state = cs6_new

    _actual_loss = min(_licenze_loss, player.licenze)
    player.licenze = max(0, player.licenze - _licenze_loss)

    # Boss 57 (Named Credentials Thief): lost licenze go to the opponent with most certs
    if engine.boss_death_licenze_to_top_cert(boss.id) and _actual_loss > 0:
        opponents_cert = [p for p in game.players if p.id != player.id]
        if opponents_cert:
            top = max(opponents_cert, key=lambda p: p.certificazioni)
            top.licenze += _actual_loss

    # ── State cleanups ─────────────────────────────────────────────────────

    # Boss 31 (AppExchange Parasite): locked addon is also discarded on death
    if (player.combat_state or {}).get("locked_addon_id"):
        _locked_pa_id = player.combat_state["locked_addon_id"]
        from app.models.game import PlayerAddon as _PA31
        _pa31 = db.get(_PA31, _locked_pa_id)
        if _pa31 and _pa31.player_id == player.id:
            game.addon_graveyard = (game.addon_graveyard or []) + [_pa31.addon_id]
            db.delete(_pa31)

    # Addon 200 (The Lost Trailbraizer): vanishes forever on death
    _pa200_death = get_addon_pa(player, 200)
    if _pa200_death:
        db.delete(_pa200_death)
        db.flush()

    # Build a clean combat_state preserving only cross-turn persistent flags
    _old_cs = player.combat_state or {}
    _new_cs: dict = {}
    for _k in ("object_store_licenze", "drip_program_remaining",
                "next_addon_price_fixed", "next_addon_price_discount",
                "sandbox_shield_used", "backup_restore_used"):
        if _k in _old_cs:
            _new_cs[_k] = _old_cs[_k]

    # Reset per-death streaks/counters
    if has_addon(player, 152):   # Superbadge Grind
        _new_cs["superbadge_grind_streak"] = 0
    if has_addon(player, 48):    # Net Zero Tracker
        _new_cs["net_zero_turns"] = 0
    if has_addon(player, 105):   # Epic Feature
        _new_cs["epic_feature_streak"] = 0

    # Signal that the player must still choose which card + addon to lose
    _new_cs["death_penalty_pending"] = True
    player.combat_state = _new_cs

    # ── Tap ALL remaining addons ───────────────────────────────────────────
    db.flush()  # ensure deleted addons (PA31, PA200) are gone before iterating
    for pa_death in list(player.addons):
        pa_death.is_tapped = True

    # ── Clear combat fields ────────────────────────────────────────────────
    player.hp = 0
    player.is_in_combat = False
    _source_death = player.current_boss_source
    player.current_boss_id = None
    player.current_boss_hp = None
    player.current_boss_source = None
    player.combat_round = None

    # Boss returns to top of its deck (market bosses stay in market)
    if _source_death == "deck_1":
        game.boss_deck_1 = [boss.id] + (game.boss_deck_1 or [])
    elif _source_death == "deck_2":
        game.boss_deck_2 = [boss.id] + (game.boss_deck_2 or [])

    game.current_phase = TurnPhase.action

    return False  # death happened — dice.py must commit + broadcast + send choice event
