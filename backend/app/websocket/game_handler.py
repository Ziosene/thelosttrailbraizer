"""
WebSocket message router — connects client actions to game engine logic and DB.
"""
import json
import random
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
            "trophies": gp.trophies or [],  # list of BossCard.id — visible to all players
        })

    # Resolve visible market cards to full objects for the client
    def _boss_info(boss_id: int | None) -> dict | None:
        if boss_id is None:
            return None
        b = db.get(BossCard, boss_id)
        return {"id": b.id, "name": b.name, "hp": b.hp, "threshold": b.dice_threshold} if b else None

    def _addon_info(addon_id: int | None) -> dict | None:
        if addon_id is None:
            return None
        a = db.get(AddonCard, addon_id)
        return {"id": a.id, "name": a.name, "cost": a.cost, "effect": a.effect, "rarity": a.rarity} if a else None

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
            "boss_deck_1_count": len(game.boss_deck_1 or []),
            "boss_deck_2_count": len(game.boss_deck_2 or []),
            "boss_market_1": _boss_info(game.boss_market_1),
            "boss_market_2": _boss_info(game.boss_market_2),
            "addon_deck_1_count": len(game.addon_deck_1 or []),
            "addon_deck_2_count": len(game.addon_deck_2 or []),
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
    hand = []
    for hc in player.hand:
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
        await _handle_draw_card(game, user_id, data, db)
    elif action == ClientAction.PLAY_CARD:
        await _handle_play_card(game, user_id, data, db)
    elif action == ClientAction.BUY_ADDON:
        await _handle_buy_addon(game, user_id, data, db)
    elif action == ClientAction.USE_ADDON:
        await _handle_use_addon(game, user_id, data, db)
    elif action == ClientAction.START_COMBAT:
        await _handle_start_combat(game, user_id, data, db)
    elif action == ClientAction.ROLL_DICE:
        await _handle_roll_dice(game, user_id, db)
    elif action == ClientAction.END_TURN:
        await _handle_end_turn(game, user_id, db)
    elif action == ClientAction.RETREAT_COMBAT:
        await _handle_retreat(game, user_id, db)
    elif action == ClientAction.DECLARE_CARD:
        await _handle_declare_card(game, user_id, data, db)
    elif action == ClientAction.DECLARE_CARD_TYPE:
        await _handle_declare_card_type(game, user_id, data, db)
    else:
        await _error(game_code, user_id, f"Unknown action: {action}")


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------

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
    from app.models.card import ActionCard, BossCard, AddonCard, Rarity
    action_cards = db.query(ActionCard).all()
    boss_cards = db.query(BossCard).all()
    addon_cards = db.query(AddonCard).all()

    by_rarity: dict[str, list[int]] = {}
    for ac in action_cards:
        by_rarity.setdefault(ac.rarity, []).append(ac.id)

    full_action_deck = engine.build_action_deck(by_rarity)
    game.action_deck_1, game.action_deck_2 = engine.split_deck(full_action_deck)
    game.action_discard = []

    full_boss_deck = engine.shuffle_deck([bc.id for bc in boss_cards])
    game.boss_deck_1, game.boss_deck_2 = engine.split_deck(full_boss_deck)
    game.boss_graveyard = []
    # Reveal first market card from each boss deck
    game.boss_market_1 = game.boss_deck_1.pop(0) if game.boss_deck_1 else None
    game.boss_market_2 = game.boss_deck_2.pop(0) if game.boss_deck_2 else None

    full_addon_deck = engine.shuffle_deck([ac.id for ac in addon_cards])
    game.addon_deck_1, game.addon_deck_2 = engine.split_deck(full_addon_deck)
    game.addon_graveyard = []
    # Reveal first market card from each addon deck
    game.addon_market_1 = game.addon_deck_1.pop(0) if game.addon_deck_1 else None
    game.addon_market_2 = game.addon_deck_2.pop(0) if game.addon_deck_2 else None
    game.turn_order = [p.id for p in players]
    game.status = GameStatus.in_progress
    game.current_turn_index = 0
    game.turn_number = 1
    game.current_phase = TurnPhase.draw

    # Deal starting hands (alternate draws between deck_1 and deck_2 for balance)
    from app.models.game import PlayerHandCard
    for i, player in enumerate(players):
        for j in range(engine.STARTING_HAND_SIZE):
            if (i + j) % 2 == 0:
                drawn = [game.action_deck_1.pop(0)] if game.action_deck_1 else []
            else:
                drawn = [game.action_deck_2.pop(0)] if game.action_deck_2 else []
            for card_id in drawn:
                db.add(PlayerHandCard(player_id=player.id, action_card_id=card_id))

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {"type": ServerEvent.GAME_STARTED})
    await _broadcast_state(game, db)
    # Send each player their private starting hand
    for player in players:
        db.refresh(player)
        await _send_hand_state(game.code, player, db)


async def _handle_draw_card(game: GameSession, user_id: int, data: dict, db: Session):
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

    deck_num = data.get("deck", 1)  # client sends 1 or 2
    if deck_num not in (1, 2):
        await _error(game.code, user_id, "Invalid deck number (must be 1 or 2)")
        return

    # Try to draw from the requested deck; if empty, reshuffle shared discard into both decks
    if deck_num == 1:
        if not game.action_deck_1 and game.action_discard:
            new_deck = engine.shuffle_deck(game.action_discard)
            game.action_deck_1, game.action_deck_2 = engine.split_deck(new_deck)
            game.action_discard = []
        drawn = [game.action_deck_1.pop(0)] if game.action_deck_1 else []
    else:
        if not game.action_deck_2 and game.action_discard:
            new_deck = engine.shuffle_deck(game.action_discard)
            game.action_deck_1, game.action_deck_2 = engine.split_deck(new_deck)
            game.action_discard = []
        drawn = [game.action_deck_2.pop(0)] if game.action_deck_2 else []
    if not drawn:
        await _error(game.code, user_id, f"No cards left in deck {deck_num}")
        return

    from app.models.game import PlayerHandCard

    # Boss 81 (Trailhead Jinx): drawn cards may be jinxed — d10 ≤ 3 → card discarded, no effect
    jinxed = False
    if player.is_in_combat and player.current_boss_id and engine.boss_jinx_on_draw(player.current_boss_id):
        if engine.roll_d10() <= 3:
            jinxed = True
            game.action_discard = (game.action_discard or []) + [drawn[0]]

    if not jinxed:
        db.add(PlayerHandCard(player_id=player.id, action_card_id=drawn[0]))

    # Boss 92 (Einstein Copilot Seraph): every card drawn during combat costs 1 HP
    if player.is_in_combat and player.current_boss_id:
        hp_cost = engine.boss_draw_costs_hp(player.current_boss_id)
        if hp_cost > 0:
            player.hp = max(0, player.hp - hp_cost)

    # TODO: trigger_passive_addons(event="on_draw", player, game, db)

    game.current_phase = TurnPhase.action
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {"type": ServerEvent.CARD_DRAWN, "player_id": player.id})
    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)


