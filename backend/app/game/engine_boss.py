"""
Boss ability system — pure functions, no DB/WebSocket dependencies.
All 100 bosses implemented and complete.

game_handler reads the returned values and applies the actual mutations to DB objects.

Triggers:
  "on_combat_start"  — fired once when combat begins
  "on_round_start"   — before rolling each round
  "after_miss"       — fired each round the player fails to hit
  "after_hit"        — fired each round the player lands a hit
  "on_player_damage" — fired each time the player loses HP (includes extra damage)
  "on_round_end"     — after hit/miss and damage resolved
  "on_boss_defeated" — when boss HP reaches 0

Query helpers (called before an action to decide whether it is allowed):
  boss_roll_mode          — how many dice to roll and which to keep
  boss_addons_disabled    — True if addons are locked this round
  boss_offensive_cards_blocked — True if offensive action cards are forbidden
  boss_interference_doubled    — True if opponent interference has 2x efficiency
  boss_threshold          — effective dice threshold (may differ from card value)
"""

# Death penalty constants (same values as defined in engine.py core)
DEATH_LOSE_LICENZE = 1
DEATH_LOSE_ADDONS = 1

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
    "exam_roll": False,             # handler rolls d10 before combat: ≥7 → player +1 HP; ≤3 → player -1 HP
    "deal_offer": False,            # boss offers 1 free licenza; if accepted, threshold +1 this round (player chooses)
    "bonus_hp_per_player_addon": False,  # boss starts combat with +1 HP for each addon the combatant owns
    "boss_splits_on_heavy_hit": False,   # if boss takes 2+ damage this round, spawn a 3-HP no-ability duplicate
    "aoe_discard_all_hands": 0,     # remove N random cards from EVERY player's hand (including combatant)
    "opponent_draws_card": 0,       # a random opponent draws N extra cards
    "reveal_all_licenze": False,    # reveal all players' licenze counts; richest non-combatant plays 1 free card
    "refresh_hand": 0,              # combatant discards entire hand and draws N new cards
    "certification_exam_rolls": 0,  # roll N dice before combat: each ≥8 → +1 HP +2 licenze; each ≤4 → -1 HP
    # ── Bosses 81-90 ────────────────────────────────────────────────────────
    "petrify_cards": 0,             # lock N random cards from combatant's hand; unlocked on boss defeat
    "siren_deal": False,            # boss offers siren bargain: skip attack → +2 licenze, boss +1 HP (player chooses)
    "doomsayer_prediction_roll": False,  # handler rolls d10 at combat start; stores prediction; each exceeded round → +1 HP
    "force_card_type_declaration": False,  # combatant must declare Attack or Defense type; restricted for full combat
    "aoe_unblockable_hp_damage": 0, # ALL players (including combatant) lose N HP; defensive cards cannot negate this
    "reveal_next_bosses": 0,        # reveal the next N boss cards in the deck to all players
    # ── Bosses 91-100 ───────────────────────────────────────────────────────
    "steal_and_use_addon": False,   # boss steals 1 combatant addon, applies its effect vs player; returned on defeat
    "draw_bonus_cards": 0,          # combatant draws N extra cards at combat start
    "subscription_drain": 0,        # pay N licenze each round; if unable, take 2×N HP instead
    "permanently_destroy_addon": 0, # permanently destroy N random combatant addons (not recovered on win)
    "shuffle_all_hands": False,     # pool all players' hand cards, reshuffle, redistribute keeping same counts
    "bonus_licenze_to_helpers": 0,  # every player who played an action card this combat gains N licenze on defeat
    "instant_win": False,           # combatant wins the game immediately on boss defeat (skips cert check)
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
    """Returns True if the COMBATANT's addons are disabled for the current round."""
    match boss_id:
        case 4:   # The Cursed Friday Deployment — addons locked rounds 1 and 2
            return combat_round <= 2
        case 30:  # The Release Update Scourge — addons locked rounds 1, 2, and 3
            return combat_round <= 3
        case 77:  # The SFDX Imp — addons disabled for the entire combat
            return True
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


