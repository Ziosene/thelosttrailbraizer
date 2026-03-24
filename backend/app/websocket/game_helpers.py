"""
Shared helper functions used by all WebSocket action handlers.
Imported by handlers/lobby.py, handlers/turn.py, handlers/combat.py.
"""
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.models.game import GameSession, GamePlayer
from app.models.card import ActionCard, BossCard, AddonCard
from app.models.user import User
from app.game import engine


def _build_game_state(game: GameSession, db: Session) -> dict:
    current_player_id = None
    if game.turn_order and game.current_turn_index < len(game.turn_order):
        current_player_id = game.turn_order[game.current_turn_index]

    def _boss_info(boss_id: int | None) -> dict | None:
        if boss_id is None:
            return None
        b = db.get(BossCard, boss_id)
        return {
            "id": b.id, "name": b.name, "hp": b.hp, "threshold": b.dice_threshold,
            "ability": b.ability, "reward_licenze": b.reward_licenze, "difficulty": b.difficulty,
        } if b else None

    players = []
    for gp in game.players:
        user = db.get(User, gp.user_id)
        players.append({
            "id": gp.id,
            "user_id": gp.user_id,
            "nickname": user.nickname if user else "?",
            "seniority": gp.seniority,
            "role": gp.role,
            "hp": gp.hp,
            "max_hp": gp.max_hp,
            "licenze": gp.licenze,
            "certificazioni": gp.certificazioni,
            "hand_count": len(gp.hand),
            "addon_count": len(gp.addons),
            "addons": [
                {
                    "player_addon_id": pa.id,
                    "addon_id": pa.addon_id,
                    "name": (_ac := db.get(AddonCard, pa.addon_id)) and _ac.name or "?",
                    "effect": (_ac2 := db.get(AddonCard, pa.addon_id)) and _ac2.effect or "",
                    "is_tapped": pa.is_tapped,
                }
                for pa in gp.addons
            ],
            "is_in_combat": gp.is_in_combat,
            "is_eliminated": gp.is_eliminated,
            "bosses_defeated": gp.bosses_defeated,
            "trophies": gp.trophies or [],  # list of BossCard.id — visible to all players
            "current_boss": _boss_info(gp.current_boss_id) if gp.is_in_combat else None,
            "current_boss_hp": gp.current_boss_hp if gp.is_in_combat else None,
            "combat_round": gp.combat_round if gp.is_in_combat else None,
        })

    # Resolve visible market cards to full objects for the client
    def _addon_info(addon_id: int | None) -> dict | None:
        if addon_id is None:
            return None
        a = db.get(AddonCard, addon_id)
        return {"id": a.id, "name": a.name, "cost": a.cost, "effect": a.effect, "rarity": a.rarity} if a else None

    def _action_top(card_id: int | None) -> dict | None:
        if card_id is None:
            return None
        c = db.get(ActionCard, card_id)
        return {"id": c.id, "name": c.name, "card_type": c.card_type, "rarity": c.rarity} if c else None

    def _boss_top(card_id: int | None) -> dict | None:
        if card_id is None:
            return None
        b = db.get(BossCard, card_id)
        return {"id": b.id, "name": b.name, "difficulty": b.difficulty} if b else None

    def _addon_top(card_id: int | None) -> dict | None:
        if card_id is None:
            return None
        a = db.get(AddonCard, card_id)
        return {"id": a.id, "name": a.name, "rarity": a.rarity} if a else None

    action_discard = game.action_discard or []
    boss_graveyard = game.boss_graveyard or []
    addon_graveyard = game.addon_graveyard or []

    return {
        "type": ServerEvent.GAME_STATE,
        "game": {
            "id": game.id,
            "code": game.code,
            "status": game.status,
            "current_phase": game.current_phase,
            "turn_number": game.turn_number,
            "current_player_id": current_player_id,
            "action_deck_1_count": len(game.action_deck_1 or []),
            "action_deck_2_count": len(game.action_deck_2 or []),
            "action_discard_count": len(action_discard),
            "action_discard_top": _action_top(action_discard[-1] if action_discard else None),
            "boss_deck_1_count": len(game.boss_deck_1 or []),
            "boss_deck_2_count": len(game.boss_deck_2 or []),
            "boss_graveyard_count": len(boss_graveyard),
            "boss_graveyard_top": _boss_top(boss_graveyard[-1] if boss_graveyard else None),
            "boss_market_1": _boss_info(game.boss_market_1),
            "boss_market_2": _boss_info(game.boss_market_2),
            "addon_deck_1_count": len(game.addon_deck_1 or []),
            "addon_deck_2_count": len(game.addon_deck_2 or []),
            "addon_graveyard_count": len(addon_graveyard),
            "addon_graveyard_top": _addon_top(addon_graveyard[-1] if addon_graveyard else None),
            "addon_market_1": _addon_info(game.addon_market_1),
            "addon_market_2": _addon_info(game.addon_market_2),
            "players": players,
        },
    }


