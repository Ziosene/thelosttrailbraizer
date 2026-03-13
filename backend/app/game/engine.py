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


def split_deck(deck: list) -> tuple[list, list]:
    """Split a shuffled deck into two halves as evenly as possible."""
    mid = len(deck) // 2
    return deck[:mid], deck[mid:]


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


# ---------------------------------------------------------------------------
# Boss ability system (bosses 1–60 implemented)
# ---------------------------------------------------------------------------
# All functions are pure — no DB access.  game_handler reads the returned
# values and applies the actual mutations to DB objects.
#
# Triggers used:
#   "on_combat_start"  — fired once when combat begins
#   "after_miss"       — fired each round the player fails to hit
#   "after_hit"        — fired each round the player lands a hit
#   "on_player_damage" — fired each time the player loses HP (includes extra damage)
#
# Query helpers (called before an action to decide whether it is allowed):
#   boss_roll_mode          — how many dice to roll and which to keep
#   boss_addons_disabled    — True if addons are locked this round
#   boss_offensive_cards_blocked — True if offensive action cards are forbidden
#   boss_interference_doubled    — True if opponent interference has 2x efficiency
#   boss_threshold          — effective dice threshold (may differ from card value)
# ---------------------------------------------------------------------------

_EMPTY_EFFECT: dict = {
    "extra_damage": 0,              # additional HP damage to combat player
    "boss_heal": 0,                 # boss recovers N HP
    "discard_cards": 0,             # player randomly discards N cards
    "steal_licenze": 0,             # player loses N licenze
    "opponent_gains_licenza": 0,    # a random opponent gains N licenza
    "aoe_hp_damage": 0,             # a random opponent (not combatant) loses N HP
    "aoe_all_hp_damage": 0,         # ALL opponents (not combatant) each lose N HP
    "licenza_drain": 0,             # player loses N licenze this round (always, hit or miss)
    "force_discard_or_damage": 0,   # player must discard N cards or take N HP each
    "bonus_certification": 0,       # player gains N extra certifications on boss defeat
    "bonus_licenze": 0,             # player gains N extra licenze on boss defeat
    "reveal_hand": False,           # player must reveal full hand to opponents
    "boss_revive": 0,               # boss resurrects with N HP (one-shot; handler tracks flag)
    "next_addon_cost_penalty": 0,   # player's next addon purchase costs +N licenze
    "absorb_cards": 0,              # boss absorbs N cards from player's hand (stored in combat state)
    "return_absorbed_cards": False, # player recovers all previously absorbed cards
    "lock_addon": 0,                # player must lock N addons at combat start (their choice); recovered on win
    "unlock_locked_addon": False,   # player recovers any addon locked by this combat
    "opponent_discards_from_hand": 0,  # one opponent (their choice) discards N cards from combatant's hand
    "bonus_chaos_roll": False,      # handler rolls an extra d10; on 1 a random penalty fires (card/HP/licenza)
    "boss_revive_to_deck": 0,       # boss is defeated but re-enters deck with N HP (once per game; handler tracks flag)
    "aoe_all_players_hp_damage": 0, # ALL players (including combatant) each lose N HP
    "licenza_or_hp_drain": 0,       # drain N licenze from player; if player has 0 licenze, drain N HP instead
    "hijack_addon": False,          # boss uses 1 of the combatant's untapped addons against them (inverted)
    "force_extra_card_discard": False,  # combatant must discard 1 additional card this round (involuntarily)
    "entry_fee_licenze": 0,         # pay N licenze at combat start; 1 HP damage per missing licenza
    "corrupt_deck_cards": 0,        # insert N corrupted cards into combatant's action deck; each deals 1 HP if drawn
    "makes_prediction": False,      # boss predicts hit/miss before roll; if correct, double the round effect
    "invert_random_hand_card": False,   # invert the effect of 1 random card in combatant's hand for this combat
}


def _boss_effect(**kwargs) -> dict:
    """Return a full effect dict with all keys, overriding only the supplied ones."""
    return {**_EMPTY_EFFECT, **kwargs}