def boss_disables_all_addons(boss_id: int, combat_round: int = 1) -> bool:
    """
    Returns True if ALL players' addons are disabled this round.
    Checked in _handle_use_addon for any player in the game, not just the combatant.

    Args:
        combat_round: 1-indexed round number (used by boss 79 which only disables for 3 rounds).
    """
    match boss_id:
        case 15:  # trust.salesforce.DOOM — disables all addons for the entire combat
            return True
        case 79:  # The ISVForce Overlord — disables all addons only for rounds 1–3
            return combat_round <= 3
    return False


def boss_interference_blocked(boss_id: int) -> bool:
    """Returns True if opponents cannot play interference cards against this boss."""
    match boss_id:
        case 15:  # trust.salesforce.DOOM
            return True
        case 79:  # The ISVForce Overlord (Legendary)
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


def boss_immune_to_card_damage(boss_id: int, combat_round: int = 0) -> bool:
    """
    Returns True if action-card damage effects deal 0 HP to this boss this round.

    Args:
        combat_round: 1-indexed round number (used by boss 78 alternating immunity).
    """
    match boss_id:
        case 43:  # The Shield Golem — always immune to card damage
            return True
        case 78:  # The Known Issues Ghost — immune to cards on even rounds
            return combat_round % 2 == 0
        case 89:  # The Object Manager Juggernaut — immune to cards on odd rounds
            return combat_round % 2 == 1
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
        case 90:  # The Quick Action Marauder — escapes after round 3 with no reward
            return 3
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


def boss_forces_top_card_play(boss_id: int) -> bool:
    """
    Returns True if the combatant's hand is reshuffled into the deck each round and
    only the top card may be played (no free choice of card).
    """
    match boss_id:
        case 64:  # The Order Management Maelstrom
            return True
    return False


def boss_cancels_offensive_if_revealed(boss_id: int) -> bool:
    """
    Returns True if the boss reveals the intended action card before it resolves
    and automatically cancels it if it is an offensive card (card is still consumed).
    """
    match boss_id:
        case 65:  # The Einstein Vision Stalker
            return True
    return False


def boss_blocks_retreat(boss_id: int) -> bool:
    """Returns True if no action card or game mechanic can trigger a retreat from this combat."""
    match boss_id:
        case 66:  # The Deploy to Production Nemesis (Legendary)
            return True
    return False


def boss_death_addon_penalty(boss_id: int) -> int:
    """Returns the number of addons lost on player death (default: DEATH_LOSE_ADDONS = 1)."""
    match boss_id:
        case 66:  # The Deploy to Production Nemesis — death costs 2 addons
            return 2
    return DEATH_LOSE_ADDONS


def boss_nullifies_round_on_low_roll(boss_id: int) -> bool:
    """
    Returns True if a dice result of 1 or 2 nullifies the entire round — no damage
    in either direction.  Handler checks the actual roll AFTER rolling and skips
    all damage application if True and roll ≤ 2.
    """
    match boss_id:
        case 67:  # The Developer Console Glitch
            return True
    return False


def boss_heals_on_defensive_card(boss_id: int) -> int:
    """
    Returns the HP the boss recovers each time the combatant plays a defensive action card.
    Returns 0 if the boss has no such ability.
    """
    match boss_id:
        case 72:  # The DevOps Center Saboteur — +1 HP per defensive card played
            return 1
    return 0


def boss_is_shape_shifter(boss_id: int) -> bool:
    """
    Returns True if this boss changes its active ability every 2 rounds by copying
    a randomly selected previously-defeated boss.
    Handler: on every even round, pick a random id from game.defeated_boss_ids and
    call apply_boss_ability(that_id, trigger, ...) for the rest of that round.
    """
    match boss_id:
        case 74:  # The Org Shape Shifter
            return True
    return False


def boss_immune_to_dice(boss_id: int, combat_round: int) -> bool:
    """
    Returns True if the boss cannot take damage from dice rolls this round.
    Handler should skip boss HP decrement when this returns True.
    """
    match boss_id:
        case 78:  # The Known Issues Ghost — immune to dice on odd rounds
            return combat_round % 2 == 1
        case 89:  # The Object Manager Juggernaut — immune to dice on even rounds
            return combat_round % 2 == 0
    return False


def boss_requires_approval_roll(boss_id: int) -> bool:
    """
    Returns True if every action card played must pass an approval roll (extra d10).
    If the approval roll is ≤ 4 the card is consumed but has no effect.
    """
    match boss_id:
        case 69:  # The Approval Process Bureaucrat
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


