"""
WebSocket message router — connects client actions to game engine logic and DB.
"""
import json
from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ClientAction, ServerEvent
from app.models.game import GameSession, GamePlayer, GameStatus, TurnPhase
from app.models.card import ActionCard, BossCard, AddonCard
from app.models.user import User
from app.game import engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_game_state(game: GameSession, db: Session) -> dict:
    current_player_id = None
    if game.turn_order and game.current_turn_index < len(game.turn_order):
        current_player_id = game.turn_order[game.current_turn_index]

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
            "is_in_combat": gp.is_in_combat,
            "bosses_defeated": gp.bosses_defeated,
        })

    return {
        "type": ServerEvent.GAME_STATE,
        "game": {
            "id": game.id,
            "code": game.code,
            "status": game.status,
            "current_phase": game.current_phase,
            "turn_number": game.turn_number,
            "current_player_id": current_player_id,
            "action_deck_count": len(game.action_deck),
            "boss_deck_count": len(game.boss_deck),
            "addon_deck_count": len(game.addon_deck),
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


def _apply_elo(game: GameSession, winner_player_id: int, db: Session) -> None:
    """Update ELO ratings and game stats for all players at game end."""
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
        user.elo_rating = new_ratings[i]
        user.games_played += 1
        if gp.id == winner_player_id:
            user.games_won += 1


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

async def handle_message(
    game_code: str,
    user_id: int,
    raw: str,
    db: Session,
):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        await _error(game_code, user_id, "Invalid JSON")
        return

    action = data.get("action")
    game = db.query(GameSession).filter(GameSession.code == game_code).first()
    if not game:
        await _error(game_code, user_id, "Game not found")
        return

    if action == ClientAction.JOIN_GAME:
        await _handle_join(game, user_id, data, db)
    elif action == ClientAction.SELECT_CHARACTER:
        await _handle_select_character(game, user_id, data, db)
    elif action == ClientAction.START_GAME:
        await _handle_start_game(game, user_id, db)
    elif action == ClientAction.DRAW_CARD:
        await _handle_draw_card(game, user_id, db)
    elif action == ClientAction.PLAY_CARD:
        await _handle_play_card(game, user_id, data, db)
    elif action == ClientAction.BUY_ADDON:
        await _handle_buy_addon(game, user_id, data, db)
    elif action == ClientAction.USE_ADDON:
        await _handle_use_addon(game, user_id, data, db)
    elif action == ClientAction.START_COMBAT:
        await _handle_start_combat(game, user_id, db)
    elif action == ClientAction.ROLL_DICE:
        await _handle_roll_dice(game, user_id, db)
    elif action == ClientAction.END_TURN:
        await _handle_end_turn(game, user_id, db)
    elif action == ClientAction.RETREAT_COMBAT:
        await _handle_retreat(game, user_id, db)
    else:
        await _error(game_code, user_id, f"Unknown action: {action}")


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

async def _handle_join(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.waiting:
        await _error(game.code, user_id, "Game already started")
        return

    existing = _get_player(game, user_id)
    if existing:
        # Rejoin — send current state
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
    from app.models.card import ActionCard, BossCard, AddonCard, Rarity
    action_cards = db.query(ActionCard).all()
    boss_cards = db.query(BossCard).all()
    addon_cards = db.query(AddonCard).all()

    by_rarity: dict[str, list[int]] = {}
    for ac in action_cards:
        by_rarity.setdefault(ac.rarity, []).append(ac.id)

    game.action_deck = engine.build_action_deck(by_rarity)
    game.boss_deck = engine.shuffle_deck([bc.id for bc in boss_cards])
    game.addon_deck = engine.shuffle_deck([ac.id for ac in addon_cards])
    game.turn_order = [p.id for p in players]
    game.status = GameStatus.in_progress
    game.current_turn_index = 0
    game.turn_number = 1
    game.current_phase = TurnPhase.draw

    # Deal starting hands
    for player in players:
        drawn, game.action_deck, game.action_discard = engine.draw_cards(
            game.action_deck, game.action_discard, engine.STARTING_HAND_SIZE
        )
        from app.models.game import PlayerHandCard
        for card_id in drawn:
            db.add(PlayerHandCard(player_id=player.id, action_card_id=card_id))

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {"type": ServerEvent.GAME_STARTED})
    await _broadcast_state(game, db)


async def _handle_draw_card(game: GameSession, user_id: int, db: Session):
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Game not in progress")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if game.current_phase != TurnPhase.draw:
        await _error(game.code, user_id, "Not in draw phase")
        return

    if len(player.hand) >= engine.MAX_HAND_SIZE:
        await _error(game.code, user_id, "Hand is full")
        return

    drawn, game.action_deck, game.action_discard = engine.draw_cards(
        game.action_deck, game.action_discard, 1
    )
    if not drawn:
        await _error(game.code, user_id, "No cards left")
        return

    from app.models.game import PlayerHandCard
    db.add(PlayerHandCard(player_id=player.id, action_card_id=drawn[0]))
    game.current_phase = TurnPhase.action
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {"type": ServerEvent.CARD_DRAWN, "player_id": player.id})
    await _broadcast_state(game, db)


async def _handle_play_card(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.action:
        await _error(game.code, user_id, "Cannot play card now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if player.cards_played_this_turn >= engine.MAX_CARDS_PER_TURN:
        await _error(game.code, user_id, "Card limit reached this turn")
        return

    hand_card_id = data.get("hand_card_id")
    from app.models.game import PlayerHandCard
    hc = db.get(PlayerHandCard, hand_card_id)
    if not hc or hc.player_id != player.id:
        await _error(game.code, user_id, "Card not in hand")
        return

    card = db.get(ActionCard, hc.action_card_id)
    game.action_discard.append(hc.action_card_id)
    db.delete(hc)
    player.cards_played_this_turn += 1
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.CARD_PLAYED,
        "player_id": player.id,
        "card": {"id": card.id, "name": card.name, "effect": card.effect} if card else {},
    })
    await _broadcast_state(game, db)


async def _handle_buy_addon(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.action:
        await _error(game.code, user_id, "Cannot buy addon now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if not game.addon_deck:
        await _error(game.code, user_id, "No addons available")
        return

    addon_id = game.addon_deck[0]
    addon = db.get(AddonCard, addon_id)
    if not addon:
        await _error(game.code, user_id, "Addon not found")
        return

    cost = addon.cost
    if player.licenze < cost:
        await _error(game.code, user_id, f"Need {cost} Licenze (have {player.licenze})")
        return

    player.licenze -= cost
    game.addon_deck = game.addon_deck[1:]
    from app.models.game import PlayerAddon
    db.add(PlayerAddon(player_id=player.id, addon_id=addon_id))
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_BOUGHT,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name},
    })
    await _broadcast_state(game, db)