def boss_roll_mode(boss_id: int, combat_round: int) -> str | None:
    """
    Returns a roll-mode override for this boss/round, or None for a normal single d10.
    combat_round is 1-indexed (first roll of the fight = round 1).

    Modes:
      "worst_of_2"  — roll twice, keep the lower result
    """
    match boss_id:
        case 1:   # Lord of the Governor Limits — odd rounds: worst of two rolls
            return "worst_of_2" if combat_round % 2 == 1 else None
        case 39:  # The Bulk API Behemoth — always roll twice, keep only the second result
            return "second_of_2"
    return None


def boss_addons_disabled(boss_id: int, combat_round: int) -> bool:
    """Returns True if the player's addons are disabled for the current round."""
    match boss_id:
        case 4:   # The Cursed Friday Deployment — addons locked rounds 1 and 2
            return combat_round <= 2
        case 30:  # The Release Update Scourge — addons locked rounds 1, 2, and 3
            return combat_round <= 3
    return False


def boss_offensive_cards_blocked(boss_id: int) -> bool:
    """Returns True if the player cannot play offensive action cards this combat."""
    match boss_id:
        case 9:  # The Code Coverage Ghoul
            return True
    return False


def boss_interference_doubled(boss_id: int) -> bool:
    """Returns True if opponent action-card interference has double efficiency."""
    match boss_id:
        case 8:  # The MuleSoft Kraken
            return True
    return False


def boss_threshold(
    boss_id: int,
    base_threshold: int,
    current_hp: int,
    *,
    hand_count: int = 0,
    combat_round: int = 1,
) -> int:
    """
    Returns the effective dice threshold for this roll.
    May differ from the card's printed value due to phase/condition mechanics.

    Args:
        hand_count:    number of cards currently in the player's hand (used by boss 12).
        combat_round:  1-indexed round number (used by boss 22).
    """
    match boss_id:
        case 10:  # The Eternal Org — phase 2 (≤ 4 HP remaining) raises threshold to 7
            if current_hp <= 4:
                return max(base_threshold, 7)
        case 12:  # The Merge Conflict Demon — more than 5 cards in hand → threshold 7+
            if hand_count > 5:
                return max(base_threshold, 7)
        case 22:  # The Seasonal Release Nightmare — threshold +1 per round, cap 10
            return min(10, base_threshold + (combat_round - 1))
        case 37:  # The Hyperforce Leviathan — 3 phases by HP
            # Phase 3 (≤3 HP): threshold 8+; phases 1–2 (>3 HP): threshold 7+
            if current_hp <= 3:
                return max(base_threshold, 8)
            return max(base_threshold, 7)
    return base_threshold


def boss_death_licenze_penalty(boss_id: int) -> int:
    """Returns total licenze lost on player death (default: DEATH_LOSE_LICENZE = 1)."""
    match boss_id:
        case 14:  # The Great Data Reaper — death costs 2 Licenze instead of 1
            return 2
    return DEATH_LOSE_LICENZE


def boss_disables_all_addons(boss_id: int) -> bool:
    """
    Returns True if ALL players' addons are disabled while fighting this boss.
    Checked in _handle_use_addon for any player in the game, not just the combatant.
    """
    match boss_id:
        case 15:  # trust.salesforce.DOOM
            return True
    return False


def boss_interference_blocked(boss_id: int) -> bool:
    """Returns True if opponents cannot play interference cards against this boss."""
    match boss_id:
        case 15:  # trust.salesforce.DOOM
            return True
    return False


def boss_max_cards_per_turn(boss_id: int, default_max: int) -> int:
    """Returns the max action cards the player may play per turn during this combat."""
    match boss_id:
        case 16:  # The Forbidden Profile & Permission Set — only 1 card allowed
            return 1
    return default_max


def boss_dice_modifiers_blocked(boss_id: int) -> bool:
    """Returns True if action-card dice modifiers have no effect during this combat."""
    match boss_id:
        case 17:  # Validation Rule Hell
            return True
    return False


def boss_free_interference(boss_id: int) -> bool:
    """Returns True if opponents can interfere for free (no Licenza cost) during combat."""
    match boss_id:
        case 19:  # Dreamforce Hydra (Legendary)
            return True
    return False


