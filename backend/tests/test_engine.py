"""
Unit tests for the pure game engine functions.
Run with: pytest tests/test_engine.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Minimal stub so engine.py can be imported without a real DB
import types
mock_game = types.ModuleType("app.models.game")
mock_game.SENIORITY_HP = {"Junior": 1, "Experienced": 2, "Senior": 3, "Evangelist": 4}
mock_game.Seniority = type("Seniority", (), {
    "junior": "Junior", "experienced": "Experienced",
    "senior": "Senior", "evangelist": "Evangelist",
})
sys.modules.setdefault("app", types.ModuleType("app"))
sys.modules.setdefault("app.models", types.ModuleType("app.models"))
sys.modules["app.models.game"] = mock_game

from app.game.engine import (
    roll_d10,
    resolve_combat_round,
    calculate_max_hp,
    check_victory,
    shuffle_deck,
    build_action_deck,
    draw_cards,
    apply_death_penalty,
    update_elo,
    expected_score,
    CERTIFICATIONS_TO_WIN,
)


# ---------------------------------------------------------------------------
# roll_d10
# ---------------------------------------------------------------------------

def test_roll_d10_range():
    for _ in range(200):
        result = roll_d10()
        assert 1 <= result <= 10


# ---------------------------------------------------------------------------
# resolve_combat_round
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dice,threshold,expected", [
    (6, 6, "hit"),
    (10, 6, "hit"),
    (5, 6, "miss"),
    (1, 6, "miss"),
    (7, 7, "hit"),
    (6, 7, "miss"),
])
def test_resolve_combat_round(dice, threshold, expected):
    assert resolve_combat_round(dice, threshold) == expected


# ---------------------------------------------------------------------------
# calculate_max_hp
# ---------------------------------------------------------------------------

def test_calculate_max_hp():
    assert calculate_max_hp("Junior") == 1
    assert calculate_max_hp("Experienced") == 2
    assert calculate_max_hp("Senior") == 3
    assert calculate_max_hp("Evangelist") == 4


# ---------------------------------------------------------------------------
# check_victory
# ---------------------------------------------------------------------------

def test_check_victory():
    assert check_victory(CERTIFICATIONS_TO_WIN) is True
    assert check_victory(CERTIFICATIONS_TO_WIN - 1) is False
    assert check_victory(0) is False
    assert check_victory(10) is True


# ---------------------------------------------------------------------------
# shuffle_deck
# ---------------------------------------------------------------------------

def test_shuffle_deck_same_elements():
    deck = list(range(50))
    shuffled = shuffle_deck(deck)
    assert sorted(shuffled) == sorted(deck)
    assert len(shuffled) == len(deck)


def test_shuffle_deck_does_not_mutate():
    deck = [1, 2, 3]
    original = deck.copy()
    shuffle_deck(deck)
    assert deck == original


# ---------------------------------------------------------------------------
# build_action_deck
# ---------------------------------------------------------------------------

def test_build_action_deck_copies():
    by_rarity = {
        "Comune": [1, 2],
        "Non comune": [3],
        "Raro": [4],
        "Leggendario": [5],
    }
    deck = build_action_deck(by_rarity)
    from collections import Counter
    counts = Counter(deck)
    assert counts[1] == 3   # Comune × 3
    assert counts[2] == 3
    assert counts[3] == 2   # Non comune × 2
    assert counts[4] == 1   # Raro × 1
    assert counts[5] == 1   # Leggendario × 1
    assert len(deck) == 3 + 3 + 2 + 1 + 1


# ---------------------------------------------------------------------------
# draw_cards
# ---------------------------------------------------------------------------

def test_draw_cards_basic():
    deck = [1, 2, 3, 4, 5]
    drawn, new_deck, new_discard = draw_cards(deck, [], 3)
    assert drawn == [1, 2, 3]
    assert new_deck == [4, 5]
    assert new_discard == []


def test_draw_cards_reshuffle():
    deck = [1]
    discard = [10, 11, 12]
    drawn, new_deck, new_discard = draw_cards(deck, discard, 4)
    assert len(drawn) == 4
    assert 1 in drawn
    assert set(drawn) - {1} <= {10, 11, 12}


def test_draw_cards_empty():
    drawn, new_deck, new_discard = draw_cards([], [], 3)
    assert drawn == []
    assert new_deck == []
    assert new_discard == []


def test_draw_cards_does_not_mutate_inputs():
    deck = [1, 2, 3]
    discard = [9]
    draw_cards(deck, discard, 2)
    assert deck == [1, 2, 3]
    assert discard == [9]


# ---------------------------------------------------------------------------
# apply_death_penalty
# ---------------------------------------------------------------------------

def test_death_penalty_loses_one_of_each():
    result = apply_death_penalty([10, 20, 30], 5, [100, 200])
    assert len(result["hand"]) == 2
    assert result["licenze"] == 4
    assert len(result["addons"]) == 1
    assert "card" in result["lost"]
    assert result["lost"]["licenza"] == 1
    assert "addon" in result["lost"]


def test_death_penalty_empty_hand():
    result = apply_death_penalty([], 3, [100])
    assert result["hand"] == []
    assert "card" not in result["lost"]
    assert result["licenze"] == 2


def test_death_penalty_no_licenze():
    result = apply_death_penalty([1], 0, [])
    assert result["licenze"] == 0
    assert "licenza" not in result["lost"]


def test_death_penalty_player_chooses_addon():
    result = apply_death_penalty([1], 3, [100, 200], player_chooses_addon=200)
    assert 200 not in result["addons"]
    assert result["lost"]["addon"] == 200


# ---------------------------------------------------------------------------
# ELO
# ---------------------------------------------------------------------------

def test_expected_score_equal_ratings():
    assert expected_score(1000, 1000) == pytest.approx(0.5)


def test_expected_score_higher_rating():
    assert expected_score(1200, 1000) > 0.5
    assert expected_score(1000, 1200) < 0.5


def test_update_elo_winner_gains():
    ratings = [1000, 1000, 1000]
    new = update_elo(ratings, winner_index=0)
    assert new[0] > 1000
    assert new[1] < 1000
    assert new[2] < 1000


def test_update_elo_minimum_rating():
    ratings = [100, 3000]
    new = update_elo(ratings, winner_index=1)
    assert new[0] >= 100  # floor at 100


def test_update_elo_preserves_count():
    ratings = [1000, 1100, 900, 1050]
    new = update_elo(ratings, winner_index=2)
    assert len(new) == 4
