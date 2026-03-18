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
    """Quick Action — Non conta come una delle 2 carte giocabili per turno; pesca 2 carte.

    Decrements cards_played_this_turn by 1 to cancel the +1 applied before this call.
    """
    from app.models.game import PlayerHandCard
    player.cards_played_this_turn = max(0, player.cards_played_this_turn - 1)
    drew = 0
    for _ in range(2):
        src = game.action_deck_1 if game.action_deck_1 else game.action_deck_2
        if src:
            db.add(PlayerHandCard(player_id=player.id, action_card_id=src.pop(0)))
            drew += 1
    return {"applied": True, "card_did_not_count": True, "drew": drew}


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
    """Checkout Flow — Acquista gratis 1 AddOn dal mazzo; gioca 1 carta extra che non conta nel limite.

    Takes the first addon from addon_deck_1 (or deck_2) and gives it to the player for free.
    Also decrements cards_played_this_turn by 1 so this card itself doesn't count.
    """
    from app.models.game import PlayerAddon
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    src_deck = "deck_1" if game.addon_deck_1 else ("deck_2" if game.addon_deck_2 else None)
    if not src_deck:
        return {"applied": False, "reason": "no_addon_available"}
    addon_id = game.addon_deck_1.pop(0) if src_deck == "deck_1" else game.addon_deck_2.pop(0)
    db.add(PlayerAddon(player_id=player.id, addon_id=addon_id))
    player.cards_played_this_turn = max(0, player.cards_played_this_turn - 1)
    return {"applied": True, "addon_acquired_free": addon_id, "card_did_not_count": True}


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


def _card_137(player, game, db, *, target_player_id=None) -> dict:
    """CPQ Rules Engine — Cerca le prime 5 carte del mazzo azione e aggiungine 1 alla mano; rimetti le altre nell'ordine originale.

    Draws top 5, keeps first (auto-selected; TODO: accept chosen_id from client).
    Returns the remaining 4 to top of deck in their original order.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    from app.models.game import PlayerHandCard as _PHC137
    drawn_ids = []
    for _ in range(5):
        if game.action_deck_1:
            drawn_ids.append(game.action_deck_1.pop(0))
        elif game.action_deck_2:
            drawn_ids.append(game.action_deck_2.pop(0))
    if not drawn_ids:
        return {"applied": False, "reason": "action_deck_empty"}
    # Keep first, return the rest in original order to top of deck
    if len(list(player.hand)) < engine.MAX_HAND_SIZE:
        db.add(_PHC137(player_id=player.id, action_card_id=drawn_ids[0]))
        kept = 1
        returned = drawn_ids[1:]
    else:
        kept = 0
        returned = drawn_ids
    game.action_deck_1 = returned + (game.action_deck_1 or [])
    return {"applied": True, "cards_kept": kept, "cards_returned": len(returned)}


def _card_138(player, game, db, *, target_player_id=None) -> dict:
    """Pardot Form Handler — Ogni volta che un avversario pesca una carta in questo turno, pesca 1 anche tu (max 2).

    Stores pardot_form_handler_remaining=2 in player's combat_state.
    turn.py draw_card: after each opponent draw, if any other player has this flag active
    (non-current-turn player), award them 1 draw and decrement the counter.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    cs = dict(player.combat_state or {})
    cs["pardot_form_handler_remaining"] = 2
    player.combat_state = cs
    return {"applied": True, "pardot_form_handler_remaining": 2}


def _card_172(player, game, db, *, target_player_id=None) -> dict:
    """Tableau Dashboard — Pesca 2 carte e guarda le prime 2 del mazzo boss (info)."""
    from app.models.game import PlayerHandCard as _PHC172
    drew = 0
    for deck in (game.action_deck_1, game.action_deck_2):
        if deck and drew < 2:
            db.add(_PHC172(player_id=player.id, action_card_id=deck.pop(0)))
            drew += 1
    next_boss_ids = (game.boss_deck_1 or game.boss_deck_2 or [])[:2]
    return {"applied": True, "cards_drawn": drew, "next_boss_card_ids": next_boss_ids}


