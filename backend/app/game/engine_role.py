"""
Role passive ability system.
Each role has a passive ability that can be:
- "automatic": triggers on specific game events
- "active": player explicitly triggers once per turn
"""

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.game import GamePlayer, GameSession

# Role name constants (as stored in player.role)
ROLE_ADMINISTRATOR = "Administrator"
ROLE_ADVANCED_ADMINISTRATOR = "Advanced Administrator"
ROLE_PLATFORM_DEV_I = "Platform Developer I"
ROLE_PLATFORM_DEV_II = "Platform Developer II"
ROLE_JS_DEV_I = "JavaScript Developer I"
ROLE_INTEGRATION_ARCH = "Integration Architect"
ROLE_DATA_ARCH = "Data Architect"
ROLE_SHARING_VISIBILITY_ARCH = "Sharing & Visibility Architect"
ROLE_IAM_ARCH = "Identity & Access Management Architect"
ROLE_DEV_LIFECYCLE_ARCH = "Development Lifecycle Architect"
ROLE_SYSTEM_ARCH = "System Architect"
ROLE_APP_ARCH = "Application Architect"
ROLE_CTA = "Technical Architect (CTA)"
ROLE_SALES_CLOUD_CONSULTANT = "Sales Cloud Consultant"
ROLE_SERVICE_CLOUD_CONSULTANT = "Service Cloud Consultant"
ROLE_FIELD_SERVICE_CONSULTANT = "Field Service Consultant"
ROLE_EXPERIENCE_CLOUD_CONSULTANT = "Experience Cloud Consultant"
ROLE_MARKETING_CLOUD_CONSULTANT = "Marketing Cloud Consultant"
ROLE_MARKETING_CLOUD_ADMIN = "Marketing Cloud Administrator"
ROLE_MARKETING_CLOUD_DEV = "Marketing Cloud Developer"
ROLE_PARDOT_CONSULTANT = "Pardot Consultant"
ROLE_DATA_CLOUD_CONSULTANT = "Data Cloud Consultant"
ROLE_EINSTEIN_ANALYTICS_CONSULTANT = "Einstein Analytics Consultant"
ROLE_B2C_COMMERCE_DEV = "B2C Commerce Developer"
ROLE_OMNISTUDIO_CONSULTANT = "OmniStudio Consultant"

# Type of passive: "automatic" fires on events, "active" requires explicit trigger
ROLE_PASSIVE_TYPE = {
    ROLE_ADMINISTRATOR: "active",
    ROLE_ADVANCED_ADMINISTRATOR: "active",
    ROLE_PLATFORM_DEV_I: "automatic",
    ROLE_PLATFORM_DEV_II: "automatic",
    ROLE_JS_DEV_I: "automatic",
    ROLE_INTEGRATION_ARCH: "active",
    ROLE_DATA_ARCH: "active",
    ROLE_SHARING_VISIBILITY_ARCH: "automatic",
    ROLE_IAM_ARCH: "automatic",
    ROLE_DEV_LIFECYCLE_ARCH: "automatic",
    ROLE_SYSTEM_ARCH: "automatic",
    ROLE_APP_ARCH: "automatic",
    ROLE_CTA: "automatic",
    ROLE_SALES_CLOUD_CONSULTANT: "automatic",
    ROLE_SERVICE_CLOUD_CONSULTANT: "automatic",
    ROLE_FIELD_SERVICE_CONSULTANT: "automatic",
    ROLE_EXPERIENCE_CLOUD_CONSULTANT: "active",
    ROLE_MARKETING_CLOUD_CONSULTANT: "active",
    ROLE_MARKETING_CLOUD_ADMIN: "active",
    ROLE_MARKETING_CLOUD_DEV: "automatic",
    ROLE_PARDOT_CONSULTANT: "automatic",
    ROLE_DATA_CLOUD_CONSULTANT: "active",
    ROLE_EINSTEIN_ANALYTICS_CONSULTANT: "active",
    ROLE_B2C_COMMERCE_DEV: "automatic",
    ROLE_OMNISTUDIO_CONSULTANT: "automatic",
}


def get_seniority_rank(seniority_value: str) -> int:
    """Returns 1-4 based on seniority string or enum value."""
    _map = {
        "junior": 1,
        "experienced": 2,
        "senior": 3,
        "evangelist": 4,
    }
    if seniority_value is None:
        return 0
    # Handle both string and enum (via .value or str())
    val = seniority_value if isinstance(seniority_value, str) else str(seniority_value)
    val = val.lower()
    return _map.get(val, 0)


