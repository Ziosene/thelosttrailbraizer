"""
Test per le carte Interferenza.

Copre: logica engine, target resolution, stati pending_reaction/pending_choice,
effetti su licenze/hp, immunità.
"""
import pytest
from app.game.engine_cards import apply_action_card_effect
from app.models.card import ActionCard
from tests.engine_cards.conftest import make_game, make_player, make_action_card


# ─── Helper ───────────────────────────────────────────────────────────────────

def _get_card(db, number: int) -> ActionCard:
    return db.query(ActionCard).filter_by(number=number).first()


# ─── Carta 115 — HTTP Connector ───────────────────────────────────────────────

class TestCard115HttpConnector:
    def test_2player_returns_pending_reaction(self, db, game2):
        """In 2 giocatori, auto-seleziona il target e ritorna pending_reaction."""
        game, caster, target = game2
        card = _get_card(db, 115)
        if card is None:
            pytest.skip("Carta 115 non presente nel DB (serve seed)")

        result = apply_action_card_effect(card, caster, game, db)
        assert result["status"] == "pending_reaction"
        assert result["reaction_type"] == "comply_or_refuse"
        assert result["target_player_id"] == target.id
        assert result["comply_cost"] == 1
        assert result["refuse_cost"] == 2

    def test_3player_no_target_fails(self, db, game3):
        """In 3 giocatori senza target esplicito → no_target."""
        game, caster, *_ = game3
        card = _get_card(db, 115)
        if card is None:
            pytest.skip("Carta 115 non presente nel DB")

        result = apply_action_card_effect(card, caster, game, db)
        assert result["applied"] is False
        assert result["reason"] == "no_target"

    def test_3player_explicit_target_works(self, db, game3):
        """In 3 giocatori con target esplicito → pending_reaction."""
        game, caster, p2, p3 = game3
        card = _get_card(db, 115)
        if card is None:
            pytest.skip("Carta 115 non presente nel DB")

        result = apply_action_card_effect(card, caster, game, db, target_player_id=p2.id)
        assert result["status"] == "pending_reaction"
        assert result["target_player_id"] == p2.id

    def test_immune_target_blocks_effect(self, db, game2):
        """Target con licenze_theft_immune → blocked."""
        game, caster, target = game2
        card = _get_card(db, 115)
        if card is None:
            pytest.skip("Carta 115 non presente nel DB")

        target.combat_state = {"licenze_theft_immune": True}
        db.flush()

        result = apply_action_card_effect(card, caster, game, db)
        assert result["applied"] is False
        assert result["reason"] == "target_immune"


# ─── Carta 116 — API Rate Limiting ───────────────────────────────────────────

class TestCard116ApiRateLimiting:
    def test_sets_rate_limit_on_target(self, db, game2):
        """Imposta api_rate_limit_max_cards=1 nel combat_state del target."""
        game, caster, target = game2
        card = _get_card(db, 116)
        if card is None:
            pytest.skip("Carta 116 non presente nel DB")

        result = apply_action_card_effect(card, caster, game, db)
        assert result["applied"] is True
        # L'engine modifica l'oggetto in-memory; flush per persistere, poi verifica
        db.flush()
        assert (target.combat_state or {}).get("api_rate_limit_max_cards") == 1

    def test_no_target_in_3player(self, db, game3):
        """In 3 giocatori senza target → no_target."""
        game, caster, *_ = game3
        card = _get_card(db, 116)
        if card is None:
            pytest.skip("Carta 116 non presente nel DB")

        result = apply_action_card_effect(card, caster, game, db)
        assert result["applied"] is False
        assert result["reason"] == "no_target"


# ─── Carte generiche — pattern comuni ────────────────────────────────────────

class TestTargetedCards:
    """
    Verifica che le carte interferenza con target non crashino
    e ritornino applied=False con reason='no_target' in 3+ giocatori
    senza target esplicito.
    """
    TARGETED_INTERFERENCE_CARD_NUMBERS = [
        113, 114, 115, 116, 117, 118, 119, 120,
    ]

    @pytest.mark.parametrize("card_number", TARGETED_INTERFERENCE_CARD_NUMBERS)
    def test_no_target_in_3player_never_crashes(self, db, game3, card_number):
        """Nessuna carta interferenza deve crashare in 3 giocatori senza target."""
        game, caster, *_ = game3
        card = _get_card(db, card_number)
        if card is None:
            pytest.skip(f"Carta {card_number} non nel DB")

        # Non deve sollevare eccezioni
        result = apply_action_card_effect(card, caster, game, db)
        assert isinstance(result, dict)
        # Deve sempre ritornare 'applied' o 'status'
        assert "applied" in result or "status" in result
