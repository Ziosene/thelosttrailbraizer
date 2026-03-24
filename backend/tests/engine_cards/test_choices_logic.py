"""
Test per app.game.engine_cards.choices_logic — resolver pure per pending_choice.

Ogni test:
- Prepara uno stato game/player/db realistico
- Chiama il resolver direttamente (nessun WS, nessun mock)
- Verifica che il DB sia mutato correttamente
- Verifica che il risultato contenga {"ok": True}

Test di errore:
- Verifica che l'input invalido restituisca {"error": ...} senza crashare
"""
import pytest
from app.models.game import GamePlayer, PlayerHandCard, PlayerAddon, GameSession
from app.models.card import ActionCard, AddonCard

from app.game.engine_cards.choices_logic import (
    resolve_discard_specific_cards,
    resolve_reorder_boss_deck,
    resolve_reorder_action_deck,
    resolve_keep_one_from_drawn,
    resolve_recover_from_discard,
    resolve_return_card_to_deck_top,
    resolve_choose_cards_to_keep,
    resolve_choose_addon_to_return,
    resolve_delete_target_addon,
    resolve_choose_boss_to_front,
    resolve_sell_addon_for_licenze,
)
from tests.engine_cards.conftest import make_game, make_player, make_action_card


# ── Helpers ───────────────────────────────────────────────────────────────────

def _add_cards_to_hand(db, player, n: int) -> list[PlayerHandCard]:
    hcs = []
    for _ in range(n):
        card = make_action_card(db)
        hc = PlayerHandCard(player_id=player.id, action_card_id=card.id)
        db.add(hc)
        hcs.append(hc)
    db.flush()
    db.refresh(player)
    return hcs


def _add_addon(db, player, *, number_offset: int = 0) -> PlayerAddon:
    num = 7000 + player.id * 10 + number_offset
    addon = AddonCard(
        id=num, number=num,
        name=f"Test Addon {num}",
        addon_type="Passivo", effect="X",
        cost=5, rarity="Comune",
    )
    db.add(addon)
    db.flush()
    pa = PlayerAddon(player_id=player.id, addon_id=addon.id)
    db.add(pa)
    db.flush()
    db.refresh(player)
    return pa


# ── resolve_discard_specific_cards ────────────────────────────────────────────

class TestResolveDiscardSpecificCards:
    def test_happy_path(self, db, game2):
        game, p1, p2 = game2
        hcs = _add_cards_to_hand(db, p1, 3)
        ids_to_discard = [hcs[0].id, hcs[1].id]

        result = resolve_discard_specific_cards(game, p1, db, ids_to_discard, count=2)

        assert result["ok"] is True
        assert len(game.action_discard) == 2
        db.refresh(p1)
        assert len(list(p1.hand)) == 1  # only hcs[2] remains

    def test_wrong_count(self, db, game2):
        game, p1, _ = game2
        hcs = _add_cards_to_hand(db, p1, 3)

        result = resolve_discard_specific_cards(game, p1, db, [hcs[0].id], count=2)

        assert "error" in result

    def test_invalid_card_id(self, db, game2):
        game, p1, _ = game2

        result = resolve_discard_specific_cards(game, p1, db, [99999, 99998], count=2)

        assert "error" in result

    def test_card_belonging_to_other_player(self, db, game2):
        game, p1, p2 = game2
        hcs_p2 = _add_cards_to_hand(db, p2, 2)

        result = resolve_discard_specific_cards(game, p1, db, [hcs_p2[0].id, hcs_p2[1].id], count=2)

        assert "error" in result


# ── resolve_reorder_boss_deck ─────────────────────────────────────────────────

class TestResolveReorderBossDeck:
    def test_happy_path(self, db, game2):
        game, p1, _ = game2
        game.boss_deck_1 = [10, 20, 30, 40]
        db.flush()

        result = resolve_reorder_boss_deck(game, p1, db, [30, 10, 20], [10, 20, 30])

        assert result["ok"] is True
        assert game.boss_deck_1[:3] == [30, 10, 20]
        assert game.boss_deck_1[3] == 40  # rest preserved

    def test_wrong_cards(self, db, game2):
        game, p1, _ = game2
        game.boss_deck_1 = [10, 20, 30]

        result = resolve_reorder_boss_deck(game, p1, db, [10, 99], [10, 20])

        assert "error" in result


# ── resolve_reorder_action_deck ───────────────────────────────────────────────

class TestResolveReorderActionDeck:
    def test_happy_path(self, db, game2):
        game, p1, _ = game2
        game.action_deck_1 = [1, 2, 3, 4, 5]
        db.flush()

        result = resolve_reorder_action_deck(game, p1, db, [3, 1, 2], [1, 2, 3])

        assert result["ok"] is True
        assert game.action_deck_1[:3] == [3, 1, 2]
        assert game.action_deck_1[3:] == [4, 5]

    def test_wrong_cards(self, db, game2):
        game, p1, _ = game2

        result = resolve_reorder_action_deck(game, p1, db, [1, 99], [1, 2])

        assert "error" in result