def boss_jinx_on_draw(boss_id: int) -> bool:
    """
    Returns True if cards drawn by the combatant during combat are cursed —
    handler rolls a d10 on each draw; result of 1–3 means the card is discarded
    immediately without effect (jinxed).
    """
    match boss_id:
        case 81:  # The Trailhead Jinx
            return True
    return False


def boss_halves_card_effects(boss_id: int) -> bool:
    """
    Returns True if all action card effects are halved (rounded down) during this combat:
    damage, healing, licenze bonuses, and any numeric modifier.
    """
    match boss_id:
        case 85:  # The Formula Field Corruptor
            return True
    return False


def boss_draw_costs_hp(boss_id: int) -> int:
    """
    Returns the HP cost the combatant pays each time they draw an action card during combat.
    Handler deducts N HP from the combatant after every draw (including the combat-start draw bonus).
    """
    match boss_id:
        case 92:  # The Einstein Copilot Seraph — each card drawn costs 1 HP
            return 1
    return 0


def boss_loyalty_shield(boss_id: int) -> int:
    """
    Returns the starting number of loyalty points that shield this boss from dice damage.
    Handler stores current loyalty in combat_state.loyalty_points;
    while loyalty_points > 0, boss_immune_to_dice returns True.
    Each defensive action card the combatant plays decrements loyalty_points by 1.
    Returns 0 if the boss has no loyalty shield.
    """
    match boss_id:
        case 94:  # The Loyalty Cloud Warden — starts with 3 loyalty points
            return 3
    return 0


def boss_redirects_damage_to_opponent(boss_id: int) -> bool:
    """
    Returns True if HP damage that the boss would deal to the combatant is redirected
    to a random opponent instead.  The combatant still fights the boss normally;
    only the damage destination changes.
    """
    match boss_id:
        case 95:  # The Identity & Access Heretic
            return True
    return False


def boss_compliance_penalty_per_extra_card(boss_id: int) -> int:
    """
    Returns the extra HP damage the boss deals for each action card played beyond the
    first in a single round.  Handler checks cards_played_this_turn after each play_card;
    if it exceeds 1, immediately deals (cards_played_this_turn - 1) × return_value HP.
    Returns 0 if the boss has no compliance mechanic.
    """
    match boss_id:
        case 96:  # The Compliance Cloud Sentinel — 1 extra HP per card over the first
            return 1
    return 0