def boss_action_cards_inverted(boss_id: int) -> bool:
    """
    Returns True if action card effects are inverted during this combat
    (healing effects become damage and vice versa).
    """
    match boss_id:
        case 21:  # The Einstein GPT Hallucination
            return True
    return False


def boss_opponent_free_action_per_round(boss_id: int) -> bool:
    """
    Returns True if each round one opponent (of their choice) may play
    1 action card for free against the combatant.
    """
    match boss_id:
        case 24:  # The Slack Apparition
            return True
    return False


def boss_action_card_licenze_blocked(boss_id: int) -> bool:
    """Returns True if the combatant cannot gain Licenze from action cards during this combat."""
    match boss_id:
        case 28:  # The Pardot Shadow
            return True
    return False


def boss_card_declared_before_roll(boss_id: int) -> bool:
    """
    Returns True if the player must declare which action card they intend to play
    BEFORE rolling the dice.  If the roll fails, the declared card is still consumed.
    """
    match boss_id:
        case 33:  # The Experience Cloud Illusion
            return True
    return False


def boss_hand_visible_to_opponents(boss_id: int) -> bool:
    """
    Returns True if opponents can see which action card the combatant intends to play
    before it resolves (handler broadcasts a 'card_declared' event to non-combatants).
    """
    match boss_id:
        case 41:  # The Quip Wisp
            return True
    return False


def boss_immune_to_card_damage(boss_id: int) -> bool:
    """Returns True if action-card damage effects deal 0 HP to this boss."""
    match boss_id:
        case 43:  # The Shield Golem — only dice rolls can wound it
            return True
    return False


def boss_heals_on_addon_use(boss_id: int) -> int:
    """
    Returns the HP the boss recovers every time the combatant activates an addon.
    Returns 0 if the boss has no such ability.
    """
    match boss_id:
        case 49:  # The Managed Package Leech — +1 HP per addon activation
            return 1
    return 0


def boss_expires_after_rounds(boss_id: int) -> int | None:
    """
    Returns the maximum number of combat rounds before this boss auto-expires
    (combat ends immediately with NO reward for the player).
    Returns None if the boss does not have an expiry mechanic.
    """
    match boss_id:
        case 48:  # The Scratch Org Mirage — expires if combat exceeds 5 rounds
            return 5
    return None


def boss_damage_absorption(boss_id: int) -> int:
    """
    Returns the number of hits this boss absorbs (ignores) before taking real damage.
    Handler tracks `combat_hits_absorbed` counter; only decrement boss HP once counter is exhausted.
    """
    match boss_id:
        case 52:  # The Manufacturing Cloud Beast — first 3 hits absorbed
            return 3
    return 0


def boss_is_mimic(boss_id: int) -> bool:
    """
    Returns True if this boss copies the ability of the last boss defeated in this game.
    Handler must call apply_boss_ability(game.last_defeated_boss_id, trigger, ...) in parallel
    and apply those effects too.  If no boss has been defeated yet, no extra effects fire.
    """
    match boss_id:
        case 55:  # The Custom Metadata Mimic
            return True
    return False


def boss_permanently_bans_used_cards(boss_id: int) -> bool:
    """
    Returns True if every action card played during this combat is permanently banned —
    removed from the deck and added to game.banned_card_ids for the rest of the game.
    """
    match boss_id:
        case 56:  # The Change Data Capture Lurker
            return True
    return False


def boss_death_licenze_to_top_cert(boss_id: int) -> bool:
    """
    Returns True if, when the combatant dies during this fight, their lost Licenze go
    to the opponent with the most certifications instead of disappearing.
    """
    match boss_id:
        case 57:  # The Named Credentials Thief
            return True
    return False


def boss_heals_on_interference(boss_id: int) -> int:
    """
    Returns the HP the boss recovers each time an opponent plays an interference card
    against the combatant during this combat.
    """
    match boss_id:
        case 59:  # The Trailblazer Community Mob — +1 HP per interference card
            return 1
    return 0


def boss_blocks_addon_purchase(boss_id: int) -> bool:
    """Returns True if the combatant cannot buy addons while this boss is in combat."""
    match boss_id:
        case 60:  # The Connected App Infiltrator (Legendary)
            return True
    return False


