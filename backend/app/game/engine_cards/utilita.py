"""Carte Utilità — gestione mano, mazzo e risorse (carte 31–37, 63–69, 80, 106–110)."""
import random

from app.game import engine
from app.models.card import BossCard, AddonCard


def _card_31(player, game, db, *, target_player_id=None) -> dict:
    """Trailhead Module — Pesca 2 carte extra (fuori da combattimento)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "cannot_use_in_combat"}

    from app.models.game import PlayerHandCard
    drawn = 0
    for _ in range(2):
        if len(list(player.hand)) + drawn >= engine.MAX_HAND_SIZE:
            break
        if game.action_deck_1:
            db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            drawn += 1
        elif game.action_deck_2:
            db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
            drawn += 1
        elif game.action_discard:
            new_deck = engine.shuffle_deck(game.action_discard)
            game.action_deck_1, game.action_deck_2 = engine.split_deck(new_deck)
            game.action_discard = []
            if game.action_deck_1:
                db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
                drawn += 1

    return {"applied": True, "cards_drawn": drawn}


def _card_32(player, game, db, *, target_player_id=None) -> dict:
    """Knowledge Article — Guarda le prime 3 carte del mazzo azione e rimettile nell'ordine preferito.

    Returns top 3 card info as revealed_top_cards. Reordering requires a second client
    message with the preferred order — not yet implemented (TODO).
    """
    from app.models.card import ActionCard

    preview = []
    for cid in (game.action_deck_1 or [])[:3]:
        card = db.get(ActionCard, cid)
        if card:
            preview.append({"id": card.id, "number": card.number, "name": card.name})
    return {
        "applied": True,
        "revealed_top_cards": preview,
        "note": "reorder_requires_client_followup",
    }


def _card_33(player, game, db, *, target_player_id=None) -> dict:
    """Quick Action — Questa carta non conta come una delle 2 carte giocabili per turno.

    Decrements cards_played_this_turn by 1 to cancel the +1 applied before this call.
    """
    player.cards_played_this_turn = max(0, player.cards_played_this_turn - 1)
    return {"applied": True, "card_did_not_count": True}


def _card_34(player, game, db, *, target_player_id=None) -> dict:
    """Recycle Bin — Recupera fino a 2 carte dal mazzo degli scarti (fuori da combattimento).

    Takes the 2 most recently discarded cards and adds them to the player's hand.
    TODO: accept specific card IDs from client via extra_data for player choice.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "cannot_use_in_combat"}

    from app.models.game import PlayerHandCard
    discard = list(game.action_discard or [])
    recovered = []
    for _ in range(min(2, len(discard))):
        if len(list(player.hand)) + len(recovered) >= engine.MAX_HAND_SIZE:
            break
        card_id = discard.pop(-1)
        db.add(PlayerHandCard(player_id=player.id, action_card_id=card_id))
        recovered.append(card_id)

    game.action_discard = discard
    return {"applied": True, "cards_recovered": recovered}


def _card_35(player, game, db, *, target_player_id=None) -> dict:
    """Sandbox Refresh — Rimescola la mano nel mazzo e pesca 4 nuove carte (fuori da combattimento)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "cannot_use_in_combat"}

    from app.models.game import PlayerHandCard

    # Discard entire hand
    hand_discarded = 0
    for hc in list(player.hand):
        game.action_discard = (game.action_discard or []) + [hc.action_card_id]
        db.delete(hc)
        hand_discarded += 1
    db.flush()

    # Draw 4 new cards
    drawn = 0
    for _ in range(4):
        if game.action_deck_1:
            db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            drawn += 1
        elif game.action_deck_2:
            db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
            drawn += 1
        elif game.action_discard:
            new_deck = engine.shuffle_deck(game.action_discard)
            game.action_deck_1, game.action_deck_2 = engine.split_deck(new_deck)
            game.action_discard = []
            if game.action_deck_1:
                db.add(PlayerHandCard(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
                drawn += 1

    return {"applied": True, "hand_discarded": hand_discarded, "cards_drawn": drawn}


def _card_36(player, game, db, *, target_player_id=None) -> dict:
    """Sprint Planning — Guarda le prime 2 carte del mazzo boss senza pescarle (fuori da combattimento)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "cannot_use_in_combat"}

    preview = []
    for bid in (game.boss_deck_1 or [])[:2]:
        bc = db.get(BossCard, bid)
        if bc:
            preview.append({
                "id": bc.id,
                "name": bc.name,
                "hp": bc.hp,
                "threshold": bc.dice_threshold,
                "has_certification": bc.has_certification,
            })
    return {"applied": True, "revealed_boss_cards": preview}


