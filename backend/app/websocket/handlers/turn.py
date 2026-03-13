"""
Turn phase handlers: draw card, play card, buy addon, use addon, end turn.
"""
import random
from sqlalchemy.orm import Session

from app.websocket.manager import manager
from app.websocket.events import ServerEvent
from app.websocket.game_helpers import (
    _get_player, _is_player_turn, _error, _broadcast_state, _send_hand_state,
)
from app.models.game import GameSession, GameStatus, TurnPhase
from app.models.card import ActionCard, BossCard, AddonCard
from app.game import engine


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
