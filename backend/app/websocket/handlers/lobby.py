"""
Lobby phase handlers: join, character selection, game start.
"""
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _error, _broadcast_state, _build_game_state, _send_hand_state,
)
from app.models.game import GameSession, GamePlayer, GameStatus, TurnPhase
from app.models.user import User
from app.game import engine


async def _handle_join(game: GameSession, user_id: int, data: dict, db: Session):
    existing = _get_player(game, user_id)

    if game.status == GameStatus.finished:
        await _error(game.code, user_id, "Game already finished")
        return

    if game.status == GameStatus.in_progress:
        if existing:
            # Reconnect during active game — send public state to all + private hand to this player
            await _broadcast_state(game, db)
            await _send_hand_state(game.code, existing, db)
        else:
            await _error(game.code, user_id, "Game already started")
        return

    # status == waiting
    if existing:
        # Rejoin lobby — send current state
        await manager.send_to_player(game.code, user_id, _build_game_state(game, db))
        return

    if len(game.players) >= game.max_players:
        await _error(game.code, user_id, "Game is full")
        return

    player = GamePlayer(
        game_id=game.id,
        user_id=user_id,
        seniority="Junior",   # placeholder until character select
        role="",
        hp=1,
        max_hp=1,
        licenze=engine.STARTING_LICENZE,
    )
    db.add(player)
    db.commit()
    db.refresh(game)

    user = db.get(User, user_id)
    await manager.broadcast(game.code, {
        "type": ServerEvent.PLAYER_JOINED,
        "user_id": user_id,
        "nickname": user.nickname if user else "?",
    })
    await _broadcast_state(game, db)


async def _handle_select_character(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.waiting:
        await _error(game.code, user_id, "Cannot change character after game started")
        return

    player = _get_player(game, user_id)
    if not player:
        await _error(game.code, user_id, "Not in this game")
        return

    seniority = data.get("seniority")
    role = data.get("role", "")
    if seniority not in ("Junior", "Experienced", "Senior", "Evangelist"):
        await _error(game.code, user_id, "Invalid seniority")
        return

    from app.models.game import Seniority
    player.seniority = Seniority(seniority)
    player.role = role
    player.max_hp = engine.calculate_max_hp(Seniority(seniority))
    player.hp = player.max_hp
    db.commit()
    await _broadcast_state(game, db)


async def _handle_start_game(game: GameSession, user_id: int, db: Session):
    if game.status != GameStatus.waiting:
        await _error(game.code, user_id, "Game already started")
        return

    players = game.players
    if len(players) < 2:
        await _error(game.code, user_id, "Need at least 2 players")
        return

    # Build shared decks
    from app.models.card import ActionCard, BossCard, AddonCard
    action_cards = db.query(ActionCard).all()
    boss_cards = db.query(BossCard).all()
    addon_cards = db.query(AddonCard).all()

    by_rarity: dict[str, list[int]] = {}
    for ac in action_cards:
        by_rarity.setdefault(ac.rarity, []).append(ac.id)

    full_action_deck = engine.build_action_deck(by_rarity)
    game.action_deck = full_action_deck
    game.action_discard = []

    full_boss_deck = engine.shuffle_deck([bc.id for bc in boss_cards])
    game.boss_deck = full_boss_deck
    game.boss_graveyard = []
    # Reveal first 2 market cards from boss deck
    game.boss_market_1 = game.boss_deck.pop(0) if game.boss_deck else None
    game.boss_market_2 = game.boss_deck.pop(0) if game.boss_deck else None

    full_addon_deck = engine.shuffle_deck([ac.id for ac in addon_cards])
    game.addon_deck = full_addon_deck
    game.addon_graveyard = []
    # Reveal first 2 market cards from addon deck
    game.addon_market_1 = game.addon_deck.pop(0) if game.addon_deck else None
    game.addon_market_2 = game.addon_deck.pop(0) if game.addon_deck else None
    game.turn_order = [p.id for p in players]
    game.status = GameStatus.in_progress
    game.current_turn_index = 0
    game.turn_number = 1
    game.current_phase = TurnPhase.draw

    # Deal starting hands from single action deck
    from app.models.game import PlayerHandCard
    for player in players:
        for _ in range(engine.STARTING_HAND_SIZE):
            if game.action_deck:
                db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck.pop(0)))

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {"type": ServerEvent.GAME_STARTED})
    await _broadcast_state(game, db)
    # Send each player their private starting hand
    for player in players:
        db.refresh(player)
        await _send_hand_state(game.code, player, db)