def _card_37(player, game, db, *, target_player_id=None) -> dict:
    """Free Trial — Pesca 1 carta AddOn e tienila senza pagare per questo turno. Scartata a fine turno.

    Draws from addon_deck_1 (or deck_2 if empty). Creates a PlayerAddon tagged as
    free trial in combat_state["free_trial_addon_player_addon_ids"].
    turn.py _handle_end_turn removes these addons when the player's turn ends.
    """
    from app.models.game import PlayerAddon

    addon_id = None
    if game.addon_deck_1:
        addon_id = game.addon_deck_1.pop(0)
    elif game.addon_deck_2:
        addon_id = game.addon_deck_2.pop(0)

    if addon_id is None:
        return {"applied": False, "reason": "no_addons_available"}

    addon = db.get(AddonCard, addon_id)
    pa = PlayerAddon(player_id=player.id, addon_id=addon_id)
    db.add(pa)
    db.flush()  # needed to get pa.id

    cs = dict(player.combat_state or {})
    trial_ids = list(cs.get("free_trial_addon_player_addon_ids", []))
    trial_ids.append(pa.id)
    cs["free_trial_addon_player_addon_ids"] = trial_ids
    player.combat_state = cs

    return {
        "applied": True,
        "free_trial_addon": {"id": addon.id, "name": addon.name} if addon else {},
        "expires_at_turn_end": True,
    }


def _card_63(player, game, db, *, target_player_id=None) -> dict:
    """Automation Studio — Pesca 2 carte extra (fuori da combattimento)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    from app.models.game import PlayerHandCard as _PHC63
    drawn = 0
    for _ in range(2):
        if len(list(player.hand)) + drawn >= engine.MAX_HAND_SIZE:
            break
        if game.action_deck_1:
            db.add(_PHC63(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            drawn += 1
        elif game.action_deck_2:
            db.add(_PHC63(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
            drawn += 1
        elif game.action_discard:
            new_deck = engine.shuffle_deck(game.action_discard)
            game.action_deck_1, game.action_deck_2 = engine.split_deck(new_deck)
            game.action_discard = []
            if game.action_deck_1:
                db.add(_PHC63(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
                drawn += 1
    return {"applied": True, "cards_drawn": drawn}


def _card_64(player, game, db, *, target_player_id=None) -> dict:
    """Contact Builder — Guarda la mano completa di un avversario a scelta."""
    from app.models.card import ActionCard as _AC64
    from .helpers import get_target
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    hand_info = []
    for hc in target.hand:
        c = db.get(_AC64, hc.action_card_id)
        if c:
            hand_info.append({"id": c.id, "number": c.number, "name": c.name})
    return {"applied": True, "target_player_id": target.id, "revealed_hand": hand_info}


def _card_65(player, game, db, *, target_player_id=None) -> dict:
    """Audience Builder — Guarda le prime 3 carte del mazzo boss senza pescarle."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    preview = []
    for bid in (game.boss_deck_1 or [])[:3]:
        bc = db.get(BossCard, bid)
        if bc:
            preview.append({
                "id": bc.id, "name": bc.name,
                "hp": bc.hp, "threshold": bc.dice_threshold,
                "has_certification": bc.has_certification,
            })
    return {"applied": True, "revealed_boss_cards": preview}


def _card_66(player, game, db, *, target_player_id=None) -> dict:
    """Data Extension — Rimescola il mazzo degli scarti azione nel mazzo principale."""
    if not game.action_discard:
        return {"applied": True, "note": "discard_already_empty", "cards_recycled": 0}
    recycled = len(game.action_discard)
    new_deck = engine.shuffle_deck(game.action_discard)
    d1, d2 = engine.split_deck(new_deck)
    game.action_deck_1 = (game.action_deck_1 or []) + d1
    game.action_deck_2 = (game.action_deck_2 or []) + d2
    game.action_discard = []
    return {"applied": True, "cards_recycled": recycled}


