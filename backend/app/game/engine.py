"""
Core game logic — pure functions, no DB/WebSocket dependencies.
All functions receive game state objects and return updated state or results.
"""
import random
from app.models.game import SENIORITY_HP, Seniority

# Victory condition
CERTIFICATIONS_TO_WIN = 5
# Starting resources
STARTING_LICENZE = 3
STARTING_HAND_SIZE = 4
MAX_HAND_SIZE = 10
MAX_CARDS_PER_TURN = 2
ADDON_BASE_COST = 10

# Death penalties
DEATH_LOSE_CARDS = 1
DEATH_LOSE_LICENZE = 1
DEATH_LOSE_ADDONS = 1


def roll_d10() -> int:
    return random.randint(1, 10)


def resolve_combat_round(dice_result: int, threshold: int) -> str:
    """Returns 'hit' if player hits the boss, 'miss' otherwise."""
    return "hit" if dice_result >= threshold else "miss"


def calculate_max_hp(seniority: Seniority) -> int:
    return SENIORITY_HP[seniority]


def check_victory(certificazioni: int) -> bool:
    return certificazioni >= CERTIFICATIONS_TO_WIN


def shuffle_deck(deck: list) -> list:
    shuffled = deck.copy()
    random.shuffle(shuffled)
    return shuffled


def build_action_deck(card_ids_by_rarity: dict) -> list:
    """
    Build the shared action deck with correct copy counts.
    comune=3 copies, non_comune=2, raro=1, leggendario=1
    """
    copies_map = {"Comune": 3, "Non comune": 2, "Raro": 1, "Leggendario": 1}
    deck = []
    for rarity, card_ids in card_ids_by_rarity.items():
        n = copies_map.get(rarity, 1)
        for card_id in card_ids:
            deck.extend([card_id] * n)
    return shuffle_deck(deck)


def draw_cards(deck: list, discard: list, count: int) -> tuple[list, list, list]:
    """
    Draw `count` cards from deck, reshuffling discard if needed.
    Returns (drawn_cards, new_deck, new_discard).
    """
    drawn = []
    deck = deck.copy()
    discard = discard.copy()

    for _ in range(count):
        if not deck:
            if not discard:
                break
            deck = shuffle_deck(discard)
            discard = []
        drawn.append(deck.pop(0))

    return drawn, deck, discard


def apply_death_penalty(
    hand: list,
    licenze: int,
    addons: list,
    player_chooses_addon: int | None = None,
) -> dict:
    """
    Apply death consequences:
    - lose 1 card (random from hand)
    - lose 1 Licenza
    - lose 1 AddOn (player chooses which; if not specified, random)
    Returns a dict with new values and what was lost.
    """
    lost = {}
    hand = hand.copy()
    addons = addons.copy()

    if hand:
        card = random.choice(hand)
        hand.remove(card)
        lost["card"] = card

    if licenze > 0:
        licenze -= 1
        lost["licenza"] = 1

    if addons:
        if player_chooses_addon is not None and player_chooses_addon in addons:
            addon = player_chooses_addon
        else:
            addon = random.choice(addons)
        addons.remove(addon)
        lost["addon"] = addon

    return {
        "hand": hand,
        "licenze": licenze,
        "addons": addons,
        "lost": lost,
    }


# ---------------------------------------------------------------------------
# ELO rating
# ---------------------------------------------------------------------------

ELO_K_FACTOR = 32


def expected_score(rating_a: int, rating_b: int) -> float:
    """Expected score for player A against player B."""
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_elo(ratings: list[int], winner_index: int) -> list[int]:
    """
    Update ELO ratings for a multiplayer game.
    Winner gets score=1 against every other player.
    Losers get score=0 against the winner, and 0.5 against each other.
    Returns a list of updated ratings in the same order as the input.
    """
    n = len(ratings)
    deltas = [0.0] * n

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            actual_i = 1.0 if i == winner_index else (0.0 if j == winner_index else 0.5)
            expected_i = expected_score(ratings[i], ratings[j])
            deltas[i] += ELO_K_FACTOR * (actual_i - expected_i)

    return [max(100, ratings[i] + round(deltas[i])) for i in range(n)]