def _card_173(player, game, db, *, target_player_id=None) -> dict:
    """CRM Analytics — Riordina le prime 4 carte del mazzo azione nell'ordine preferito.

    Stores crm_analytics_reorder_pending=True; the WS handler should prompt the client
    to provide an ordered list of top-4 card IDs, then commit the reorder via a follow-up event.
    Fallback: no-op (ordering unchanged) until WS hook implemented.
    """
    cs = dict(player.combat_state or {})
    cs["crm_analytics_reorder_pending"] = True
    player.combat_state = cs
    top4 = (game.action_deck_1 or game.action_deck_2 or [])[:4]
    return {"applied": True, "crm_analytics_reorder_pending": True, "top4_card_ids": top4}


def _card_174(player, game, db, *, target_player_id=None) -> dict:
    """App Analytics — Tra gli ultimi 5 scarti azione, recupera 1 carta (la più recente).

    Simplified: recovers the most recent card from game.action_discard.
    Full implementation requires client to select from last 5 discards.
    """
    from app.models.game import PlayerHandCard as _PHC174
    discard = list(game.action_discard or [])
    if not discard:
        return {"applied": False, "reason": "discard_empty"}
    recovered_id = discard.pop()
    game.action_discard = discard
    db.add(_PHC174(player_id=player.id, action_card_id=recovered_id))
    return {"applied": True, "recovered_card_id": recovered_id}


def _card_175(player, game, db, *, target_player_id=None) -> dict:
    """Profile Explorer — Pesca 2 carte e guadagna 2 Licenze."""
    from app.models.game import PlayerHandCard as _PHC175
    drew = 0
    for _ in range(2):
        src = game.action_deck_1 if game.action_deck_1 else game.action_deck_2
        if src:
            db.add(_PHC175(player_id=player.id, action_card_id=src.pop(0)))
            drew += 1
    player.licenze += 2
    return {"applied": True, "drew": drew, "licenze_gained": 2}


def _card_176(player, game, db, *, target_player_id=None) -> dict:
    """Customer 360 — Vedi mano, AddOn, HP e Licenze di tutti i giocatori per 1 turno intero.

    Stores customer_360_active=True; WS handler may expose extra info this turn.
    """
    cs = dict(player.combat_state or {})
    cs["customer_360_active"] = True
    player.combat_state = cs
    snapshot = [
        {
            "player_id": p.id,
            "hp": p.hp,
            "licenze": p.licenze,
            "hand_size": len(list(p.hand)),
            "addon_count": len(list(p.addons)),
        }
        for p in game.players
    ]
    return {"applied": True, "customer_360_active": True, "player_snapshots": snapshot}


def _card_177(player, game, db, *, target_player_id=None) -> dict:
    """Database Connector — Cerca tra gli ultimi 10 scarti e recupera 1 carta specifica.

    Simplified: recovers the most recent card from game.action_discard (last 10 pool).
    Full implementation requires client to specify the target card ID from the last 10.
    """
    from app.models.game import PlayerHandCard as _PHC177
    discard = list(game.action_discard or [])
    if not discard:
        return {"applied": False, "reason": "discard_empty"}
    recovered_id = discard.pop()
    game.action_discard = discard
    db.add(_PHC177(player_id=player.id, action_card_id=recovered_id))
    return {"applied": True, "recovered_card_id": recovered_id}


def _card_178(player, game, db, *, target_player_id=None) -> dict:
    """VM Queue — Scarta tutta la mano e pesca lo stesso numero di carte.

    Discards all cards in hand to action_discard, then draws the same number from the deck.
    """
    from app.models.game import PlayerHandCard as _PHC178
    hand_cards = list(player.hand)
    count = len(hand_cards)
    if count == 0:
        return {"applied": False, "reason": "no_cards_in_hand"}
    discarded = []
    for hc in hand_cards:
        discarded.append(hc.action_card_id)
        db.delete(hc)
    game.action_discard = (game.action_discard or []) + discarded
    drew = 0
    for _ in range(count):
        src = game.action_deck_1 if game.action_deck_1 else game.action_deck_2
        if src:
            db.add(_PHC178(player_id=player.id, action_card_id=src.pop(0)))
            drew += 1
    return {"applied": True, "discarded": len(discarded), "drew": drew}


def _card_179(player, game, db, *, target_player_id=None) -> dict:
    """API Autodiscovery — Guarda i prossimi 3 boss e rimettili nell'ordine che preferisci.

    Returns the top 3 boss IDs from deck_1 (or deck_2) for client inspection.
    Client must respond with 'api_autodiscovery_reorder' action providing the
    ordered list of those boss IDs; server updates the deck accordingly.
    """
    src = game.boss_deck_1 if game.boss_deck_1 else game.boss_deck_2
    if not src:
        return {"applied": False, "reason": "no_boss_deck"}
    preview = src[:3]
    cs = dict(player.combat_state or {})
    cs["api_autodiscovery_pending"] = preview
    player.combat_state = cs
    return {"applied": True, "boss_preview": preview, "note": "api_autodiscovery_reorder_required"}


