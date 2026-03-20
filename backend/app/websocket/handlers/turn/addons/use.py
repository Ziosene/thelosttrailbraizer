"""
Addon use handler: _handle_use_addon dispatcher.
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
from app.websocket.handlers.turn.addons.combat import handle_combat_effects
from app.websocket.handlers.turn.addons.hand import handle_hand_effects
from app.websocket.handlers.turn.addons.market import handle_market_effects
from app.websocket.handlers.turn.addons.social import handle_social_effects
from app.websocket.handlers.turn.addons.economy import handle_economy_effects
from app.websocket.handlers.turn.addons.role import handle_role_effects


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

    # Dispatch to the appropriate category effects handler.
    # Return values:
    #   "done" = addon handled its own db.commit() + broadcast; do NOT do final broadcast
    #   True   = addon modified state but needs the final db.commit() + ADDON_USED broadcast
    #   False  = addon number not in this category; try next handler
    handled = await handle_combat_effects(addon.number, game, user_id, data, player, pa, db)
    if not handled:
        handled = await handle_hand_effects(addon.number, game, user_id, data, player, pa, db)
    if not handled:
        handled = await handle_market_effects(addon.number, game, user_id, data, player, pa, db)
    if not handled:
        handled = await handle_social_effects(addon.number, game, user_id, data, player, pa, db)
    if not handled:
        handled = await handle_economy_effects(addon.number, game, user_id, data, player, pa, db)
    if not handled:
        handled = await handle_role_effects(addon.number, game, user_id, data, player, pa, db)

    # If the handler returned "done", it already committed and broadcast; we're done.
    if handled == "done":
        return

    # Fall-through: commit state changes and broadcast ADDON_USED
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_USED,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name, "effect": addon.effect},
    })
    await _broadcast_state(game, db)
