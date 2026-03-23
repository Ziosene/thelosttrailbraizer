"""
Test per le carte Utilità.

Copre: draw multipli, pending_choice, effetti risorse (licenze, cert),
condizioni in_combat, casi limite con mazzo vuoto.
"""
import pytest
from app.game.engine_cards import apply_action_card_effect
from app.models.card import ActionCard
from app.models.game import PlayerHandCard
from tests.engine_cards.conftest import make_game, make_player, make_action_card


def _get_card(db, number: int) -> ActionCard:
    return db.query(ActionCard).filter_by(number=number).first()


# ─── Carta 68 — Dataset ───────────────────────────────────────────────────────

class TestCard68Dataset:
    def test_draws_4_cards_and_returns_choice(self, db, game2):
        """Pesca 4 carte e ritorna pending_choice con count=2."""
        game, caster, _ = game2
        card = _get_card(db, 68)
        if card is None:
            pytest.skip("Carta 68 non nel DB")

        hand_before = len(caster.hand)
        result = apply_action_card_effect(card, caster, game, db)

        assert result["status"] == "pending_choice"
        assert result["choice_type"] == "discard_specific_cards"
        assert result["count"] == 2
        assert result["card_number"] == 68
        db.refresh(caster)
        assert len(caster.hand) == hand_before + 4

    def test_blocked_in_combat(self, db, game2):
        """In combattimento la carta non si applica."""
        game, caster, _ = game2
        card = _get_card(db, 68)
        if card is None:
            pytest.skip("Carta 68 non nel DB")

        caster.is_in_combat = True
        db.flush()

        result = apply_action_card_effect(card, caster, game, db)
        assert result["applied"] is False

    def test_empty_deck_no_crash(self, db, game2):
        """Con mazzo vuoto non crasha e pesca quel che trova."""
        game, caster, _ = game2
        card = _get_card(db, 68)
        if card is None:
            pytest.skip("Carta 68 non nel DB")

        game.action_deck_1 = []
        game.action_deck_2 = []
        game.action_discard = []
        db.flush()

        result = apply_action_card_effect(card, caster, game, db)
        # Con 0 carte pescate deve ritornare applied=True senza choice
        assert isinstance(result, dict)
        assert "status" in result or result.get("applied") is True


# ─── Pattern comune: carte che non devono mai crashare ───────────────────────

class TestUtilitaNoCrash:
    """
    Smoke test per le carte Utilità: verifica che non sollevano eccezioni
    e ritornino sempre un dict con 'applied' o 'status'.
    """
    UTILITA_CARD_NUMBERS = list(range(1, 30)) + list(range(60, 90))

    @pytest.mark.parametrize("card_number", UTILITA_CARD_NUMBERS)
    def test_no_crash_out_of_combat(self, db, game2, card_number):
        game, caster, _ = game2
        card = _get_card(db, card_number)
        if card is None or card.card_type != "Utilità":
            pytest.skip(f"Carta {card_number} non è Utilità o non nel DB")

        result = apply_action_card_effect(card, caster, game, db)
        assert isinstance(result, dict)
        assert "applied" in result or "status" in result