def _card_180(player, game, db, *, target_player_id=None) -> dict:
    """Related Attribute — Vendi 1 tuo addon: recupera metà del costo in Licenze e pesca 1 carta.

    Sends the player's addon list for selection via 'related_attribute_sell' ClientAction
    with player_addon_id. Handler removes the PlayerAddon, awards floor(cost/2) Licenze,
    draws 1 card, and returns the addon to addon_deck_1.
    Stores related_attribute_sell_pending=True in combat_state to open the selection window.
    """
    from app.models.game import PlayerHandCard as _PHC180
    addons = list(player.addons)
    if not addons:
        return {"applied": False, "reason": "no_addons_to_sell"}
    addon_options = [{"player_addon_id": pa.id, "addon_id": pa.addon_id} for pa in addons]
    cs = dict(player.combat_state or {})
    cs["related_attribute_sell_pending"] = True
    player.combat_state = cs
    return {"applied": True, "addon_options": addon_options, "note": "related_attribute_sell_required"}


def _card_196(player, game, db, *, target_player_id=None) -> dict:
    """Get Records — Pesca 1 carta e guarda le prime 2 del mazzo boss senza pescarle."""
    from app.models.game import PlayerHandCard as _PHC196
    drew = False
    if game.action_deck_1:
        db.add(_PHC196(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
        drew = True
    elif game.action_deck_2:
        db.add(_PHC196(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
        drew = True
    peeked = (game.boss_deck or [])[:2]
    return {"applied": True, "drew_card": drew, "boss_deck_top2": peeked}


def _card_197(player, game, db, *, target_player_id=None) -> dict:
    """Create Records — Pesca 2 carte azione."""
    from app.models.game import PlayerHandCard as _PHC197
    drew = 0
    for _ in range(2):
        src = game.action_deck_1 if game.action_deck_1 else game.action_deck_2
        if src:
            db.add(_PHC197(player_id=player.id, action_card_id=src.pop(0)))
            drew += 1
    return {"applied": True, "drew": drew}


def _card_198(player, game, db, *, target_player_id=None) -> dict:
    """Einstein Recommendation — Pesca 1 AddOn dal mazzo gratis."""
    from app.models.game import PlayerAddon as _PA198
    src = game.addon_deck_1 if game.addon_deck_1 else game.addon_deck_2
    if not src:
        return {"applied": False, "reason": "no_addon_available"}
    addon_id = src.pop(0)
    db.add(_PA198(player_id=player.id, addon_id=addon_id, is_tapped=False))
    return {"applied": True, "addon_id": addon_id, "free": True}


def _card_199(player, game, db, *, target_player_id=None) -> dict:
    """Segment Builder — Scarta fino a 3 carte dalla mano e pesca lo stesso numero.

    Discards all cards the player wants to replace (up to 3 from hand), then draws equal count.
    Simplified: discards the first min(3, hand_size) cards and redraws that many.
    Client can implement selection via segment_builder_discard action with hand_card_ids.
    """
    from app.models.game import PlayerHandCard as _PHC199
    hand = list(player.hand)
    to_discard = hand[:3]
    count = len(to_discard)
    if count == 0:
        return {"applied": False, "reason": "no_cards_in_hand"}
    discarded = []
    for hc in to_discard:
        discarded.append(hc.action_card_id)
        db.delete(hc)
    game.action_discard = (game.action_discard or []) + discarded
    drew = 0
    for _ in range(count):
        src = game.action_deck_1 if game.action_deck_1 else game.action_deck_2
        if src:
            db.add(_PHC199(player_id=player.id, action_card_id=src.pop(0)))
            drew += 1
    return {"applied": True, "discarded": len(discarded), "drew": drew}


def _card_200(player, game, db, *, target_player_id=None) -> dict:
    """Publication List — 1 gruppo di giocatori pesca 1 carta, l'altro scarta 1 carta.

    Simplified: player designates a target (ally group). Target draws 1 card; all others discard 1.
    If no target given, all other players draw 1 (player is the publisher, everyone benefits).
    """
    from app.models.game import PlayerHandCard as _PHC200
    others = [p for p in game.players if p.id != player.id]
    beneficiaries = []
    losers = []
    if target_player_id:
        for p in others:
            if p.id == target_player_id:
                beneficiaries.append(p)
            else:
                losers.append(p)
    else:
        beneficiaries = others

    drew_count = 0
    for bp in beneficiaries:
        if game.action_deck_1:
            db.add(_PHC200(player_id=bp.id, action_card_id=game.action_deck_1.pop(0)))
            drew_count += 1
        elif game.action_deck_2:
            db.add(_PHC200(player_id=bp.id, action_card_id=game.action_deck_2.pop(0)))
            drew_count += 1

    discarded = 0
    for lp in losers:
        hand = list(lp.hand)
        if hand:
            hc = hand[-1]
            game.action_discard = (game.action_discard or []) + [hc.action_card_id]
            db.delete(hc)
            discarded += 1

    return {"applied": True, "beneficiaries": len(beneficiaries), "drew": drew_count, "discarded": discarded}


def _card_215(player, game, db, *, target_player_id=None) -> dict:
    """B2B Analytics — Analisi completa avversario: vedi tutte le carte, AddOn e risorse per 1 turno.

    Stores b2b_analytics_target_id + b2b_analytics_turns=1 in player.combat_state.
    turn.py draw_card (or broadcast): send full target snapshot to the player. Cleared in end_turn.
    """
    if not target_player_id:
        return {"applied": False, "reason": "target_required"}
    from app.game.engine_cards.helpers import get_target
    target = get_target(game, target_player_id)
    if not target:
        return {"applied": False, "reason": "target_not_found"}
    cs = dict(player.combat_state or {})
    cs["b2b_analytics_target_id"] = target_player_id
    cs["b2b_analytics_turns"] = 1
    player.combat_state = cs
    return {"applied": True, "b2b_analytics_target_id": target_player_id}


def _card_221(player, game, db, *, target_player_id=None) -> dict:
    """Workflow Step — La prossima carta che peschi si gioca automaticamente senza usare slot carta.

    Stores workflow_step_active=True in combat_state.
    turn.py draw_card: if flag set, auto-play drawn card and clear flag (no cards_played_this_turn increment).
    """
    cs = dict(player.combat_state or {})
    cs["workflow_step_active"] = True
    player.combat_state = cs
    return {"applied": True, "workflow_step_active": True}


def _card_223(player, game, db, *, target_player_id=None) -> dict:
    """App Home — +1L per ogni addon che possiedi."""
    addon_count = len(list(player.addons))
    player.licenze += addon_count
    return {"applied": True, "licenze_gained": addon_count, "addon_count": addon_count}


def _card_226(player, game, db, *, target_player_id=None) -> dict:
    """Shortcut — Salta la fase di pesca e ottieni 2 azioni extra (slots carta) questo turno.

    Stores shortcut_extra_plays=2. turn.py play_card: when checking max cards, add shortcut_extra_plays.
    Cleared in end_turn.
    """
    cs = dict(player.combat_state or {})
    cs["shortcut_extra_plays"] = cs.get("shortcut_extra_plays", 0) + 2
    player.combat_state = cs
    return {"applied": True, "shortcut_extra_plays": cs["shortcut_extra_plays"]}


def _card_227(player, game, db, *, target_player_id=None) -> dict:
    """Anypoint Visualizer — Tutti i giocatori giocano a carte scoperte per 1 turno.

    Sets anypoint_visualizer_active=True on every player's combat_state.
    _send_hand_state in turn.py broadcasts each player's hand to all when flag is set.
    Cleared at end_turn for each player.
    """
    for p in game.players:
        cs = dict(p.combat_state or {})
        cs["anypoint_visualizer_active"] = True
        p.combat_state = cs
    return {"applied": True, "anypoint_visualizer_active": True, "players_affected": len(list(game.players))}


def _card_232(player, game, db, *, target_player_id=None) -> dict:
    """Mule Message — Mostra 1 carta all'avversario (rivela mano) + pesca 1 nuova carta.

    Sets hand_revealed_this_turn=True (broadcast hook). Draws 1 card.
    """
    from app.models.game import PlayerHandCard as _PHC232
    cs = dict(player.combat_state or {})
    cs["hand_revealed_this_turn"] = True
    player.combat_state = cs
    drew = False
    if game.action_deck_1:
        db.add(_PHC232(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
        drew = True
    elif game.action_deck_2:
        db.add(_PHC232(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
        drew = True
    return {"applied": True, "hand_revealed": True, "drew_card": drew}


def _card_234(player, game, db, *, target_player_id=None) -> dict:
    """Integration Pattern — La 2a carta giocata questo turno ha +1 a qualsiasi valore numerico.

    Stores integration_pattern_boost=True. turn.py play_card: if this is the 2nd card
    (cards_played_this_turn == 2 after increment) and flag set, +1L as proxy boost. Then clear flag.
    """
    cs = dict(player.combat_state or {})
    cs["integration_pattern_boost"] = True
    player.combat_state = cs
    return {"applied": True, "integration_pattern_boost": True}


def _card_238(player, game, db, *, target_player_id=None) -> dict:
    """Recipe — Guadagna 5 Licenze."""
    player.licenze += 5
    return {"applied": True, "licenze_gained": 5}


def _card_239(player, game, db, *, target_player_id=None) -> dict:
    """SFTP Connector — Scarta 2 carte dalla mano, pesca 3."""
    from app.models.game import PlayerHandCard as _PHC239
    hand = list(player.hand)
    if len(hand) < 2:
        return {"applied": False, "reason": "need_at_least_2_cards"}
    discarded = []
    for hc in hand[-2:]:
        game.action_discard = (game.action_discard or []) + [hc.action_card_id]
        db.delete(hc)
        discarded.append(hc.action_card_id)
    drawn = []
    for deck in (game.action_deck_1, game.action_deck_2) * 3:
        if len(drawn) >= 3:
            break
        if deck:
            drawn.append(deck.pop(0))
    for card_id in drawn:
        db.add(_PHC239(player_id=player.id, action_card_id=card_id))
    return {"applied": True, "discarded": len(discarded), "drawn": len(drawn)}


def _card_242(player, game, db, *, target_player_id=None) -> dict:
    """App Builder — Se giochi 2 carte dello stesso tipo questo turno, pesca 1 carta bonus.

    Stores app_builder_active=True. turn.py play_card: tracks types with app_builder_type_counts dict;
    when any type reaches count=2, draw 1 card and clear flag.
    """
    cs = dict(player.combat_state or {})
    cs["app_builder_active"] = True
    cs.setdefault("app_builder_type_counts", {})
    player.combat_state = cs
    return {"applied": True, "app_builder_active": True}


def _card_243(player, game, db, *, target_player_id=None) -> dict:
    """Einstein GPT — Pesca 1 carta dagli scarti e giocala immediatamente senza usare lo slot carta.

    Draws 1 card from action_discard to hand. Sets einstein_gpt_free_play=True so the
    next card played this turn does not increment cards_played_this_turn.
    """
    from app.models.game import PlayerHandCard as _PHC243
    discard = list(game.action_discard or [])
    if not discard:
        return {"applied": False, "reason": "empty_discard"}
    card_id = discard.pop(-1)
    game.action_discard = discard
    db.add(_PHC243(player_id=player.id, action_card_id=card_id))
    cs = dict(player.combat_state or {})
    cs["einstein_gpt_free_play"] = True
    player.combat_state = cs
    return {"applied": True, "recovered_card_id": card_id, "free_play_granted": True}


def _card_245(player, game, db, *, target_player_id=None) -> dict:
    """Agent Skill — Applica l'abilità passiva del personaggio una seconda volta questo turno.

    Simplified: grants +2L (proxy for a passive ability re-trigger).
    TODO: trigger actual passive_ability(player, game, db) when that system exists.
    """
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    player.licenze += 2
    return {"applied": True, "licenze_gained": 2, "note": "passive_ability_proxy"}


def _card_247(player, game, db, *, target_player_id=None) -> dict:
    """Agent Action Plan — Guarda top 3 carte: tieni 1, 1 in cima al mazzo, 1 scartata.

    Auto-picks: keep first, requeue second, discard third.
    """
    from app.models.game import PlayerHandCard as _PHC247
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    deck = list(game.action_deck_1 or []) or list(game.action_deck_2 or [])
    taken = []
    while len(taken) < 3 and game.action_deck_1:
        taken.append(game.action_deck_1.pop(0))
    if len(taken) < 3 and game.action_deck_2:
        while len(taken) < 3 and game.action_deck_2:
            taken.append(game.action_deck_2.pop(0))
    if not taken:
        return {"applied": False, "reason": "empty_decks"}
    # Keep first → add to hand
    db.add(_PHC247(player_id=player.id, action_card_id=taken[0]))
    # Requeue second → back on top of deck_1
    if len(taken) >= 2:
        game.action_deck_1 = [taken[1]] + list(game.action_deck_1 or [])
    # Discard third
    if len(taken) >= 3:
        game.action_discard = (game.action_discard or []) + [taken[2]]
    return {"applied": True, "kept": taken[0], "requeued": taken[1] if len(taken) >= 2 else None, "discarded": taken[2] if len(taken) >= 3 else None}


def _card_248(player, game, db, *, target_player_id=None) -> dict:
    """Pipeline Promotion — Sposta la top card del mazzo boss in fondo (eviti il prossimo boss)."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    if game.boss_deck and len(game.boss_deck) > 1:
        top = game.boss_deck.pop(0)
        game.boss_deck = list(game.boss_deck) + [top]
        return {"applied": True, "deferred_boss_id": top}
    return {"applied": False, "reason": "boss_deck_too_small"}


def _card_249(player, game, db, *, target_player_id=None) -> dict:
    """Work Item — Traccia il lavoro: a fine turno recuperi 1 carta tra quelle giocate.

    Stores work_item_active=True. turn.py end_turn: if flag set and action_discard not empty,
    move last discard card back to player's hand.
    """
    cs = dict(player.combat_state or {})
    cs["work_item_active"] = True
    player.combat_state = cs
    return {"applied": True, "work_item_active": True}


def _card_250(player, game, db, *, target_player_id=None) -> dict:
    """Pipeline Stage — Muovi 1 carta dagli scarti in cima al mazzo azione."""
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    discard = list(game.action_discard or [])
    if not discard:
        return {"applied": False, "reason": "empty_discard"}
    card_id = discard.pop(-1)
    game.action_discard = discard
    game.action_deck_1 = [card_id] + list(game.action_deck_1 or [])
    return {"applied": True, "card_moved_to_top": card_id}


def _card_263(player, game, db, *, target_player_id=None) -> dict:
    """Architect Guild — Tutti i giocatori Architecture pescano 1; tu peschi 2."""
    from app.models.game import PlayerHandCard as _PHC263
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    arch_roles = {"architect", "Architect", "Solution Architect", "Technical Architect"}
    drew_self = 0
    drew_others = 0
    for gp in game.players:
        is_arch = (gp.role or "") in arch_roles
        n = 2 if gp.id == player.id else (1 if is_arch else 0)
        for _ in range(n):
            if game.action_deck_1:
                db.add(_PHC263(player_id=gp.id, action_card_id=game.action_deck_1.pop(0)))
            elif game.action_deck_2:
                db.add(_PHC263(player_id=gp.id, action_card_id=game.action_deck_2.pop(0)))
            if gp.id == player.id:
                drew_self += 1
            else:
                drew_others += 1
    return {"applied": True, "drew_self": drew_self, "drew_others": drew_others}


def _card_264(player, game, db, *, target_player_id=None) -> dict:
    """Trailhead Playground — Pesca 3 carte, tienine 1, le altre tornano mescolate.

    Auto-pick: keep first, return the other two to deck shuffled.
    """
    from app.models.game import PlayerHandCard as _PHC264
    from app.game import engine as _eng264
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    taken = []
    for _ in range(3):
        if game.action_deck_1:
            taken.append(game.action_deck_1.pop(0))
        elif game.action_deck_2:
            taken.append(game.action_deck_2.pop(0))
    if not taken:
        return {"applied": False, "reason": "empty_decks"}
    # Keep first → hand; shuffle rest back into deck_1
    db.add(_PHC264(player_id=player.id, action_card_id=taken[0]))
    if len(taken) > 1:
        remaining = taken[1:]
        game.action_deck_1 = _eng264.shuffle_deck(remaining + list(game.action_deck_1 or []))
    return {"applied": True, "kept_card_id": taken[0], "returned": len(taken) - 1}


def _card_265(player, game, db, *, target_player_id=None) -> dict:
    """Trailmix — Scegli 1 carta per tipo (offensiva/difensiva/economica) dagli ultimi 9 scarti.

    Auto-pick: finds first card of each type from discard tail; adds to hand.
    """
    from app.models.game import PlayerHandCard as _PHC265
    from app.models.card import ActionCard as _AC265
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    discard = list(game.action_discard or [])
    last9 = discard[-9:] if len(discard) >= 9 else discard[:]
    targets = {"Offensiva": None, "Difensiva": None, "Economica": None}
    for cid in reversed(last9):
        c = db.get(_AC265, cid)
        if c and c.card_type in targets and targets[c.card_type] is None:
            targets[c.card_type] = cid
    picked = [cid for cid in targets.values() if cid is not None]
    for cid in picked:
        discard.remove(cid)
        db.add(_PHC265(player_id=player.id, action_card_id=cid))
    game.action_discard = discard
    return {"applied": True, "picked": picked, "count": len(picked)}


def _card_266(player, game, db, *, target_player_id=None) -> dict:
    """Salesforce Ben — Pesca 2 carte + guarda prossima carta del mazzo boss."""
    from app.models.game import PlayerHandCard as _PHC266
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    drew = 0
    for _ in range(2):
        if game.action_deck_1:
            db.add(_PHC266(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            drew += 1
        elif game.action_deck_2:
            db.add(_PHC266(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
            drew += 1
    boss_peek = (game.boss_deck or [])[:1]
    return {"applied": True, "drew_cards": drew, "boss_deck_top1": boss_peek}


def _card_267(player, game, db, *, target_player_id=None) -> dict:
    """Buyer Relationship Map — Guarda le carte in mano a un avversario (snapshot privato)."""
    from .helpers import get_target
    target = get_target(game, player, target_player_id)
    if not target:
        return {"applied": False, "reason": "no_target"}
    hand_ids = [hc.action_card_id for hc in target.hand]
    return {"applied": True, "target_player_id": target.id, "hand_card_ids": hand_ids}


def _card_269(player, game, db, *, target_player_id=None) -> dict:
    """Trailhead GO — Il limite di carte giocabili questo turno diventa 4 (inclusa questa).

    Stores trailhead_go_max_cards=4 in combat_state.
    turn.py uses it to override max_cards if higher than current limit.
    Cleared in end_turn.
    """
    cs = dict(player.combat_state or {})
    cs["trailhead_go_max_cards"] = 4
    player.combat_state = cs
    return {"applied": True, "trailhead_go_max_cards": 4}


def _card_270(player, game, db, *, target_player_id=None) -> dict:
    """Success Community — Un avversario ti dà 1 carta dalla sua mano (a sua scelta).

    Simplified: takes last card from target's hand (target "chooses" to give cheapest / last).
    Requires target_player_id.
    """
    if not target_player_id:
        return {"applied": False, "reason": "target_required"}
    from app.game.engine_cards.helpers import get_target
    from app.models.game import PlayerHandCard as _PHC270
    target = get_target(game, target_player_id)
    if not target:
        return {"applied": False, "reason": "target_not_found"}
    hand = list(target.hand)
    if not hand:
        return {"applied": False, "reason": "target_has_no_cards"}
    given = hand[-1]
    card_id = given.action_card_id
    db.delete(given)
    db.add(_PHC270(player_id=player.id, action_card_id=card_id))
    return {"applied": True, "received_card_id": card_id}


def _card_282(player, game, db, *, target_player_id=None) -> dict:
    """IdeaExchange Winner (Leggendaria) — +5L, pesca 2 carte, boss -2HP."""
    from app.models.game import PlayerHandCard as _PHC282
    player.licenze += 5
    drew = 0
    for _ in range(2):
        if game.action_deck_1:
            db.add(_PHC282(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            drew += 1
        elif game.action_deck_2:
            db.add(_PHC282(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
            drew += 1
    boss_damage = 0
    if player.is_in_combat:
        player.current_boss_hp = max(0, player.current_boss_hp - 2)
        boss_damage = 2
    return {"applied": True, "licenze_gained": 5, "drew": drew, "boss_damage": boss_damage}


def _card_283(player, game, db, *, target_player_id=None) -> dict:
    """Queueable Job (Leggendaria) — Questo turno puoi giocare fino a 5 carte invece di 2.

    Stores queueable_job_max_cards=5. turn.py raises max_cards to 5 if higher.
    Cleared in end_turn.
    """
    cs = dict(player.combat_state or {})
    cs["queueable_job_max_cards"] = 5
    player.combat_state = cs
    return {"applied": True, "queueable_job_max_cards": 5}


def _card_284(player, game, db, *, target_player_id=None) -> dict:
    """Bring Your Own Model (Leggendaria) — In combattimento: +2 al prossimo tiro; altrimenti +4L."""
    if player.is_in_combat:
        cs = dict(player.combat_state or {})
        cs["byom_roll_bonus"] = cs.get("byom_roll_bonus", 0) + 2
        player.combat_state = cs
        return {"applied": True, "effect": "roll_bonus_2"}
    player.licenze += 4
    return {"applied": True, "licenze_gained": 4}


def _card_287(player, game, db, *, target_player_id=None) -> dict:
    """404 Not Found — Per 1 turno blocca carte in entrata e in uscita verso di te."""
    cs = dict(player.combat_state or {})
    cs["not_found_active"] = True
    cs["not_found_until_turn"] = game.turn_number + 1
    player.combat_state = cs
    return {"applied": True, "effect": "block_all_card_targeting_until_turn", "until": game.turn_number + 1}


def _card_289(player, game, db, *, target_player_id=None) -> dict:
    """Stack Trace — Recupera fino a 3 carte dallo scarti."""
    from app.models.game import PlayerHandCard as _PHC289
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    discard = list(game.action_discard or [])
    recovered = discard[-3:] if len(discard) >= 3 else discard
    for card_id in recovered:
        db.add(_PHC289(player_id=player.id, action_card_id=card_id))
    for card_id in recovered:
        game.action_discard.remove(card_id)
    return {"applied": True, "recovered": len(recovered)}


def _card_291(player, game, db, *, target_player_id=None) -> dict:
    """Copy/Paste — +1L e pesca 1 carta."""
    from app.models.game import PlayerHandCard as _PHC291
    player.licenze += 1
    drew = 0
    if game.action_deck_1:
        db.add(_PHC291(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
        drew = 1
    elif game.action_deck_2:
        db.add(_PHC291(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
        drew = 1
    return {"applied": True, "licenze_gained": 1, "drew": drew}


def _card_299(player, game, db, *, target_player_id=None) -> dict:
    """The Trailbraizer (Leggendaria) — Pesca 3, +5L, HP max, rimuovi flag negativi."""
    from app.models.game import PlayerHandCard as _PHC299
    if player.is_in_combat:
        return {"applied": False, "reason": "in_combat"}
    drew = 0
    for _ in range(3):
        if game.action_deck_1:
            db.add(_PHC299(player_id=player.id, action_card_id=game.action_deck_1.pop(0)))
            drew += 1
        elif game.action_deck_2:
            db.add(_PHC299(player_id=player.id, action_card_id=game.action_deck_2.pop(0)))
            drew += 1
    player.licenze += 5
    player.hp = player.max_hp
    # Clear negative combat_state flags
    cs = dict(player.combat_state or {})
    for neg_flag in ("stunned", "locked_out", "sandbox_lock_turns", "fork_in_road_used",
                     "not_found_active", "null_pointer_active"):
        cs.pop(neg_flag, None)
    player.combat_state = cs
    return {"applied": True, "drew": drew, "licenze_gained": 5, "hp_restored": True, "flags_cleared": True}


UTILITA: dict = {
    31:  _card_31,
    32:  _card_32,
    33:  _card_33,
    34:  _card_34,
    35:  _card_35,
    36:  _card_36,
    37:  _card_37,
    63:  _card_63,
    64:  _card_64,
    65:  _card_65,
    66:  _card_66,
    67:  _card_67,
    68:  _card_68,
    69:  _card_69,
    80:  _card_80,
    106: _card_106,
    107: _card_107,
    108: _card_108,
    109: _card_109,
    110: _card_110,
    137: _card_137,
    138: _card_138,
    172: _card_172,
    173: _card_173,
    174: _card_174,
    175: _card_175,
    176: _card_176,
    177: _card_177,
    178: _card_178,
    179: _card_179,
    180: _card_180,
    196: _card_196,
    197: _card_197,
    198: _card_198,
    199: _card_199,
    200: _card_200,
    215: _card_215,
    221: _card_221,
    223: _card_223,
    226: _card_226,
    227: _card_227,
    232: _card_232,
    234: _card_234,
    263: _card_263,
    264: _card_264,
    265: _card_265,
    266: _card_266,
    267: _card_267,
    269: _card_269,
    270: _card_270,
    238: _card_238,
    239: _card_239,
    242: _card_242,
    243: _card_243,
    245: _card_245,
    247: _card_247,
    248: _card_248,
    249: _card_249,
    250: _card_250,
    282: _card_282,
    283: _card_283,
    284: _card_284,
    287: _card_287,
    289: _card_289,
    291: _card_291,
    299: _card_299,
}