def boss_is_omega(boss_id: int) -> bool:
    """
    Returns True if this boss is the Lost Trailblazer Omega — the final boss.
    On each phase transition (every time boss HP crosses a multiple-of-3 threshold),
    the handler routes all triggers to game.last_defeated_legendary_boss_id and applies
    those effects in addition to the omega's own.
    Requires ≥10 bosses to have been defeated in the game before it can appear.
    """
    match boss_id:
        case 100:  # The Lost Trailblazer Omega
            return True
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

        # ── Boss 61 — The Nonprofit Cloud Blight ─────────────────────────────
        # Combatant starts combat with 2 fewer Licenze ("always underfunded").
        case (61, "on_combat_start"):
            return _boss_effect(steal_licenze=2)

        # ── Boss 62 — The Education Cloud Inquisitor ─────────────────────────
        # Before combat: roll exam d10.
        #   ≥ 7 → combatant gains +1 HP (extra health from passing)
        #   ≤ 3 → combatant starts with -1 HP (penalty for failing)
        #   4–6 → no effect
        case (62, "on_combat_start"):
            return _boss_effect(exam_roll=True)

        # ── Boss 63 — The Loyalty Management Trickster ───────────────────────
        # Every round: boss offers 1 free Licenza. Accepting raises the dice threshold
        # by 1 for this round only. Handler broadcasts a deal_offer event and waits for
        # player response; if accepted, gain 1 licenza and apply +1 to effective threshold.
        # TODO: implement client accept/reject flow; currently auto-accepts for simplicity.
        case (63, "on_round_start"):
            return _boss_effect(deal_offer=True)

        # ── Boss 68 — The Schema Builder Monstrosity ──────────────────────────
        # At combat start: boss HP increases by 1 for each addon the combatant owns.
        # Handler: boss_current_hp += len(player.addons)
        case (68, "on_combat_start"):
            return _boss_effect(bonus_hp_per_player_addon=True)

        # ── Boss 70 — The Duplicate Management Monster ────────────────────────
        # After any hit: if boss took 2+ damage this round, it splits into a second
        # boss with 3 HP and no special ability.  Handler spawns a secondary combat
        # target on player.current_boss_duplicate_hp = 3 (flag once per combat).
        case (70, "after_hit"):
            return _boss_effect(boss_splits_on_heavy_hit=True)

        # ── Boss 71 — The Data Loader Annihilator ────────────────────────────
        # At combat start: removes 2 random cards from EVERY player's hand.
        case (71, "on_combat_start"):
            return _boss_effect(aoe_discard_all_hands=2)

        # ── Boss 73 — The Streaming API Storm ────────────────────────────────
        # Every round: a random opponent (not combatant) draws 1 extra card.
        case (73, "on_round_end"):
            return _boss_effect(opponent_draws_card=1)

        # ── Boss 75 — The Einstein Opportunity Harbinger ──────────────────────
        # At combat start: reveals all players' licenze counts to everyone.
        # The opponent with the most licenze then plays 1 action card for free.
        case (75, "on_combat_start"):
            return _boss_effect(reveal_all_licenze=True)

        # ── Boss 76 — The Sandbox Refresh Catastrophe ────────────────────────
        # At combat start: combatant discards entire hand and draws 4 new cards.
        case (76, "on_combat_start"):
            return _boss_effect(refresh_hand=4)

        # ── Boss 80 — The Certification Exam Executioner (Legendary) ─────────
        # Before combat: roll 5 exam dice.
        #   Each result ≥ 8 → combatant gains +1 HP and +2 Licenze
        #   Each result ≤ 4 → combatant starts with -1 HP
        # Handler: roll 5 × d10, apply cumulative HP/licenze adjustments.
        case (80, "on_combat_start"):
            return _boss_effect(certification_exam_rolls=5)

        # ── Boss 82 — The Customer 360 Gorgon ────────────────────────────────
        # At combat start: 2 random cards in combatant's hand are petrified (cannot be played).
        # Handler stores their IDs in combat_state.petrified_card_ids; unlocked on boss defeat.
        case (82, "on_combat_start"):
            return _boss_effect(petrify_cards=2)

        # ── Boss 83 — The Account Engagement Siren ───────────────────────────
        # Every round: siren offers a deal — skip the attack, gain 2 Licenze, boss recovers 1 HP.
        # Handler broadcasts a siren_deal event; if player accepts, grant 2 licenze, heal boss 1 HP,
        # and skip the roll for this round.
        # TODO: implement client accept/reject flow; currently auto-rejects for simplicity.
        case (83, "on_round_start"):
            return _boss_effect(siren_deal=True)

        # ── Boss 84 — The Data Import Doomsayer ──────────────────────────────
        # At combat start: handler rolls d10 to predict fight duration.
        #   1–4 → predicts ≤ 2 rounds (short)
        #   5–7 → predicts ≤ 4 rounds (medium)
        #   8–10 → predicts ≤ 6 rounds (long)
        # On each on_round_end: if current combat_round exceeds the prediction cap, deal 1 HP extra.
        # Handler stores prediction category + HP flag in combat state.
        case (84, "on_combat_start"):
            return _boss_effect(doomsayer_prediction_roll=True)

        # ── Boss 86 — The Record Type Ravager ────────────────────────────────
        # At combat start: combatant must declare Attack OR Defense.
        # For the rest of the fight, only cards matching the declared type may be played.
        # Handler broadcasts declaration request; stores player choice in combat_state.allowed_card_type.
        # TODO: implement client declaration flow; currently defaults to no restriction until UX ready.
        case (86, "on_combat_start"):
            return _boss_effect(force_card_type_declaration=True)

        # ── Boss 87 — The Pub/Sub API Pestilence (Trophy) ────────────────────
        # Every round: ALL players (including combatant) each lose 1 HP from the published event.
        # Opponents' defensive action cards cannot negate this damage (handler must bypass defense checks).
        case (87, "on_round_end"):
            return _boss_effect(aoe_unblockable_hp_damage=1)

        # ── Boss 88 — The Report Builder Omen ────────────────────────────────
        # At combat start: reveal the next 3 boss cards in the deck to all players.
        # Handler reads the top 3 IDs from game.boss_deck and broadcasts a "boss_preview" event.
        # Opponents may use this info to prepare; the combatant is considered "unprepared" (flavor only).
        case (88, "on_combat_start"):
            return _boss_effect(reveal_next_bosses=3)

        # ── Boss 91 — The List View Usurper ──────────────────────────────────
        # At combat start: steals 1 addon from combatant and immediately uses it against them.
        # Handler: pick a random untapped addon → apply its effect inversely → mark it as stolen
        # (store in combat_state.stolen_addon_id).  On defeat: return it to the player's addon list.
        case (91, "on_combat_start"):
            return _boss_effect(steal_and_use_addon=True)
        case (91, "on_boss_defeated"):
            return _boss_effect(unlock_locked_addon=True)

        # ── Boss 92 — The Einstein Copilot Seraph ────────────────────────────
        # At combat start: combatant draws 2 extra cards (seraph's "gift").
        # Every card drawn during this combat costs 1 HP (tracked via boss_draw_costs_hp() helper).
        # The 2 bonus draws at start also trigger the HP cost.
        case (92, "on_combat_start"):
            return _boss_effect(draw_bonus_cards=2)

        # ── Boss 93 — The Subscription Management Tormentor ──────────────────
        # Every round: pay 1 Licenza or take 2 HP damage instead.
        # Handler checks player.licenze; if > 0 deduct 1; else deal 2 HP to combatant.
        case (93, "on_round_start"):
            return _boss_effect(subscription_drain=1)

        # ── Boss 96 — The Compliance Cloud Sentinel ───────────────────────────
        # On round end: for each action card played beyond the first this round,
        # boss deals 1 extra HP damage to the combatant.
        # (boss_compliance_penalty_per_extra_card() is the query helper for live per-card checks.)
        case (96, "on_round_end"):
            extra = max(0, cards_played - 1)
            if extra > 0:
                return _boss_effect(extra_damage=extra)

        # ── Boss 97 — The myTrailhead Defiler ─────────────────────────────────
        # At combat start: permanently destroys 1 random addon from the combatant.
        # The addon goes to game.addon_graveyard and is NOT returned even on boss defeat.
        case (97, "on_combat_start"):
            return _boss_effect(permanently_destroy_addon=1)

        # ── Boss 98 — The Dreamforce Aftermath Cataclysm (Trophy) ─────────────
        # At combat start: pool all players' hand cards, shuffle, redistribute (each keeps same count).
        # Handler: collect all player_hand_cards, shuffle pool, deal back N to each player
        # where N = their original hand size.
        case (98, "on_combat_start"):
            return _boss_effect(shuffle_all_hands=True)

        # ── Boss 99 — The Certified Technical Architect Titan (Trophy) ────────
        # Legendary, 4 phases (HP 12→9→6→3).  Each phase beyond the first adds 1 extra HP
        # damage to the combatant on every miss:
        #   Phase 1 (HP 10–12): 0 extra   Phase 2 (HP 7–9): +1
        #   Phase 3 (HP 4–6):  +2         Phase 4 (HP 1–3): +3
        # On defeat: every player who played an action card this combat gains 2 Licenze.
        # Threshold (8+) is printed on the card — no boss_threshold override needed.
        case (99, "after_miss"):
            if current_hp >= 10:
                pass  # phase 1 — no extra damage
            elif current_hp >= 7:
                return _boss_effect(extra_damage=1)
            elif current_hp >= 4:
                return _boss_effect(extra_damage=2)
            else:
                return _boss_effect(extra_damage=3)
        case (99, "on_boss_defeated"):
            return _boss_effect(bonus_licenze_to_helpers=2)

        # ── Boss 100 — The Lost Trailblazer Omega (Trophy — FINAL BOSS) ───────
        # THE final boss. 5 phases, each copies the last defeated Legendary boss's ability.
        # Handled entirely via boss_is_omega() query helper: handler routes every trigger
        # to game.last_defeated_legendary_boss_id in parallel with the omega's own effects.
        # On defeat: combatant wins the game immediately regardless of cert count,
        # and gains 2 bonus certifications.
        case (100, "on_boss_defeated"):
            return _boss_effect(instant_win=True, bonus_certification=2)

    return _boss_effect()