async def _handle_start_combat(game: GameSession, user_id: int, db: Session):
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

    if not game.boss_deck:
        await _error(game.code, user_id, "No bosses left")
        return

    boss_id = game.boss_deck.pop(0)
    boss = db.get(BossCard, boss_id)
    if not boss:
        await _error(game.code, user_id, "Boss not found")
        return

    player.is_in_combat = True
    player.current_boss_id = boss_id
    player.current_boss_hp = boss.hp
    player.combat_round = 0
    game.current_phase = TurnPhase.combat
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.COMBAT_STARTED,
        "player_id": player.id,
        "boss": {"id": boss.id, "name": boss.name, "hp": boss.hp, "threshold": boss.dice_threshold},
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

    roll = engine.roll_d10()
    result = engine.resolve_combat_round(roll, boss.dice_threshold)
    player.combat_round += 1

    if result == "hit":
        player.current_boss_hp -= 1
    else:
        player.hp -= 1

    boss_defeated = player.current_boss_hp is not None and player.current_boss_hp <= 0
    player_died = player.hp <= 0

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
        player.licenze += boss.reward_licenze
        if boss.has_certification:
            player.certificazioni += 1
        game.boss_discard.append(player.current_boss_id)
        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
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

        # Remove lost card from hand
        if "card" in penalty["lost"]:
            lost_card_id = penalty["lost"]["card"]
            hc_to_remove = next((hc for hc in player.hand if hc.action_card_id == lost_card_id), None)
            if hc_to_remove:
                game.action_discard.append(lost_card_id)
                db.delete(hc_to_remove)

        # Remove lost addon
        if "addon" in penalty["lost"]:
            lost_addon_id = penalty["lost"]["addon"]
            pa_to_remove = next((pa for pa in player.addons if pa.addon_id == lost_addon_id), None)
            if pa_to_remove:
                game.addon_discard.append(lost_addon_id)
                db.delete(pa_to_remove)

        player.licenze = penalty["licenze"]
        player.hp = player.max_hp  # respawn with full HP
        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        game.boss_deck.insert(0, boss.id)  # boss goes back to top
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
        await _broadcast_state(game, db)
        return

    db.commit()
    db.refresh(game)
    await manager.broadcast(game.code, event)
    await _broadcast_state(game, db)


async def _handle_end_turn(game: GameSession, user_id: int, db: Session):
    if game.status != GameStatus.in_progress:
        await _error(game.code, user_id, "Game not in progress")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    if game.current_phase not in (TurnPhase.action, TurnPhase.draw):
        await _error(game.code, user_id, "Cannot end turn now (in combat?)")
        return

    # Untap all addons
    for pa in player.addons:
        pa.is_tapped = False

    player.cards_played_this_turn = 0

    # Advance turn
    game.current_turn_index = (game.current_turn_index + 1) % len(game.turn_order)
    if game.current_turn_index == 0:
        game.turn_number += 1
    game.current_phase = TurnPhase.draw

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.TURN_ENDED,
        "player_id": player.id,
        "next_player_id": game.turn_order[game.current_turn_index],
    })
    await _broadcast_state(game, db)


async def _handle_use_addon(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.action:
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

    if pa.is_tapped:
        await _error(game.code, user_id, "Addon is tapped (already used this turn)")
        return

    pa.is_tapped = True
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_USED,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name, "effect": addon.effect},
    })
    await _broadcast_state(game, db)


async def _handle_retreat(game: GameSession, user_id: int, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.combat:
        await _error(game.code, user_id, "Not in combat")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player) or not player.is_in_combat:
        await _error(game.code, user_id, "Not your combat")
        return

    boss_id = player.current_boss_id
    game.boss_deck.insert(0, boss_id)  # boss goes back
    player.is_in_combat = False
    player.current_boss_id = None
    player.current_boss_hp = None
    game.current_phase = TurnPhase.action
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.COMBAT_ENDED,
        "player_id": player.id,
        "retreated": True,
    })
    await _broadcast_state(game, db)