# ── resolve_keep_one_from_drawn ───────────────────────────────────────────────

class TestResolveKeepOneFromDrawn:
    def test_happy_path(self, db, game2):
        game, p1, _ = game2
        hcs = _add_cards_to_hand(db, p1, 3)
        drawn_ids = [hcs[0].action_card_id, hcs[1].action_card_id, hcs[2].action_card_id]
        keep_id = drawn_ids[1]

        result = resolve_keep_one_from_drawn(game, p1, db, keep_id, drawn_ids)

        assert result["ok"] is True
        assert result["kept"] == keep_id
        db.refresh(p1)
        # Only the kept card remains in hand
        hand_card_ids = [h.action_card_id for h in p1.hand]
        assert keep_id in hand_card_ids
        # Returned cards are at top of deck
        assert drawn_ids[0] in game.action_deck_1
        assert drawn_ids[2] in game.action_deck_1

    def test_keep_card_not_in_drawn(self, db, game2):
        game, p1, _ = game2

        result = resolve_keep_one_from_drawn(game, p1, db, keep_id=9999, drawn=[1, 2, 3])

        assert "error" in result


# ── resolve_recover_from_discard ──────────────────────────────────────────────

class TestResolveRecoverFromDiscard:
    def test_happy_path(self, db, game2):
        game, p1, _ = game2
        card = make_action_card(db)
        game.action_discard = [card.id]
        db.flush()

        result = resolve_recover_from_discard(game, p1, db, [card.id], count=1)

        assert result["ok"] is True
        assert card.id not in game.action_discard
        db.refresh(p1)
        assert any(h.action_card_id == card.id for h in p1.hand)

    def test_wrong_count(self, db, game2):
        game, p1, _ = game2
        card = make_action_card(db)
        game.action_discard = [card.id]

        result = resolve_recover_from_discard(game, p1, db, [card.id], count=2)

        assert "error" in result

    def test_card_not_in_discard(self, db, game2):
        game, p1, _ = game2
        game.action_discard = []

        result = resolve_recover_from_discard(game, p1, db, [9999], count=1)

        assert "error" in result


# ── resolve_return_card_to_deck_top ───────────────────────────────────────────

class TestResolveReturnCardToDeckTop:
    def test_happy_path(self, db, game2):
        game, p1, _ = game2
        hcs = _add_cards_to_hand(db, p1, 1)
        hc = hcs[0]

        result = resolve_return_card_to_deck_top(game, p1, db, hc.id)

        assert result["ok"] is True
        assert result["returned_card_id"] == hc.action_card_id
        assert game.action_deck_1[0] == hc.action_card_id
        db.refresh(p1)
        assert all(h.id != hc.id for h in p1.hand)

    def test_invalid_card(self, db, game2):
        game, p1, _ = game2

        result = resolve_return_card_to_deck_top(game, p1, db, 99999)

        assert "error" in result

    def test_other_player_card(self, db, game2):
        game, p1, p2 = game2
        hcs = _add_cards_to_hand(db, p2, 1)

        result = resolve_return_card_to_deck_top(game, p1, db, hcs[0].id)

        assert "error" in result


# ── resolve_choose_cards_to_keep ──────────────────────────────────────────────

class TestResolveChooseCardsToKeep:
    def test_happy_path_keep_two(self, db, game2):
        game, p1, _ = game2
        hcs = _add_cards_to_hand(db, p1, 4)
        drawn_action_ids = [h.action_card_id for h in hcs]
        keep_hc_ids = [hcs[0].id, hcs[1].id]

        result = resolve_choose_cards_to_keep(game, p1, db, keep_hc_ids, drawn_action_ids, max_keep=2)

        assert result["ok"] is True
        assert len(result["kept"]) == 2
        assert len(result["returned_to_deck"]) == 2
        # Discarded cards went back to deck
        for cid in result["returned_to_deck"]:
            assert cid in game.action_deck_1

    def test_too_many_kept(self, db, game2):
        game, p1, _ = game2
        hcs = _add_cards_to_hand(db, p1, 3)

        result = resolve_choose_cards_to_keep(game, p1, db, [h.id for h in hcs], [h.action_card_id for h in hcs], max_keep=2)

        assert "error" in result

    def test_invalid_card_id(self, db, game2):
        game, p1, _ = game2
        hcs = _add_cards_to_hand(db, p1, 1)
        drawn = [hcs[0].action_card_id]

        result = resolve_choose_cards_to_keep(game, p1, db, [99999], drawn, max_keep=2)

        assert "error" in result


# ── resolve_choose_addon_to_return ────────────────────────────────────────────

