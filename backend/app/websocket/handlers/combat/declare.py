"""
Card declaration handlers: _handle_declare_card, _handle_declare_card_type
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