def _get_player(game: GameSession, user_id: int) -> GamePlayer | None:
    for p in game.players:
        if p.user_id == user_id:
            return p
    return None


def _is_player_turn(game: GameSession, player: GamePlayer) -> bool:
    if not game.turn_order:
        return False
    return game.turn_order[game.current_turn_index] == player.id


async def _error(game_code: str, user_id: int, msg: str):
    await manager.send_to_player(game_code, user_id, {"type": ServerEvent.ERROR, "message": msg})


async def _broadcast_state(game: GameSession, db: Session):
    state = _build_game_state(game, db)
    await manager.broadcast(game.code, state)


def _build_hand_state(player: GamePlayer, db: Session) -> dict:
    """Private payload sent only to the owning player — full hand + addon details."""
    hand_hidden = bool((player.combat_state or {}).get("hand_hidden_in_combat"))
    hand = []
    for hc in player.hand:
        if hand_hidden:
            hand.append({"hand_card_id": hc.id, "hidden": True})
        else:
            card = db.get(ActionCard, hc.action_card_id)
            if card:
                hand.append({
                    "hand_card_id": hc.id,
                    "card_id": card.id,
                    "name": card.name,
                    "card_type": card.card_type,
                    "effect": card.effect,
                    "rarity": card.rarity,
                })

    addons = []
    for pa in player.addons:
        addon = db.get(AddonCard, pa.addon_id)
        if addon:
            addons.append({
                "player_addon_id": pa.id,
                "addon_id": addon.id,
                "name": addon.name,
                "addon_type": addon.addon_type,
                "effect": addon.effect,
                "is_tapped": pa.is_tapped,
            })

    return {
        "type": ServerEvent.HAND_STATE,
        "hand": hand,
        "addons": addons,
    }


async def _send_hand_state(game_code: str, player: GamePlayer, db: Session):
    """Send private hand state to a single player."""
    await manager.send_to_player(game_code, player.user_id, _build_hand_state(player, db))


def _apply_elo(game: GameSession, winner_player_id: int, db: Session) -> None:
    """Update ELO ratings and game stats for all players at game end."""
    from app.game.engine_addons import has_addon as _has_addon
    players = game.players
    users = [db.get(User, gp.user_id) for gp in players]
    ratings = [u.elo_rating for u in users if u]

    winner_index = next(
        (i for i, gp in enumerate(players) if gp.id == winner_player_id), 0
    )
    new_ratings = engine.update_elo(ratings, winner_index)

    for i, (gp, user) in enumerate(zip(players, users)):
        if user is None:
            continue
        final_rating = new_ratings[i]
        # Addon 76 (Rollup Summary): +1 ELO per boss defeated (ranking bonus, not victory)
        if _has_addon(gp, 76):
            final_rating += (gp.combat_state or {}).get("rollup_boss_defeats", 0)
        user.elo_rating = max(100, final_rating)
        user.games_played += 1
        if gp.id == winner_player_id:
            user.games_won += 1