class TestResolveChooseAddonToReturn:
    def test_happy_path(self, db, game2):
        game, p1, _ = game2
        pa = _add_addon(db, p1)
        licenze_before = p1.licenze

        result = resolve_choose_addon_to_return(game, p1, db, pa.id, licenze_gained=8)

        assert result["ok"] is True
        assert result["licenze_gained"] == 8
        assert p1.licenze == licenze_before + 8
        assert pa.addon_id in game.addon_deck_1
        assert db.get(type(pa), pa.id) is None

    def test_addon_not_owned(self, db, game2):
        game, p1, p2 = game2
        pa = _add_addon(db, p2)

        result = resolve_choose_addon_to_return(game, p1, db, pa.id, licenze_gained=8)

        assert "error" in result

    def test_invalid_id(self, db, game2):
        game, p1, _ = game2

        result = resolve_choose_addon_to_return(game, p1, db, 99999, licenze_gained=8)

        assert "error" in result


# ── resolve_delete_target_addon ───────────────────────────────────────────────

class TestResolveDeleteTargetAddon:
    def test_happy_path(self, db, game2):
        game, p1, p2 = game2
        pa = _add_addon(db, p2)
        deck_before = len(game.addon_deck_1 or [])
        graveyard_before = len(game.addon_graveyard or [])

        result = resolve_delete_target_addon(game, p1, db, pa.id, p2.id)

        assert result["ok"] is True
        assert result["deleted_addon_id"] == pa.addon_id
        assert len(game.addon_deck_1) == deck_before + 1
        assert len(game.addon_graveyard) == graveyard_before + 1
        assert db.get(type(pa), pa.id) is None

    def test_addon_belongs_to_caster_not_target(self, db, game2):
        game, p1, p2 = game2
        pa = _add_addon(db, p1)

        result = resolve_delete_target_addon(game, p1, db, pa.id, p2.id)

        assert "error" in result

    def test_invalid_addon_id(self, db, game2):
        game, p1, p2 = game2

        result = resolve_delete_target_addon(game, p1, db, 99999, p2.id)

        assert "error" in result


# ── resolve_choose_boss_to_front ──────────────────────────────────────────────

class TestResolveChooseBossToFront:
    def test_happy_path_moves_chosen_to_front(self, db, game2):
        game, p1, _ = game2
        game.boss_deck_1 = [10, 20, 30, 40, 50]
        db.flush()
        choices = [10, 20, 30]  # top 3 shown to player

        result = resolve_choose_boss_to_front(game, p1, db, chosen_boss_id=20, choices=choices)

        assert result["ok"] is True
        assert result["chosen_boss_id"] == 20
        assert game.boss_deck_1[0] == 20
        # Others from choices are next, then rest of deck
        assert 10 in game.boss_deck_1[1:3]
        assert 30 in game.boss_deck_1[1:3]
        assert game.boss_deck_1[3:] == [40, 50]

    def test_uses_deck_2_when_deck_1_empty(self, db, game2):
        game, p1, _ = game2
        game.boss_deck_1 = []
        game.boss_deck_2 = [10, 20, 30]
        db.flush()

        result = resolve_choose_boss_to_front(game, p1, db, chosen_boss_id=10, choices=[10, 20, 30])

        assert result["ok"] is True
        assert game.boss_deck_2[0] == 10

    def test_invalid_boss_id(self, db, game2):
        game, p1, _ = game2
        game.boss_deck_1 = [10, 20, 30]

        result = resolve_choose_boss_to_front(game, p1, db, chosen_boss_id=99, choices=[10, 20, 30])

        assert "error" in result

    def test_empty_deck(self, db, game2):
        game, p1, _ = game2
        game.boss_deck_1 = []
        game.boss_deck_2 = []

        result = resolve_choose_boss_to_front(game, p1, db, chosen_boss_id=10, choices=[10])

        assert "error" in result


# ── resolve_sell_addon_for_licenze ────────────────────────────────────────────

class TestResolveSellAddonForLicenze:
    def test_happy_path(self, db, game2):
        game, p1, _ = game2
        pa = _add_addon(db, p1)
        # Set addon cost manually via db
        from app.models.card import AddonCard
        addon = db.get(AddonCard, pa.addon_id)
        addon.cost = 10
        db.flush()
        licenze_before = p1.licenze
        hand_before = len(list(p1.hand))

        result = resolve_sell_addon_for_licenze(game, p1, db, pa.id)

        assert result["ok"] is True
        assert result["licenze_gained"] == 5  # floor(10/2)
        assert p1.licenze == licenze_before + 5
        assert pa.addon_id in game.addon_deck_1
        assert db.get(type(pa), pa.id) is None
        db.refresh(p1)
        assert len(list(p1.hand)) == hand_before + 1  # drew 1 card

    def test_addon_not_owned(self, db, game2):
        game, p1, p2 = game2
        pa = _add_addon(db, p2)

        result = resolve_sell_addon_for_licenze(game, p1, db, pa.id)

        assert "error" in result

    def test_invalid_id(self, db, game2):
        game, p1, _ = game2

        result = resolve_sell_addon_for_licenze(game, p1, db, 99999)

        assert "error" in result