async def _handle_play_card(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.action:
        await _error(game.code, user_id, "Cannot play card now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
        await _error(game.code, user_id, "Not your turn")
        return

    max_cards = (
        engine.boss_max_cards_per_turn(player.current_boss_id, engine.MAX_CARDS_PER_TURN)
        if player.is_in_combat and player.current_boss_id
        else engine.MAX_CARDS_PER_TURN
    )
    if player.cards_played_this_turn >= max_cards:
        await _error(game.code, user_id, "Card limit reached this turn")
        return

    # TODO: validare il timing della carta prima di giocarla.
    # Ogni carta ha un campo "Quando" (es. "Durante combattimento", "Fuori dal combattimento",
    # "In qualsiasi momento", "Automatica"). Attualmente non viene verificato.
    # Va implementata una funzione can_play_card(card, game) che confronta
    # card.timing con game.current_phase e player.is_in_combat.

    if player.is_in_combat and player.current_boss_id:
        current_round_pc = (player.combat_round or 0) + 1

        # Boss  9 (Code Coverage Ghoul): offensive cards blocked
        # TODO: enforce once card.card_type is used in apply_action_card_effect
        # Boss 17 (Validation Rule Hell): dice-modifier cards have no effect
        # TODO: pass flag into apply_action_card_effect
        # Boss  8 (MuleSoft Kraken): interference doubled in card effect logic — TODO

        # Boss 38 (Einstein Bot Imposter): on even rounds, first card played is cancelled
        if engine.boss_cancels_next_card(player.current_boss_id, current_round_pc):
            if player.cards_played_this_turn == 0:
                # Card consumed but has no effect this round
                hand_card_id_early = data.get("hand_card_id")
                from app.models.game import PlayerHandCard as _PHC
                hc_early = db.get(_PHC, hand_card_id_early)
                if hc_early and hc_early.player_id == player.id:
                    card_early = db.get(ActionCard, hc_early.action_card_id)
                    game.action_discard.append(hc_early.action_card_id)
                    db.delete(hc_early)
                    player.cards_played_this_turn += 1
                    db.commit()
                    db.refresh(game)
                    await manager.broadcast(game.code, {
                        "type": ServerEvent.CARD_PLAYED,
                        "player_id": player.id,
                        "card": {"id": card_early.id, "name": card_early.name} if card_early else {},
                        "cancelled_by_boss": True,
                    })
                    await _broadcast_state(game, db)
                    await _send_hand_state(game.code, player, db)
                    return

        # Boss 41 (Quip Wisp): hand is visible to opponents — broadcast the card before it resolves
        if engine.boss_hand_visible_to_opponents(player.current_boss_id):
            hand_card_id_peek = data.get("hand_card_id")
            from app.models.game import PlayerHandCard as _PHC2
            hc_peek = db.get(_PHC2, hand_card_id_peek)
            if hc_peek:
                card_peek = db.get(ActionCard, hc_peek.action_card_id)
                opponents_ids = [p.user_id for p in game.players if p.id != player.id]
                for opp_uid in opponents_ids:
                    await manager.send_to_player(game.code, opp_uid, {
                        "type": "card_declared",
                        "player_id": player.id,
                        "card": {"id": card_peek.id, "name": card_peek.name} if card_peek else {},
                    })

        # Boss 65 (Einstein Vision Stalker): reveals card and cancels it if offensive
        if engine.boss_cancels_offensive_if_revealed(player.current_boss_id):
            hand_card_id_reveal = data.get("hand_card_id")
            from app.models.game import PlayerHandCard as _PHC3
            hc_reveal = db.get(_PHC3, hand_card_id_reveal)
            if hc_reveal:
                card_reveal = db.get(ActionCard, hc_reveal.action_card_id)
                if card_reveal and card_reveal.card_type == "Offensiva":
                    game.action_discard.append(hc_reveal.action_card_id)
                    db.delete(hc_reveal)
                    player.cards_played_this_turn += 1
                    db.commit()
                    db.refresh(game)
                    await manager.broadcast(game.code, {
                        "type": ServerEvent.CARD_PLAYED,
                        "player_id": player.id,
                        "card": {"id": card_reveal.id, "name": card_reveal.name} if card_reveal else {},
                        "cancelled_by_boss": True,
                    })
                    await _broadcast_state(game, db)
                    await _send_hand_state(game.code, player, db)
                    return

    hand_card_id = data.get("hand_card_id")
    from app.models.game import PlayerHandCard
    hc = db.get(PlayerHandCard, hand_card_id)
    if not hc or hc.player_id != player.id:
        await _error(game.code, user_id, "Card not in hand")
        return

    card = db.get(ActionCard, hc.action_card_id)

    # Boss 82 (Customer 360 Gorgon): petrified cards cannot be played this fight
    if player.is_in_combat and player.combat_state:
        petrified = player.combat_state.get("petrified_card_ids", [])
        if card and card.id in petrified:
            await _error(game.code, user_id, "This card is petrified and cannot be played")
            return

    # Boss 86 (Record Type Ravager): only declared card type may be played
    if player.is_in_combat and player.combat_state:
        allowed_type = player.combat_state.get("allowed_card_type")
        if allowed_type and card and card.card_type != allowed_type:
            await _error(game.code, user_id, f"Boss restricts you to {allowed_type} cards only")
            return

    # Boss 56 (Change Data Capture Lurker): banned cards cannot be played anywhere in this game
    if card and card.id in (game.banned_card_ids or []):
        await _error(game.code, user_id, "This card has been permanently banned from the game")
        return
    game.action_discard.append(hc.action_card_id)
    db.delete(hc)
    player.cards_played_this_turn += 1

    if player.is_in_combat and player.current_boss_id and card:
        current_round_post = (player.combat_round or 0) + 1

        # Boss 69 (Approval Process Bureaucrat): every card must pass an approval roll
        # d10 ≤ 4 → card consumed but has no effect
        card_approved = True
        if engine.boss_requires_approval_roll(player.current_boss_id):
            approval_roll = engine.roll_d10()
            if approval_roll <= 4:
                card_approved = False

        # Boss 56 (Change Data Capture Lurker): played cards are permanently banned from the game
        if engine.boss_permanently_bans_used_cards(player.current_boss_id):
            game.banned_card_ids = (game.banned_card_ids or []) + [card.id]

        # Boss 59 (Trailblazer Community Mob): boss heals when opponent plays an interference card
        # Interference cards played by NON-combatant players against this player also heal the boss
        if card.card_type == "Interferenza":
            boss_heal_interference = engine.boss_heals_on_interference(player.current_boss_id)
            if boss_heal_interference > 0:
                boss_card_hi = db.get(BossCard, player.current_boss_id)
                if boss_card_hi:
                    player.current_boss_hp = min(boss_card_hi.hp, (player.current_boss_hp or 0) + boss_heal_interference)

        # Boss 72 (DevOps Center Saboteur): boss heals when combatant plays a defensive card
        if card.card_type == "Difensiva":
            boss_heal_def = engine.boss_heals_on_defensive_card(player.current_boss_id)
            if boss_heal_def > 0:
                boss_card_hd = db.get(BossCard, player.current_boss_id)
                if boss_card_hd:
                    player.current_boss_hp = min(boss_card_hd.hp, (player.current_boss_hp or 0) + boss_heal_def)

        # Boss 96 (Compliance Cloud Sentinel): 1 extra HP per card played beyond the first this turn
        compliance_penalty = engine.boss_compliance_penalty_per_extra_card(player.current_boss_id)
        if compliance_penalty > 0 and player.cards_played_this_turn > 1:
            extra_compliance_dmg = compliance_penalty  # 1 HP per extra card (not cumulative — fires each play)
            player.hp = max(0, player.hp - extra_compliance_dmg)

    db.commit()
    db.refresh(game)

    # TODO: implementare gli effetti di tutte le 300 carte azione.
    # Attualmente la carta viene rimossa dalla mano e messa negli scarti,
    # ma il suo effetto NON viene applicato.
    # Ogni carta va gestita per nome (card.name) o numero (card.number) in
    # una funzione dedicata tipo apply_action_card_effect(card, player, game, db).
    # Categorie da coprire:
    #   - Economiche: guadagna/trasferisci licenze (condizionali su stato gioco)
    #   - Offensive: infliggi danno al boss (immediato o persistente)
    #   - Difensive: recupera HP, blocca danno, crea scudi
    #   - Manipolazione dado: modifica soglia, ritira dado, forza valore
    #   - Utilità: pesca carte, riordina mazzi, recupera scarti
    #   - Interferenza: forza azioni su avversari, ruba carte/licenze
    #   - Leggendarie: effetti compositi multi-categoria
    # Furto trofeo: victim.trophies.remove(boss_id) → thief.trophies.append(boss_id)
    #   aggiorna victim.certificazioni -= 1 e thief.certificazioni += 1
    # Distruzione trofeo: victim.trophies.remove(boss_id) → game.boss_graveyard.append(boss_id)
    #   aggiorna victim.certificazioni -= 1
    # Vedere cards/action_cards.md per l'effetto completo di ogni carta.

    await manager.broadcast(game.code, {
        "type": ServerEvent.CARD_PLAYED,
        "player_id": player.id,
        "card": {"id": card.id, "name": card.name, "effect": card.effect} if card else {},
    })
    await _broadcast_state(game, db)
    await _send_hand_state(game.code, player, db)


async def _handle_buy_addon(game: GameSession, user_id: int, data: dict, db: Session):
    if game.status != GameStatus.in_progress or game.current_phase != TurnPhase.action:
        await _error(game.code, user_id, "Cannot buy addon now")
        return

    player = _get_player(game, user_id)
    if not player or not _is_player_turn(game, player):
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

    # Boss 60 (Connected App Infiltrator): addon purchases are blocked during this combat
    if player.is_in_combat and player.current_boss_id:
        if engine.boss_blocks_addon_purchase(player.current_boss_id):
            await _error(game.code, user_id, "Addon purchases are blocked by the boss")
            return

    cost = addon.cost + (player.pending_addon_cost_penalty or 0)
    if player.licenze < cost:
        await _error(game.code, user_id, f"Need {cost} Licenze (have {player.licenze})")
        return

    player.licenze -= cost
    player.pending_addon_cost_penalty = 0  # penalty consumed on first purchase (boss 26)

    # Bought addons are tracked as owned by player; market slot gets refilled
    if source == "market_1":
        game.addon_market_1 = game.addon_deck_1.pop(0) if game.addon_deck_1 else None
    elif source == "market_2":
        game.addon_market_2 = game.addon_deck_2.pop(0) if game.addon_deck_2 else None
    # deck_1 / deck_2: card already popped above, nothing else to do

    from app.models.game import PlayerAddon
    db.add(PlayerAddon(player_id=player.id, addon_id=addon_id))

    # TODO: triggherare gli addon passivi con trigger "quando acquisti un addon" (sia il nuovo che quelli già posseduti).
    # Alcuni addon esistenti danno bonus al momento dell'acquisto di un nuovo addon.
    # Va chiamata trigger_passive_addons(event="on_addon_bought", player, game, new_addon=addon, db).
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.ADDON_BOUGHT,
        "player_id": player.id,
        "addon": {"id": addon.id, "name": addon.name},
    })
    await _broadcast_state(game, db)


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

    player.is_in_combat = True
    player.current_boss_id = boss_id
    player.current_boss_source = source
    player.current_boss_hp = boss.hp
    player.combat_round = 0
    player.combat_state = {}  # reset per-combat state for every new fight
    game.current_phase = TurnPhase.combat

    # Boss 68 (Schema Builder Monstrosity): boss HP increases by 1 for each addon the combatant owns
    if engine.apply_boss_ability(boss_id, "on_combat_start")["bonus_hp_per_player_addon"]:
        player.current_boss_hp = boss.hp + len(player.addons)

    start_effect = engine.apply_boss_ability(boss_id, "on_combat_start")

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

    # Boss 91 (List View Usurper): steal 1 random untapped addon; return it on defeat
    # Note: applying the stolen addon's effect against the player requires apply_addon_effect —
    # deferred until that system is implemented. Theft and return are fully tracked.
    if start_effect["steal_and_use_addon"]:
        untapped_91 = [pa for pa in player.addons if not pa.is_tapped]
        if untapped_91:
            pa_steal = random.choice(untapped_91)
            cs = dict(player.combat_state or {})
            cs["stolen_addon_id"] = pa_steal.addon_id
            player.combat_state = cs
            db.delete(pa_steal)
            await manager.broadcast(game.code, {
                "type": "addon_stolen_by_boss",
                "player_id": player.id,
                "boss_id": boss_id,
            })

    # Boss 94 (Loyalty Cloud Warden): initialise loyalty points shield (blocks first 3 hits)
    if engine.boss_loyalty_shield(boss_id) > 0:
        cs = dict(player.combat_state or {})
        cs["loyalty_points"] = engine.boss_loyalty_shield(boss_id)
        player.combat_state = cs

    # Boss 86 (Record Type Ravager): prompt combatant to declare card type before fighting
    if start_effect["force_card_type_declaration"]:
        await manager.send_to_player(game.code, player.user_id, {
            "type": "card_type_declaration_required",
            "player_id": player.id,
            "options": ["Offensiva", "Difensiva"],
        })

    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.COMBAT_STARTED,
        "player_id": player.id,
        "boss": {"id": boss.id, "name": boss.name, "hp": boss.hp, "threshold": boss.dice_threshold},
        "boss_effect": {k: v for k, v in start_effect.items() if v},
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

    # combat_round is still 0-indexed here; current roll = round N+1
    current_round = (player.combat_round or 0) + 1

    # ── Boss 55 (mimic) / Boss 74 (shape shifter): copy last defeated boss ───
    copy_boss_id: int | None = None
    if game.last_defeated_boss_id:
        if engine.boss_is_mimic(boss.id):
            copy_boss_id = game.last_defeated_boss_id
        elif engine.boss_is_shape_shifter(boss.id) and current_round % 2 == 0:
            copy_boss_id = game.last_defeated_boss_id

    # ── on_round_start effects (before rolling) ──────────────────────────
    round_start = engine.apply_boss_ability(
        boss.id, "on_round_start",
        combat_round=current_round,
        cards_played=player.cards_played_this_turn,
    )

    # Boss 18 (Tech Debt Lich): drain 1 Licenza every round
    if round_start["licenza_drain"] > 0:
        player.licenze = max(0, player.licenze - round_start["licenza_drain"])

    # Boss 13 (Flow Builder Gone Rogue): discard 1 card or take 1 HP
    if round_start["force_discard_or_damage"] > 0:
        hand_cards = list(player.hand)
        if hand_cards:
            hc = random.choice(hand_cards)
            game.action_discard = (game.action_discard or []) + [hc.action_card_id]
            db.delete(hc)
        else:
            player.hp = max(0, player.hp - round_start["force_discard_or_damage"])

    # Boss 42 (Revenue Cloud Devourer): drain 1 licenza; if 0 licenze → drain 1 HP
    if round_start["licenza_or_hp_drain"] > 0:
        n = round_start["licenza_or_hp_drain"]
        if player.licenze >= n:
            player.licenze -= n
        else:
            player.hp = max(0, player.hp - n)

    # Boss 46 (Process Builder Abomination): involuntarily discard 1 extra card every round
    if round_start["force_extra_card_discard"]:
        hand_cards_fe = list(player.hand)
        if hand_cards_fe:
            hc_fe = random.choice(hand_cards_fe)
            game.action_discard = (game.action_discard or []) + [hc_fe.action_card_id]
            db.delete(hc_fe)

    # Boss 35 (Platform Event Gremlin): chaos roll — extra d10; on 1 → random penalty
    if round_start["bonus_chaos_roll"]:
        chaos_roll = engine.roll_d10()
        if chaos_roll == 1:
            chaos_penalty = random.choice(["card", "hp", "licenza_opponent"])
            if chaos_penalty == "card":
                hand_cards_ch = list(player.hand)
                if hand_cards_ch:
                    hc_ch = random.choice(hand_cards_ch)
                    game.action_discard = (game.action_discard or []) + [hc_ch.action_card_id]
                    db.delete(hc_ch)
            elif chaos_penalty == "hp":
                player.hp = max(0, player.hp - 1)
            else:
                opponents_ch = [p for p in game.players if p.id != player.id]
                if opponents_ch:
                    random.choice(opponents_ch).licenze += 2

    # Boss 53 (Einstein Discovery Oracle): boss predicts hit/miss; correct → double round effect
    prediction = None
    if round_start["makes_prediction"]:
        prediction = random.choice(["hit", "miss"])
        await manager.broadcast(game.code, {
            "type": "boss_prediction",
            "player_id": player.id,
            "prediction": prediction,
        })

    # Boss 93 (Subscription Management Tormentor): pay 1 licenza or take 2 HP
    if round_start["subscription_drain"] > 0:
        n_sub = round_start["subscription_drain"]
        if player.licenze >= n_sub:
            player.licenze -= n_sub
        else:
            player.hp = max(0, player.hp - 2 * n_sub)

    # Boss 100 (Omega): apply last legendary boss's on_round_start effects in parallel
    if engine.boss_is_omega(boss.id) and game.last_defeated_legendary_boss_id:
        omega_rs = engine.apply_boss_ability(
            game.last_defeated_legendary_boss_id, "on_round_start",
            combat_round=current_round,
            cards_played=player.cards_played_this_turn,
        )
        if omega_rs["licenza_drain"] > 0:
            player.licenze = max(0, player.licenze - omega_rs["licenza_drain"])
        if omega_rs["licenza_or_hp_drain"] > 0:
            n = omega_rs["licenza_or_hp_drain"]
            if player.licenze >= n:
                player.licenze -= n
            else:
                player.hp = max(0, player.hp - n)
        if omega_rs["subscription_drain"] > 0:
            ns = omega_rs["subscription_drain"]
            if player.licenze >= ns:
                player.licenze -= ns
            else:
                player.hp = max(0, player.hp - 2 * ns)

    # Boss 55 / Boss 74: apply shadow copy's on_round_start effects
    if copy_boss_id:
        copy_rs = engine.apply_boss_ability(
            copy_boss_id, "on_round_start",
            combat_round=current_round,
            cards_played=player.cards_played_this_turn,
        )
        if copy_rs["licenza_drain"] > 0:
            player.licenze = max(0, player.licenze - copy_rs["licenza_drain"])
        if copy_rs["licenza_or_hp_drain"] > 0:
            n = copy_rs["licenza_or_hp_drain"]
            if player.licenze >= n:
                player.licenze -= n
            else:
                player.hp = max(0, player.hp - n)
        if copy_rs["force_discard_or_damage"] > 0:
            hcl = list(player.hand)
            if hcl:
                hc_cp = random.choice(hcl)
                game.action_discard = (game.action_discard or []) + [hc_cp.action_card_id]
                db.delete(hc_cp)
            else:
                player.hp = max(0, player.hp - copy_rs["force_discard_or_damage"])
        if copy_rs["subscription_drain"] > 0:
            ns = copy_rs["subscription_drain"]
            if player.licenze >= ns:
                player.licenze -= ns
            else:
                player.hp = max(0, player.hp - 2 * ns)

    # Boss 45 (Agentforce Rebellion): hijack 1 random untapped addon — tap it (boss "uses" it)
    # Full inverted-effect application deferred until apply_addon_effect is implemented.
    threshold_bonus = 0
    if round_start["hijack_addon"]:
        untapped_45 = [pa for pa in player.addons if not pa.is_tapped]
        if untapped_45:
            pa_hijack = random.choice(untapped_45)
            pa_hijack.is_tapped = True
            hijacked_addon = db.get(AddonCard, pa_hijack.addon_id)
            await manager.broadcast(game.code, {
                "type": "addon_hijacked_by_boss",
                "player_id": player.id,
                "addon": {"id": hijacked_addon.id, "name": hijacked_addon.name} if hijacked_addon else {},
            })

    # Boss 63 (Loyalty Management Trickster): auto-accept deal — +1 Licenza, threshold +1 this roll
    if round_start["deal_offer"]:
        player.licenze += 1
        threshold_bonus += 1
        await manager.broadcast(game.code, {
            "type": "boss_deal_auto_accepted",
            "player_id": player.id,
            "gained_licenze": 1,
            "threshold_penalty": 1,
        })

    # Boss 83 (Account Engagement Siren): auto-reject siren deal — no HP trade this round
    if round_start["siren_deal"]:
        await manager.broadcast(game.code, {
            "type": "boss_siren_deal_rejected",
            "player_id": player.id,
        })

    # Boss 33 (Experience Cloud Illusion): player must have declared a card before rolling
    if engine.boss_card_declared_before_roll(boss.id):
        if not (player.combat_state or {}).get("declared_card_id"):
            await _error(game.code, user_id, "You must declare a card (declare_card) before rolling against this boss")
            return

    # ── Boss expires check ────────────────────────────────────────────────
    # Boss 48 (Scratch Org Mirage) / Boss 90 (Quick Action Marauder): auto-expire
    expire_rounds = engine.boss_expires_after_rounds(boss.id)
    if expire_rounds is not None and current_round > expire_rounds:
        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        player.current_boss_source = None
        game.current_phase = TurnPhase.action
        db.commit()
        db.refresh(game)
        await manager.broadcast(game.code, {
            "type": ServerEvent.COMBAT_ENDED,
            "player_id": player.id,
            "boss_escaped": True,
        })
        await _broadcast_state(game, db)
        return

    # ── Roll dice ─────────────────────────────────────────────────────────
    # Boss 1 (worst_of_2) / Boss 39 (second_of_2 — keep only the second roll)
    roll_mode = engine.boss_roll_mode(boss.id, current_round)
    roll = engine.roll_d10()
    if roll_mode == "worst_of_2":
        roll = min(roll, engine.roll_d10())
    elif roll_mode == "second_of_2":
        roll = engine.roll_d10()

    # Boss 67 (Developer Console Glitch): roll 1 or 2 → entire round is nullified
    round_nullified = engine.boss_nullifies_round_on_low_roll(boss.id) and roll <= 2

    # Boss 10, 12, 22, 37: dynamic threshold (now also passes combat_round for boss 22)
    # threshold_bonus from boss 63 deal (auto-accept raises threshold by 1 for this roll only)
    threshold = engine.boss_threshold(
        boss.id,
        boss.dice_threshold,
        player.current_boss_hp or 0,
        hand_count=len(player.hand),
        combat_round=current_round,
    ) + threshold_bonus

    result = engine.resolve_combat_round(roll, threshold)
    player.combat_round += 1

    player_took_damage = False

    if round_nullified:
        # No damage in either direction this round
        pass
    elif result == "hit":
        # Boss 78 (Known Issues Ghost) / Boss 89 (Object Manager Juggernaut): immune to dice
        if not engine.boss_immune_to_dice(boss.id, current_round):
            # Boss 94 (Loyalty Cloud Warden): absorb hit with loyalty point instead of HP
            if engine.boss_loyalty_shield(boss.id) > 0 and player.combat_state:
                lp = player.combat_state.get("loyalty_points", 0)
                if lp > 0:
                    cs = dict(player.combat_state)
                    cs["loyalty_points"] = lp - 1
                    player.combat_state = cs
                    # Hit absorbed by loyalty — no boss HP damage this roll
                else:
                    player.current_boss_hp -= 1
                    if prediction == "hit":
                        player.current_boss_hp -= 1
            else:
                player.current_boss_hp -= 1
                # Double boss damage if prediction was "hit" and correct (boss 53)
                if prediction == "hit":
                    player.current_boss_hp -= 1  # extra damage for correct prediction
    else:
        # Boss 95 (Identity & Access Heretic): player damage redirected to random opponent
        if engine.boss_redirects_damage_to_opponent(boss.id):
            opponents_redir = [p for p in game.players if p.id != player.id]
            if opponents_redir:
                target_redir = random.choice(opponents_redir)
                target_redir.hp = max(0, target_redir.hp - 1)
        else:
            player.hp -= 1
            player_took_damage = True

        miss_effect = engine.apply_boss_ability(
            boss.id, "after_miss",
            dice_result=roll,
            combat_round=current_round,
            current_hp=player.current_boss_hp or 0,
        )
        if miss_effect["extra_damage"] > 0:
            player.hp = max(0, player.hp - miss_effect["extra_damage"])
            # Double player damage if prediction was "miss" and correct (boss 53)
            if prediction == "miss":
                player.hp = max(0, player.hp - miss_effect["extra_damage"])
        if miss_effect["boss_heal"] > 0:
            player.current_boss_hp = min(
                boss.hp, (player.current_boss_hp or 0) + miss_effect["boss_heal"]
            )
        if miss_effect["aoe_all_players_hp_damage"] > 0:
            # Boss 40 (Net Zero Apocalypse): ALL players lose 1 HP on every miss
            for p_aoe in game.players:
                p_aoe.hp = max(0, p_aoe.hp - miss_effect["aoe_all_players_hp_damage"])

        # Boss 33 (Experience Cloud Illusion): consume declared card on miss
        if engine.boss_card_declared_before_roll(boss.id) and player.combat_state:
            declared_hc_id = player.combat_state.get("declared_hand_card_id")
            if declared_hc_id:
                from app.models.game import PlayerHandCard as _PHC33
                hc_33 = db.get(_PHC33, declared_hc_id)
                if hc_33 and hc_33.player_id == player.id:
                    game.action_discard = (game.action_discard or []) + [hc_33.action_card_id]
                    db.delete(hc_33)

    # Clear boss 33 declaration after every roll (hit or miss)
    if engine.boss_card_declared_before_roll(boss.id) and player.combat_state:
        cs = dict(player.combat_state)
        cs.pop("declared_card_id", None)
        cs.pop("declared_hand_card_id", None)
        player.combat_state = cs

    # Boss 55 / Boss 74: apply shadow copy's after_miss effects
    if copy_boss_id and result == "miss":
        copy_miss = engine.apply_boss_ability(
            copy_boss_id, "after_miss",
            dice_result=roll,
            combat_round=current_round,
            current_hp=player.current_boss_hp or 0,
        )
        if copy_miss["extra_damage"] > 0:
            player.hp = max(0, player.hp - copy_miss["extra_damage"])
        if copy_miss["boss_heal"] > 0:
            player.current_boss_hp = min(boss.hp, (player.current_boss_hp or 0) + copy_miss["boss_heal"])

    # Boss 5 (Sandbox Tyrant): random opponent gains 1 Licenza when player takes damage
    if player_took_damage:
        dmg_effect = engine.apply_boss_ability(boss.id, "on_player_damage")
        if dmg_effect["opponent_gains_licenza"] > 0:
            opponents = [p for p in game.players if p.id != player.id]
            if opponents:
                random.choice(opponents).licenze += dmg_effect["opponent_gains_licenza"]

    # ── on_round_end effects ──────────────────────────────────────────────
    round_end = engine.apply_boss_ability(
        boss.id, "on_round_end",
        combat_round=current_round,
        cards_played=player.cards_played_this_turn,
    )

    # Boss 11 (LWC Poltergeist): even rounds → random opponent takes 1 HP
    if round_end["aoe_hp_damage"] > 0:
        opponents = [p for p in game.players if p.id != player.id]
        if opponents:
            target = random.choice(opponents)
            target.hp = max(0, target.hp - round_end["aoe_hp_damage"])

    # Boss 27 (Marketing Cloud Banshee): every round ALL opponents (not combatant) lose 1 HP
    if round_end["aoe_all_hp_damage"] > 0:
        for p_aoe in [p for p in game.players if p.id != player.id]:
            p_aoe.hp = max(0, p_aoe.hp - round_end["aoe_all_hp_damage"])

    # Boss 50 (Health Cloud Plague) / Boss 40 (on_round_end variant): ALL players lose 1 HP
    if round_end["aoe_all_players_hp_damage"] > 0:
        for p_aoe in game.players:
            p_aoe.hp = max(0, p_aoe.hp - round_end["aoe_all_players_hp_damage"])

    # Boss 87 (Pub/Sub API Pestilence): ALL players lose 1 HP, not blockable by defensive cards
    if round_end["aoe_unblockable_hp_damage"] > 0:
        for p_aoe in game.players:
            p_aoe.hp = max(0, p_aoe.hp - round_end["aoe_unblockable_hp_damage"])

    # Boss 84 (Data Import Doomsayer): if fight runs longer than prediction, deal 1 extra HP per excess round
    if player.combat_state:
        dcap = player.combat_state.get("doomsayer_prediction_cap")
        if dcap is not None and current_round > dcap:
            player.hp = max(0, player.hp - 1)

    # Boss 55 / Boss 74: apply shadow copy's on_round_end effects
    if copy_boss_id:
        copy_re = engine.apply_boss_ability(
            copy_boss_id, "on_round_end",
            combat_round=current_round,
            cards_played=player.cards_played_this_turn,
        )
        if copy_re["aoe_hp_damage"] > 0:
            opponents_c = [p for p in game.players if p.id != player.id]
            if opponents_c:
                random.choice(opponents_c).hp = max(0, random.choice(opponents_c).hp - copy_re["aoe_hp_damage"])
        if copy_re["aoe_all_hp_damage"] > 0:
            for p_c in [p for p in game.players if p.id != player.id]:
                p_c.hp = max(0, p_c.hp - copy_re["aoe_all_hp_damage"])
        if copy_re["aoe_all_players_hp_damage"] > 0:
            for p_c in game.players:
                p_c.hp = max(0, p_c.hp - copy_re["aoe_all_players_hp_damage"])

    # Boss 73 (Streaming API Storm): every round a random opponent draws 1 extra card
    if round_end["opponent_draws_card"] > 0:
        opponents_draw = [p for p in game.players if p.id != player.id]
        if opponents_draw:
            target_draw = random.choice(opponents_draw)
            from app.models.game import PlayerHandCard as PHC_draw
            if game.action_deck_1:
                db.add(PHC_draw(player_id=target_draw.id, action_card_id=game.action_deck_1.pop(0)))
            elif game.action_deck_2:
                db.add(PHC_draw(player_id=target_draw.id, action_card_id=game.action_deck_2.pop(0)))

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

        # ── on_boss_defeated effects ──────────────────────────────────────
        defeated_effect = engine.apply_boss_ability(
            boss.id, "on_boss_defeated", cards_played=player.cards_played_this_turn
        )
        # Boss 19 (Dreamforce Hydra): +1 bonus certification on kill
        if defeated_effect["bonus_certification"] > 0:
            player.certificazioni += defeated_effect["bonus_certification"]
        # Boss 20 (Corrupted Trailblazer): +3 licenze if no cards played this turn
        if defeated_effect["bonus_licenze"] > 0:
            player.licenze += defeated_effect["bonus_licenze"]

        # Boss 25 (Heroku Dyno Zombie): one-shot revive — only fires if resurrection not yet used
        if defeated_effect["boss_revive"] > 0:
            cs = dict(player.combat_state or {})
            if not cs.get("resurrection_used", False):
                cs["resurrection_used"] = True
                player.combat_state = cs
                player.current_boss_hp = defeated_effect["boss_revive"]
                db.commit()
                db.refresh(game)
                await manager.broadcast(game.code, {
                    "type": "boss_revived",
                    "player_id": player.id,
                    "boss_id": boss.id,
                    "new_hp": player.current_boss_hp,
                })
                await _broadcast_state(game, db)
                return  # combat continues — boss revived

        # Boss 34 (Batch Apex Necromancer): first defeat re-inserts boss into deck; second is permanent
        if defeated_effect["boss_revive_to_deck"] > 0:
            cs = dict(player.combat_state or {})
            if not cs.get("necromancer_resurrected", False):
                cs["necromancer_resurrected"] = True
                player.combat_state = cs
                if player.current_boss_source in ("deck_1", "market_1"):
                    game.boss_deck_1 = (game.boss_deck_1 or []) + [boss.id]
                else:
                    game.boss_deck_2 = (game.boss_deck_2 or []) + [boss.id]
            # On second defeat the boss is simply discarded normally (falls through to defeat logic)

        # Boss 26 (CPQ Configuration Chaos): next addon purchase costs +3 licenze
        if defeated_effect["next_addon_cost_penalty"] > 0:
            player.pending_addon_cost_penalty = (
                (player.pending_addon_cost_penalty or 0) + defeated_effect["next_addon_cost_penalty"]
            )

        # Boss 99 (CTA Titan): every player who played an action card this combat gains N licenze
        if defeated_effect["bonus_licenze_to_helpers"] > 0:
            for p_help in game.players:
                if p_help.id != player.id and p_help.cards_played_this_turn > 0:
                    p_help.licenze += defeated_effect["bonus_licenze_to_helpers"]

        # Boss 100 (Lost Trailblazer Omega): instant win regardless of cert count
        if defeated_effect["instant_win"]:
            game.status = GameStatus.finished
            game.winner_id = player.id
            from datetime import datetime, timezone
            game.finished_at = datetime.now(timezone.utc)
            _apply_elo(game, player.id, db)
            db.commit()
            await manager.broadcast(game.code, {"type": ServerEvent.GAME_OVER, "winner_id": player.id})
            await _broadcast_state(game, db)
            return

        # Boss 31 (AppExchange Parasite): unlock locked addon (untap it)
        # Boss 91 (List View Usurper): return stolen addon to player's possession
        if defeated_effect["unlock_locked_addon"] and player.combat_state:
            cs = player.combat_state
            locked_pa_id = cs.get("locked_addon_id")
            stolen_addon_id = cs.get("stolen_addon_id")
            if locked_pa_id:
                from app.models.game import PlayerAddon as _PA
                pa_unlock = db.get(_PA, locked_pa_id)
                if pa_unlock and pa_unlock.player_id == player.id:
                    pa_unlock.is_tapped = False
            if stolen_addon_id:
                from app.models.game import PlayerAddon as _PA2
                db.add(_PA2(player_id=player.id, addon_id=stolen_addon_id))

        # Boss 82 (Customer 360 Gorgon): clear petrified cards on defeat
        if player.combat_state and player.combat_state.get("petrified_card_ids"):
            cs = dict(player.combat_state)
            cs.pop("petrified_card_ids", None)
            player.combat_state = cs

        # Boss 55 / Boss 74: also apply shadow copy's on_boss_defeated effects
        if copy_boss_id:
            copy_def = engine.apply_boss_ability(
                copy_boss_id, "on_boss_defeated",
                cards_played=player.cards_played_this_turn,
            )
            if copy_def["bonus_certification"] > 0:
                player.certificazioni += copy_def["bonus_certification"]
            if copy_def["bonus_licenze"] > 0:
                player.licenze += copy_def["bonus_licenze"]
            if copy_def["next_addon_cost_penalty"] > 0:
                player.pending_addon_cost_penalty = (
                    (player.pending_addon_cost_penalty or 0) + copy_def["next_addon_cost_penalty"]
                )

        # Boss 100 (Omega): also apply the last legendary boss's on_boss_defeated effects
        if engine.boss_is_omega(boss.id) and game.last_defeated_legendary_boss_id:
            omega_def = engine.apply_boss_ability(
                game.last_defeated_legendary_boss_id, "on_boss_defeated",
                cards_played=player.cards_played_this_turn,
            )
            if omega_def["bonus_certification"] > 0:
                player.certificazioni += omega_def["bonus_certification"]
            if omega_def["bonus_licenze"] > 0:
                player.licenze += omega_def["bonus_licenze"]

        # Track last defeated boss for mimic (55) / shape shifter (74) / omega (100) routing
        game.last_defeated_boss_id = boss.id
        if boss.has_certification:
            game.last_defeated_legendary_boss_id = boss.id

        source = player.current_boss_source
        if boss.has_certification:
            # Cert boss becomes a trophy in the player's possession.
            # Can be stolen or destroyed by other players via card effects.
            # Only goes to boss_graveyard if destroyed from a player's trophies.
            player.trophies = (player.trophies or []) + [boss.id]
        else:
            # Non-cert bosses go to the shared graveyard
            game.boss_graveyard = (game.boss_graveyard or []) + [boss.id]
        # Refill market slot if boss was taken from market
        if source == "market_1":
            game.boss_market_1 = game.boss_deck_1.pop(0) if game.boss_deck_1 else None
        elif source == "market_2":
            game.boss_market_2 = game.boss_deck_2.pop(0) if game.boss_deck_2 else None

        player.is_in_combat = False
        player.current_boss_id = None
        player.current_boss_hp = None
        player.current_boss_source = None
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
        if "card" in penalty["lost"]:
            lost_card_id = penalty["lost"]["card"]
            hc_to_remove = next((hc for hc in player.hand if hc.action_card_id == lost_card_id), None)
            if hc_to_remove:
                game.action_discard = (game.action_discard or []) + [lost_card_id]
                db.delete(hc_to_remove)

        # Remove lost addon
        if "addon" in penalty["lost"]:
            lost_addon_id = penalty["lost"]["addon"]
            pa_to_remove = next((pa for pa in player.addons if pa.addon_id == lost_addon_id), None)
            if pa_to_remove:
                game.addon_graveyard = (game.addon_graveyard or []) + [lost_addon_id]
                db.delete(pa_to_remove)

        player.licenze = penalty["licenze"]
        player.hp = player.max_hp  # respawn with full HP
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
        db.refresh(player)
        await _broadcast_state(game, db)
        await _send_hand_state(game.code, player, db)
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

    # TODO: triggherare gli addon passivi con trigger "fine turno" o "inizio turno".
    # Alcuni addon applicano effetti periodici (es. guadagna 1L ogni turno, recupera 1HP, ecc.).
    # Va chiamata trigger_passive_addons(event="on_turn_end", player, game, db) prima di avanzare.

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

    pa.is_tapped = True

    # Boss 49 (Managed Package Leech): boss heals 1 HP every time combatant activates an addon
    if player.is_in_combat and player.current_boss_id:
        boss_for_addon = db.get(BossCard, player.current_boss_id)
        heal = engine.boss_heals_on_addon_use(player.current_boss_id)
        if heal > 0 and boss_for_addon:
            player.current_boss_hp = min(boss_for_addon.hp, (player.current_boss_hp or 0) + heal)

    db.commit()
    db.refresh(game)

    # TODO: implementare gli effetti di tutti i 200 addon attivi.
    # Attualmente l'addon viene tappato ma il suo effetto NON viene applicato.
    # Ogni addon va gestito per nome (addon.name) o numero (addon.number) in
    # una funzione dedicata tipo apply_addon_effect(addon, player, game, db).
    # Gli addon Passivi hanno effetti che si attivano automaticamente in
    # determinati momenti del gioco (roll_dice, acquisto, inizio turno, ecc.)
    # e vanno anch'essi implementati nei punti giusti del flusso.
    # Vedere cards/addon_cards.md per l'effetto completo di ogni addon.

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

    # Boss 66 (Deploy to Production Nemesis): retreat is permanently blocked
    if engine.boss_blocks_retreat(player.current_boss_id):
        await _error(game.code, user_id, "Retreat blocked by boss ability")
        return

    boss_id = player.current_boss_id
    source = player.current_boss_source
    # Boss goes back to its origin: deck → top of that deck; market → back to its market slot
    if source == "deck_1":
        game.boss_deck_1 = [boss_id] + (game.boss_deck_1 or [])
    elif source == "deck_2":
        game.boss_deck_2 = [boss_id] + (game.boss_deck_2 or [])
    elif source == "market_1":
        game.boss_market_1 = boss_id
    elif source == "market_2":
        game.boss_market_2 = boss_id
    player.is_in_combat = False
    player.current_boss_id = None
    player.current_boss_hp = None
    player.current_boss_source = None
    game.current_phase = TurnPhase.action
    db.commit()
    db.refresh(game)

    await manager.broadcast(game.code, {
        "type": ServerEvent.COMBAT_ENDED,
        "player_id": player.id,
        "retreated": True,
    })
    await _broadcast_state(game, db)


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
