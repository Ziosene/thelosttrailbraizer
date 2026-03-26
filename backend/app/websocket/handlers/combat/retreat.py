"""
Combat retreat handler: _handle_retreat
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
    # Boss goes back to its origin: deck → top of deck; market → back to its market slot
    if source == "deck":
        game.boss_deck = [boss_id] + (game.boss_deck or [])
    elif source == "market_1":
        game.boss_market_1 = boss_id
    elif source == "market_2":
        game.boss_market_2 = boss_id
    player.is_in_combat = False
    player.current_boss_id = None
    player.current_boss_hp = None
    player.current_boss_source = None
    # Card 285 (Trailhead Superbadge): reset consecutive defeat counter on retreat
    if (player.combat_state or {}).get("superbadge_tracking"):
        _cs_sb_ret = dict(player.combat_state)
        _cs_sb_ret["superbadge_defeats"] = 0
        player.combat_state = _cs_sb_ret
    game.current_phase = TurnPhase.action
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.COMBAT_ENDED,
        "player_id": player.id,
        "retreated": True,
    })
    await _broadcast_state(game, db)
