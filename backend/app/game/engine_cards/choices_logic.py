"""
Pure resolver functions for pending card choices.

Each function takes the game/player/db objects and the validated choice data,
performs the DB mutations, and returns either:
  {"ok": True, ...extra_info}   — success
  {"error": "message"}          — validation failure (caller sends error to client)

No WebSocket calls here. The WS layer (choices.py) is responsible for:
  - extracting payload from client data
  - calling the resolver
  - sending the error or broadcasting state
"""
from app.game import engine


def resolve_discard_specific_cards(game, player, db, chosen_ids: list, count: int) -> dict:
    """Card 68 — discard exactly `count` cards from hand.
    chosen_ids: list of PlayerHandCard.id
    """
    if len(chosen_ids) != count:
        return {"error": f"Devi scegliere esattamente {count} carte"}
    from app.models.game import PlayerHandCard as _PHC
    for hcid in chosen_ids:
        hc = db.get(_PHC, hcid)
        if not hc or hc.player_id != player.id:
            return {"error": f"Carta non valida: {hcid}"}
        game.action_discard = (game.action_discard or []) + [hc.action_card_id]
        db.delete(hc)
    return {"ok": True, "discarded": chosen_ids}


def resolve_reorder_boss_deck(game, player, db, ordered_ids: list, original: list) -> dict:
    """Card 67 — reorder top N boss cards.
    ordered_ids: boss card IDs in new preferred order.
    original: the IDs that were shown to the player (from pending).
    """
    if sorted(ordered_ids) != sorted(original):
        return {"error": "Ordine non valido — usa le stesse carte boss"}
    game.boss_deck_1 = ordered_ids + (game.boss_deck_1 or [])[len(ordered_ids):]
    return {"ok": True, "new_order": ordered_ids}


def resolve_reorder_action_deck(game, player, db, ordered_ids: list, original: list) -> dict:
    """Cards 32, 107 — reorder top N action cards.
    ordered_ids: action card IDs in new preferred order.
    original: the IDs that were shown to the player (from pending).
    """
    if sorted(ordered_ids) != sorted(original):
        return {"error": "Ordine non valido — usa le stesse carte azione"}
    game.action_deck_1 = ordered_ids + (game.action_deck_1 or [])[len(ordered_ids):]
    return {"ok": True, "new_order": ordered_ids}


def resolve_keep_one_from_drawn(game, player, db, keep_id: int, drawn: list) -> dict:
    """Card 137 — keep one drawn card, return the rest to the top of action_deck_1.
    keep_id: action_card_id to keep.
    drawn: list of action_card_ids that were drawn.
    """
    if keep_id not in drawn:
        return {"error": "La carta scelta non era tra quelle pescate"}
    from app.models.game import PlayerHandCard as _PHC
    to_return = [cid for cid in drawn if cid != keep_id]
    for cid in to_return:
        hc = db.query(_PHC).filter(
            _PHC.player_id == player.id,
            _PHC.action_card_id == cid,
        ).first()
        if hc:
            db.delete(hc)
    db.flush()
    game.action_deck_1 = to_return + (game.action_deck_1 or [])
    return {"ok": True, "kept": keep_id, "returned": to_return}


def resolve_recover_from_discard(game, player, db, chosen_ids: list, count: int) -> dict:
    """Cards 34, 69 — recover `count` cards from action discard pile into hand.
    chosen_ids: list of action_card_id to recover.
    """
    if len(chosen_ids) != count:
        return {"error": f"Devi scegliere esattamente {count} carte"}
    discard = list(game.action_discard or [])
    from app.models.game import PlayerHandCard as _PHC
    recovered = []
    for cid in chosen_ids:
        if cid not in discard:
            return {"error": f"Carta {cid} non è negli scarti"}
        if len(list(player.hand)) >= engine.MAX_HAND_SIZE:
            break
        discard.remove(cid)
        db.add(_PHC(player_id=player.id, action_card_id=cid))
        recovered.append(cid)
    game.action_discard = discard
    return {"ok": True, "recovered": recovered}


def resolve_return_card_to_deck_top(game, player, db, chosen_hc_id: int) -> dict:
    """Card 106 — return a card from hand to the top of action_deck_1.
    chosen_hc_id: PlayerHandCard.id of the card to return.
    """
    from app.models.game import PlayerHandCard as _PHC
    hc = db.get(_PHC, chosen_hc_id)
    if not hc or hc.player_id != player.id:
        return {"error": "Carta non valida"}
    card_id = hc.action_card_id
    db.delete(hc)
    db.flush()
    game.action_deck_1 = [card_id] + (game.action_deck_1 or [])
    return {"ok": True, "returned_card_id": card_id}


def resolve_choose_cards_to_keep(game, player, db, keep_hc_ids: list, drawn: list, max_keep: int) -> dict:
    """Card 108 — keep up to `max_keep` drawn cards, shuffle the rest back into the deck.
    keep_hc_ids: list of PlayerHandCard.id to keep.
    drawn: list of action_card_ids that were drawn (from pending).
    """
    if len(keep_hc_ids) > max_keep:
        return {"error": f"Puoi tenere al massimo {max_keep} carte"}
    from app.models.game import PlayerHandCard as _PHC
    keep_action_ids = []
    for hcid in keep_hc_ids:
        hc = db.get(_PHC, hcid)
        if not hc or hc.player_id != player.id:
            return {"error": f"Carta non valida: {hcid}"}
        keep_action_ids.append(hc.action_card_id)
    discard_ids = [cid for cid in drawn if cid not in keep_action_ids]
    for cid in discard_ids:
        hc = db.query(_PHC).filter(
            _PHC.player_id == player.id,
            _PHC.action_card_id == cid,
        ).first()
        if hc:
            db.delete(hc)
    db.flush()
    if discard_ids:
        shuffled = engine.shuffle_deck(discard_ids)
        game.action_deck_1 = (game.action_deck_1 or []) + shuffled
    return {"ok": True, "kept": keep_action_ids, "returned_to_deck": discard_ids}


def resolve_choose_addon_to_return(game, player, db, chosen_pa_id: int, licenze_gained: int) -> dict:
    """Card 110 — return an owned addon to the market deck, gain licenze.
    chosen_pa_id: PlayerAddon.id to return.
    licenze_gained: amount to grant (from pending).
    """
    from app.models.game import PlayerAddon as _PA
    pa = db.get(_PA, chosen_pa_id)
    if not pa or pa.player_id != player.id:
        return {"error": "Addon non valido"}
    addon_id = pa.addon_id
    game.addon_deck_1 = [addon_id] + (game.addon_deck_1 or [])
    db.delete(pa)
    db.flush()
    player.licenze += licenze_gained
    return {"ok": True, "returned_addon_id": addon_id, "licenze_gained": licenze_gained}


def resolve_delete_target_addon(game, player, db, chosen_pa_id: int, target_player_id: int) -> dict:
    """Card 189 — delete a specific addon belonging to the target player.
    chosen_pa_id: PlayerAddon.id to delete (must belong to target_player_id).
    target_player_id: the player whose addon is being destroyed.
    """
    from app.models.game import PlayerAddon as _PA
    pa = db.get(_PA, chosen_pa_id)
    if not pa or pa.player_id != target_player_id:
        return {"error": "Addon non valido o non appartiene al bersaglio"}
    addon_id = pa.addon_id
    game.addon_deck_1 = (game.addon_deck_1 or []) + [addon_id]
    game.addon_graveyard = (game.addon_graveyard or []) + [addon_id]
    db.delete(pa)
    db.flush()
    return {"ok": True, "deleted_addon_id": addon_id}