def boss_cancels_next_card(boss_id: int, combat_round: int) -> bool:
    """
    Returns True if the boss automatically nullifies the next action card played
    this round.  Handler must set a per-round flag so the first card played is ignored.
    """
    match boss_id:
        case 38:  # The Einstein Bot Imposter — cancels on even rounds (2, 4, 6, …)
            return combat_round % 2 == 0
    return False


def apply_boss_ability(
    boss_id: int,
    trigger: str,
    *,
    dice_result: int | None = None,
    combat_round: int = 1,
    cards_played: int = 0,
    current_hp: int = 0,
) -> dict:
    """
    Returns a side-effect dict describing what the game_handler must apply.
    All values default to 0 — caller only needs to act on non-zero entries.

    Args:
        boss_id:       BossCard.id of the boss currently in combat.
        trigger:       Event that fired:
                         "on_combat_start"  — once when combat begins
                         "on_round_start"   — before rolling each round
                         "after_miss"       — after a failed roll
                         "after_hit"        — after a successful hit
                         "on_player_damage" — after player loses HP
                         "on_round_end"     — after hit/miss and damage resolved
                         "on_boss_defeated" — when boss HP reaches 0
        dice_result:   Actual d10 value (needed for some after_miss effects).
        combat_round:  1-indexed round number (needed for round-conditional effects).
        cards_played:  Cards played this turn (needed for on_boss_defeated effects).
        current_hp:    Boss current HP (needed for phase-based effects like boss 37).
    """
    match (boss_id, trigger):

        # ── Boss 2 — The Haunted Debug Log ─────────────────────────────────
        # At combat start the player randomly discards 1 card from their hand.
        case (2, "on_combat_start"):
            return _boss_effect(discard_cards=1)

        # ── Boss 3 — The Screaming Unhandled Exception ──────────────────────
        # Rolling a natural 1 deals 2 HP damage instead of 1 (extra_damage=1).
        case (3, "after_miss"):
            if dice_result == 1:
                return _boss_effect(extra_damage=1)

        # ── Boss 5 — The Sandbox Tyrant ─────────────────────────────────────
        # Every time the player takes HP damage a random opponent gains 1 Licenza.
        # NOTE: player technically chooses the opponent; handler picks randomly for now.
        case (5, "on_player_damage"):
            return _boss_effect(opponent_gains_licenza=1)

        # ── Boss 6 — The Infinite Apex Loop of Doom ─────────────────────────
        # Each missed roll heals the boss by 1 HP (capped at max HP by caller).
        case (6, "after_miss"):
            return _boss_effect(boss_heal=1)

        # ── Boss 7 — The SOQL Vampire ────────────────────────────────────────
        # At combat start the boss steals 2 Licenze from the player.
        case (7, "on_combat_start"):
            return _boss_effect(steal_licenze=2)

        # ── Boss 11 — The LWC Poltergeist ───────────────────────────────────
        # On even rounds, a random opponent (not the combatant) takes 1 HP damage.
        case (11, "on_round_end"):
            if combat_round % 2 == 0:
                return _boss_effect(aoe_hp_damage=1)

        # ── Boss 13 — Flow Builder Gone Rogue ───────────────────────────────
        # At the start of every round: player must discard 1 card or take 1 HP.
        # Handler auto-discards if cards are available; otherwise deals 1 HP damage.
        # TODO: make this a client choice (discard which card?) when UX is in place.
        case (13, "on_round_start"):
            return _boss_effect(force_discard_or_damage=1)

        # ── Boss 18 — The Tech Debt Lich ────────────────────────────────────
        # Every round (hit or miss) the player loses 1 Licenza.
        case (18, "on_round_start"):
            return _boss_effect(licenza_drain=1)

        # ── Boss 19 — Dreamforce Hydra (Legendary) ──────────────────────────
        # The combatant gets 1 bonus certification when the boss is defeated
        # (on top of the standard cert reward). Free-interference flag is handled
        # via boss_free_interference() query helper, not here.
        case (19, "on_boss_defeated"):
            return _boss_effect(bonus_certification=1)

        # ── Boss 20 — The Corrupted Trailblazer ─────────────────────────────
        # Win without playing any action cards this turn → +3 bonus Licenze.
        case (20, "on_boss_defeated"):
            if cards_played == 0:
                return _boss_effect(bonus_licenze=3)

        # ── Boss 23 — The Tableau Wraith ─────────────────────────────────────
        # At combat start the combatant's hand is revealed to all opponents.
        # The handler broadcasts a "hand_reveal" event to non-combatant players.
        case (23, "on_combat_start"):
            return _boss_effect(reveal_hand=True)

        # ── Boss 25 — The Heroku Dyno Zombie ─────────────────────────────────
        # First time the boss reaches 0 HP it auto-revives with 3 HP.
        # Handler must check a `boss_resurrection_used` flag in combat state;
        # if False, apply boss_revive and set the flag to True instead of ending combat.
        case (25, "on_boss_defeated"):
            return _boss_effect(boss_revive=3)

        # ── Boss 26 — The CPQ Configuration Chaos ────────────────────────────
        # After defeating this boss the combatant's NEXT addon purchase costs +3.
        # Handler stores a `pending_addon_cost_penalty` value on the player record.
        case (26, "on_boss_defeated"):
            return _boss_effect(next_addon_cost_penalty=3)

        # ── Boss 27 — The Marketing Cloud Banshee ────────────────────────────
        # Every round ALL opponents (not the combatant) lose 1 HP from the banshee's scream.
        case (27, "on_round_end"):
            return _boss_effect(aoe_all_hp_damage=1)

        # ── Boss 29 — The Data Cloud Colossus ────────────────────────────────
        # Each hit: boss absorbs 1 card from the combatant's hand into combat state.
        # On defeat: all absorbed cards are returned to the player's hand.
        case (29, "after_hit"):
            return _boss_effect(absorb_cards=1)
        case (29, "on_boss_defeated"):
            return _boss_effect(return_absorbed_cards=True)

        # ── Boss 31 — The AppExchange Parasite ───────────────────────────────
        # At combat start the player locks 1 addon of their choice (disabled for the fight).
        # On defeat, the locked addon is restored.
        case (31, "on_combat_start"):
            return _boss_effect(lock_addon=1)
        case (31, "on_boss_defeated"):
            return _boss_effect(unlock_locked_addon=True)

        # ── Boss 32 — The Field Service Revenant ─────────────────────────────
        # On even rounds the boss automatically deals 1 extra HP damage to the combatant.
        case (32, "on_round_end"):
            if combat_round % 2 == 0:
                return _boss_effect(extra_damage=1)

        # ── Boss 34 — The Batch Apex Necromancer ─────────────────────────────
        # First defeat is real (player gets rewards). Boss re-enters deck with 3 HP.
        # Handler checks `batch_necromancer_resurrected` flag in game state;
        # if already True, the boss is simply discarded normally on second defeat.
        case (34, "on_boss_defeated"):
            return _boss_effect(boss_revive_to_deck=3)

        # ── Boss 35 — The Platform Event Gremlin ─────────────────────────────
        # Every round the handler rolls an extra d10. On a 1, one random penalty fires:
        # lose 1 card | take 1 HP damage | a random opponent gains 2 Licenze.
        case (35, "on_round_start"):
            return _boss_effect(bonus_chaos_roll=True)

        # ── Boss 36 — The SOSL Shade ─────────────────────────────────────────
        # At combat start one opponent (of their choice) peeks at the combatant's hand
        # and discards 1 card from it.
        case (36, "on_combat_start"):
            return _boss_effect(opponent_discards_from_hand=1)

        # ── Boss 37 — The Hyperforce Leviathan (Legendary) ───────────────────
        # Phases 2 & 3 (boss HP ≤ 6): each miss deals 2 HP to combatant (extra_damage=1
        # on top of the standard 1 HP miss penalty).
        # Threshold scaling is handled by boss_threshold(); free-interference flag by
        # boss_free_interference() is NOT set here — this boss has no free-interference.
        case (37, "after_miss"):
            if current_hp <= 6:
                return _boss_effect(extra_damage=1)

        # ── Boss 40 — The Net Zero Apocalypse ────────────────────────────────
        # Every miss: ALL players (including the combatant) each lose 1 HP.
        case (40, "after_miss"):
            return _boss_effect(aoe_all_players_hp_damage=1)

        # ── Boss 42 — The Revenue Cloud Devourer ─────────────────────────────
        # Round start: drain 1 Licenza. If player has 0 licenze, drain 1 HP instead.
        case (42, "on_round_start"):
            return _boss_effect(licenza_or_hp_drain=1)

        # ── Boss 44 — The SSO Doppelganger ───────────────────────────────────
        # At combat start a random opponent gains 2 Licenze (the "stolen identity" reward).
        # NOTE: card says "avversario a scelta" (opponent's choice); using random until UX ready.
        case (44, "on_combat_start"):
            return _boss_effect(opponent_gains_licenza=2)

        # ── Boss 45 — The Agentforce Rebellion ───────────────────────────────
        # Every round the boss hijacks 1 of the combatant's available addons and uses it
        # with inverted effect against them.
        # Handler: pick a random untapped addon → apply inverted effect → mark it as tapped.
        case (45, "on_round_start"):
            return _boss_effect(hijack_addon=True)

        # ── Boss 46 — The Process Builder Abomination ────────────────────────
        # Every round the combatant involuntarily discards 1 extra card from their hand.
        case (46, "on_round_start"):
            return _boss_effect(force_extra_card_discard=True)

        # ── Boss 47 — The Omni-Channel Chimera ───────────────────────────────
        # Cycling 3-round attack pattern (1-indexed, wraps with mod 3):
        #   cycle position 1 → extra damage to combatant
        #   cycle position 2 → steal (discard) 1 card from combatant's hand
        #   cycle position 0 → a random opponent gains 2 Licenze
        case (47, "on_round_end"):
            cycle = combat_round % 3
            if cycle == 1:
                return _boss_effect(extra_damage=1)
            elif cycle == 2:
                return _boss_effect(discard_cards=1)
            else:  # cycle == 0
                return _boss_effect(opponent_gains_licenza=2)

        # ── Boss 50 — The Health Cloud Plague ────────────────────────────────
        # Every round ALL players (including combatant) lose 1 HP.
        case (50, "on_round_end"):
            return _boss_effect(aoe_all_players_hp_damage=1)

        # ── Boss 51 — The Financial Services Fiend ───────────────────────────
        # At combat start: pay 3 Licenze as "commission". For each licenza short, take 1 HP.
        case (51, "on_combat_start"):
            return _boss_effect(entry_fee_licenze=3)

        # ── Boss 53 — The Einstein Discovery Oracle ───────────────────────────
        # Before each roll the boss makes a random prediction (hit / miss).
        # Handler stores the prediction, then after the roll doubles the effect if correct:
        #   correct hit prediction  → boss takes 2 HP instead of 1
        #   correct miss prediction → player takes 2 HP instead of 1
        case (53, "on_round_start"):
            return _boss_effect(makes_prediction=True)

        # ── Boss 54 — The Workbench Tinkerer ─────────────────────────────────
        # At combat start: 3 corrupted cards are shuffled into the combatant's action deck.
        # When drawn, each corrupted card deals 1 HP to the player instead of having an effect.
        # Handler adds 3 sentinel card IDs (e.g. -54) to the shared action_deck.
        case (54, "on_combat_start"):
            return _boss_effect(corrupt_deck_cards=3)

        # ── Boss 58 — The Prompt Builder Djinn ───────────────────────────────
        # Each round: pick 1 random card in the combatant's hand and invert its effect
        # for the remainder of this combat (tracked in combat state as a set of card IDs).
        case (58, "on_round_start"):
            return _boss_effect(invert_random_hand_card=True)

        # ── Boss 60 — The Connected App Infiltrator (Legendary) ──────────────
        # Every even round: auto-discard 1 random card from combatant's hand.
        # Addon-purchase block is handled by boss_blocks_addon_purchase() query helper.
        case (60, "on_round_end"):
            if combat_round % 2 == 0:
                return _boss_effect(discard_cards=1)

    return _boss_effect()