# --- Automatic passive hooks (called from handlers) ---

def on_roll_result(player, roll_value: int) -> dict:
    """
    Called after a dice roll during combat.
    Returns a dict with bonus effects to apply.
    Keys: extra_boss_hp_damage (int)
    """
    role = getattr(player, "role", "") or ""
    result = {"extra_boss_hp_damage": 0}
    if role == ROLE_PLATFORM_DEV_I:
        if roll_value == 10:
            result["extra_boss_hp_damage"] = 1  # total 2 instead of 1
    elif role == ROLE_PLATFORM_DEV_II:
        if roll_value == 10:
            result["extra_boss_hp_damage"] = 2  # total 3
        elif roll_value == 9:
            result["extra_boss_hp_damage"] = 1  # total 2
    elif role == ROLE_CTA:
        # CTA has Platform Dev II ability, but only fires on roll=10, every other activation
        cs = player.combat_state or {}
        cta_last = cs.get("cta_platform_last_turn", -1)
        current_turn = cs.get("turn_number", 0)
        if cta_last != current_turn:
            if roll_value == 10:
                result["extra_boss_hp_damage"] = 1
    return result


def is_immune_to_licenze_theft(player) -> bool:
    """IAM Architect (and CTA) is immune to licenze theft."""
    role = getattr(player, "role", "") or ""
    return role in (ROLE_IAM_ARCH, ROLE_CTA)


def get_addon_cost(player, base_cost: int) -> int:
    """Dev Lifecycle Architect (and CTA every-other time) pay 8L instead of base cost."""
    role = getattr(player, "role", "") or ""
    if role == ROLE_DEV_LIFECYCLE_ARCH:
        return 8
    if role == ROLE_CTA:
        # CTA at 50%: every other addon purchase is discounted
        cs = player.combat_state or {}
        if not cs.get("cta_lifecycle_used_this_addon"):
            return 8
    return base_cost


def get_cards_per_turn(player) -> int:
    """JavaScript Developer I can play 3 cards per turn."""
    role = getattr(player, "role", "") or ""
    if role == ROLE_JS_DEV_I:
        return 3
    return 2


def on_boss_defeated(player) -> dict:
    """Called when a player defeats a boss. Returns extra rewards."""
    role = getattr(player, "role", "") or ""
    result = {"extra_licenze": 0, "extra_cards": 0}
    if role == ROLE_SALES_CLOUD_CONSULTANT:
        result["extra_licenze"] = 1
    elif role == ROLE_B2C_COMMERCE_DEV:
        result["extra_cards"] = 1
    elif role == ROLE_CTA:
        cs = player.combat_state or {}
        if not cs.get("cta_sales_used_last_combat"):
            result["extra_licenze"] = 1
    return result


def on_opponent_boss_defeated(watcher_player) -> dict:
    """Called for each other player when someone else defeats a boss. Returns extra rewards."""
    role = getattr(watcher_player, "role", "") or ""
    result = {"extra_licenze": 0}
    if role == ROLE_PARDOT_CONSULTANT:
        result["extra_licenze"] = 1
    return result


def get_offensive_card_bonus_damage(player) -> int:
    """Marketing Cloud Developer deals +1 damage on offensive cards."""
    role = getattr(player, "role", "") or ""
    if role == ROLE_MARKETING_CLOUD_DEV:
        return 1
    return 0


def can_buy_addon_during_combat(player) -> bool:
    """OmniStudio Consultant can buy addons during combat."""
    role = getattr(player, "role", "") or ""
    return role == ROLE_OMNISTUDIO_CONSULTANT


def sharing_visibility_counter_chance() -> tuple:
    """Returns (threshold, max_roll) for Sharing & Visibility Architect counter.
    Roll d10: 1-3 means the card fails. Returns (3, 10)."""
    return (3, 10)


def should_recover_hp_at_round(player, round_number: int) -> int:
    """Service Cloud Consultant recovers 1 HP after round 3 (once per combat)."""
    role = getattr(player, "role", "") or ""
    if role == ROLE_SERVICE_CLOUD_CONSULTANT:
        cs = player.combat_state or {}
        if round_number >= 3 and not cs.get("service_cloud_hp_recovered"):
            return 1
    return 0