def _card_67(player, game, db, *, target_player_id=None) -> dict:
    """Pipeline Inspection — Guarda e riordina le prime 3 carte del mazzo boss come vuoi.

    Returns top 3 boss card data. Actual reordering requires a follow-up client message.
    TODO: accept preferred_order list from client to reorder boss_deck_1[:3].
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    preview = []
    for bid in (game.boss_deck_1 or [])[:3]:
        bc = db.get(BossCard, bid)
        if bc:
            preview.append({
                "id": bc.id, "name": bc.name,
                "hp": bc.hp, "threshold": bc.dice_threshold,
                "has_certification": bc.has_certification,
            })
    return {
        "applied": True,
        "revealed_boss_cards": preview,
        "note": "reorder_requires_client_followup",
    }


def _card_68(player, game, db, *, target_player_id=None) -> dict:
    """Dataset — Pesca 4 carte e scartane 2 a scelta.

    Simplified: auto-discards 2 oldest hand cards, then draws 4 fresh ones.
    TODO: accept discard_ids from client for real player choice.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    from app.models.game import PlayerHandCard as _PHC68
    current_hand = list(player.hand)
    discarded = 0
    for hc in current_hand[:2]:
        game.action_discard = (game.action_discard or []) + [hc.action_card_id]
        db.delete(hc)
        discarded += 1
    db.flush()
    drawn = 0
    for _ in range(4):
        if len(list(player.hand)) + drawn >= engine.MAX_HAND_SIZE:
            break
        if game.action_deck_1:
            db.add(_PHC68(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            drawn += 1
        elif game.action_deck_2:
            db.add(_PHC68(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
            drawn += 1
        elif game.action_discard:
            new_deck = engine.shuffle_deck(game.action_discard)
            game.action_deck_1, game.action_deck_2 = engine.split_deck(new_deck)
            game.action_discard = []
            if game.action_deck_1:
                db.add(_PHC68(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
                drawn += 1
    return {"applied": True, "discarded": discarded, "cards_drawn": drawn}


def _card_69(player, game, db, *, target_player_id=None) -> dict:
    """Lookup Query — Cerca tra gli ultimi 10 scarti e recupera 1 carta specifica a scelta.

    Simplified: recovers the most recently discarded card (last in action_discard[-10:]).
    TODO: accept target card_id from client for real player choice.
    """
    from app.models.game import PlayerHandCard as _PHC69
    discard = list(game.action_discard or [])
    last_10 = discard[-10:]
    if not last_10:
        return {"applied": False, "reason": "discard_empty"}
    recovered_id = last_10[-1]
    discard.remove(recovered_id)
    game.action_discard = discard
    db.add(_PHC69(player_id=player.id, action_card_id=recovered_id))
    return {"applied": True, "card_recovered": recovered_id}


def _card_80(player, game, db, *, target_player_id=None) -> dict:
    """Choice Router — Scegli: (A) pesca 2 carte oppure (B) guadagna 2 Licenze.

    Client signals choice via target_player_id:
      target_player_id=None  → Choice A: draw 2 cards
      target_player_id!=None → Choice B: +2 Licenze
    """
    from app.models.game import PlayerHandCard as _PHC80
    if target_player_id is None:
        drawn = 0
        for _ in range(2):
            if len(list(player.hand)) + drawn >= engine.MAX_HAND_SIZE:
                break
            if game.action_deck_1:
                db.add(_PHC80(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
                drawn += 1
            elif game.action_deck_2:
                db.add(_PHC80(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
                drawn += 1
        return {"applied": True, "choice": "A", "cards_drawn": drawn}
    else:
        player.licenze += 2
        return {"applied": True, "choice": "B", "licenze_gained": 2}


def _card_106(player, game, db, *, target_player_id=None) -> dict:
    """Anypoint Studio — Pesca 3 carte, tieni 2, la 3ª torna in cima al mazzo (fuori da combattimento).

    Draws 3: keeps first 2, puts 3rd back on top of action_deck_1.
    TODO: accept discard_id from client to choose which card to return.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    from app.models.game import PlayerHandCard as _PHC106
    drawn_ids = []
    for _ in range(3):
        if game.action_deck_1:
            drawn_ids.append(game.action_deck_1.pop(0))
        elif game.action_deck_2:
            drawn_ids.append(game.action_deck_2.pop(0))
        elif game.action_discard:
            new_deck = engine.shuffle_deck(game.action_discard)
            game.action_deck_1, game.action_deck_2 = engine.split_deck(new_deck)
            game.action_discard = []
            if game.action_deck_1:
                drawn_ids.append(game.action_deck_1.pop(0))
    for cid in drawn_ids[:2]:
        db.add(_PHC106(player_id=player.id, action_card_id=cid))
    if len(drawn_ids) == 3:
        game.action_deck_1 = [drawn_ids[2]] + (game.action_deck_1 or [])
    return {"applied": True, "cards_kept": min(2, len(drawn_ids)), "cards_returned": 1 if len(drawn_ids) == 3 else 0}


def _card_107(player, game, db, *, target_player_id=None) -> dict:
    """Flow Designer — Guarda e riordina le prime 3 carte del mazzo azione (fuori da combattimento).

    Returns top 3 action deck card info. Reordering requires follow-up client message.
    TODO: accept preferred_order from client to reorder action_deck_1[:3].
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    from app.models.card import ActionCard as _AC107
    preview = []
    for cid in (game.action_deck_1 or [])[:3]:
        c = db.get(_AC107, cid)
        if c:
            preview.append({"id": c.id, "number": c.number, "name": c.name})
    return {"applied": True, "revealed_top_cards": preview, "note": "reorder_requires_client_followup"}


def _card_108(player, game, db, *, target_player_id=None) -> dict:
    """Design Center — Guarda le prime 4 carte del mazzo azione e tienine 2; le altre tornano mescolate.

    Draws 4: keeps first 2, shuffles other 2 back into deck.
    TODO: accept chosen IDs from client for real player choice.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    from app.models.game import PlayerHandCard as _PHC108
    drawn_ids = []
    for _ in range(4):
        if game.action_deck_1:
            drawn_ids.append(game.action_deck_1.pop(0))
        elif game.action_deck_2:
            drawn_ids.append(game.action_deck_2.pop(0))
        elif game.action_discard:
            new_deck = engine.shuffle_deck(game.action_discard)
            game.action_deck_1, game.action_deck_2 = engine.split_deck(new_deck)
            game.action_discard = []
            if game.action_deck_1:
                drawn_ids.append(game.action_deck_1.pop(0))
    for cid in drawn_ids[:2]:
        if len(list(player.hand)) < engine.MAX_HAND_SIZE:
            db.add(_PHC108(player_id=player.id, action_card_id=cid))
        else:
            drawn_ids.append(cid)  # can't keep, return it
    returned = drawn_ids[2:]
    if returned:
        shuffled = engine.shuffle_deck(returned)
        game.action_deck_1 = (game.action_deck_1 or []) + shuffled
    return {"applied": True, "cards_kept": min(2, len(drawn_ids)), "cards_returned": len(returned)}


def _card_109(player, game, db, *, target_player_id=None) -> dict:
    """Checkout Flow — Gioca 1 carta azione extra che non conta nel limite (fuori da combattimento).

    Decrements cards_played_this_turn by 1 to cancel the +1 applied before this call.
    The addon purchase is handled separately via buy_addon.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.cards_played_this_turn = max(0, player.cards_played_this_turn - 1)
    return {"applied": True, "card_did_not_count": True, "note": "buy addon separately via buy_addon action"}


def _card_110(player, game, db, *, target_player_id=None) -> dict:
    """Return Order — Restituisci 1 tuo AddOn al mazzo e recupera 8 Licenze (fuori da combattimento).

    Removes the most recently acquired addon and returns it to addon_deck_1, +8 Licenze.
    TODO: accept addon_id from client for real player choice.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    addons = list(player.addons)
    if not addons:
        return {"applied": False, "reason": "no_addons_to_return"}
    from app.models.card import AddonCard as _ADC110
    pa = addons[-1]  # most recently acquired (last in relationship list)
    addon = db.get(_ADC110, pa.addon_id)
    game.addon_deck_1 = [pa.addon_id] + (game.addon_deck_1 or [])
    db.delete(pa)
    player.licenze += 8
    return {
        "applied": True,
        "returned_addon": {"id": pa.addon_id, "name": addon.name if addon else None},
        "licenze_gained": 8,
    }


UTILITA: dict = {
    31: _card_31,
    32: _card_32,
    33: _card_33,
    34: _card_34,
    35: _card_35,
    36: _card_36,
    37: _card_37,
    63: _card_63,
    64: _card_64,
    65: _card_65,
    66: _card_66,
    67: _card_67,
    68: _card_68,
    69: _card_69,
    80: _card_80,
    106: _card_106,
    107: _card_107,
    108: _card_108,
    109: _card_109,
    110: _card_110,
}
