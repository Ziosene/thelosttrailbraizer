"""
Seed script: parse the three .md card files and insert all cards into the DB.

Usage (from backend/ directory):
    python scripts/seed_cards.py

Cards already present (matched by number) are skipped — safe to re-run.
"""

import os
import re
import sys

# Ensure the app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from app.database import SessionLocal, engine
from app.models import ActionCard, BossCard, AddonCard  # triggers table registration
from app.models.card import Rarity, AddonType
from app.database import Base

# Create tables if they don't exist (useful before first Alembic migration)
Base.metadata.create_all(bind=engine)

# Docker mounts cards at /cards; locally they are ../../../cards relative to this script
_DOCKER_CARDS = "/cards"
_LOCAL_CARDS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "cards",
)
CARDS_DIR = _DOCKER_CARDS if os.path.isdir(_DOCKER_CARDS) else _LOCAL_CARDS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _field(lines: list[str], key: str) -> str:
    """Extract value from a '- **Key**: Value' line."""
    for line in lines:
        m = re.match(rf"\s*-\s*\*\*{re.escape(key)}\*\*:\s*(.*)", line, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _rarity(raw: str) -> Rarity:
    mapping = {
        "comune": Rarity.comune,
        "non comune": Rarity.non_comune,
        "raro": Rarity.raro,
        "leggendario": Rarity.leggendario,
    }
    return mapping.get(raw.lower().strip(), Rarity.comune)


def _copies_from_rarity(r: Rarity) -> int:
    return {
        Rarity.comune: 3,
        Rarity.non_comune: 2,
        Rarity.raro: 1,
        Rarity.leggendario: 1,
    }[r]


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_action_cards(path: str) -> list[dict]:
    cards = []
    with open(path, encoding="utf-8") as f:
        content = f.read()

    # Each card starts with "### N. Name"
    blocks = re.split(r"\n(?=### \d+\.)", content)
    for block in blocks:
        header = re.match(r"### (\d+)\.\s+(.+)", block.strip())
        if not header:
            continue
        number = int(header.group(1))
        name = header.group(2).strip()
        lines = block.splitlines()

        tipo = _field(lines, "Tipo")
        quando = _field(lines, "Quando")
        effetto = _field(lines, "Effetto")
        rarità_raw = _field(lines, "Rarità")
        rar = _rarity(rarità_raw)

        cards.append({
            "number": number,
            "name": name,
            "card_type": tipo or "Utilità",
            "when": quando or "In qualsiasi momento",
            "effect": effetto or "",
            "rarity": rar,
            "copies": _copies_from_rarity(rar),
        })
    return cards


def parse_boss_cards(path: str) -> list[dict]:
    cards = []
    with open(path, encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n(?=### \d+\.)", content)
    for block in blocks:
        header = re.match(r"### (\d+)\.\s+(.+)", block.strip())
        if not header:
            continue
        number = int(header.group(1))
        name = header.group(2).strip()
        lines = block.splitlines()

        hp_raw = _field(lines, "HP")
        soglia_raw = _field(lines, "Soglia dado")
        abilita = _field(lines, "Abilità")
        ricompensa_raw = _field(lines, "Ricompensa")
        difficolta = _field(lines, "Difficoltà")

        # HP
        try:
            hp = int(re.search(r"\d+", hp_raw).group())
        except (AttributeError, ValueError):
            hp = 3

        # Dice threshold — "6+" → 6
        try:
            threshold = int(re.search(r"\d+", soglia_raw).group())
        except (AttributeError, ValueError):
            threshold = 6

        # Reward licenze
        try:
            reward_licenze = int(re.search(r"\d+", ricompensa_raw).group())
        except (AttributeError, ValueError):
            reward_licenze = 3

        # Certification
        has_cert = "certificazione" in ricompensa_raw.lower()

        cards.append({
            "number": number,
            "name": name,
            "hp": hp,
            "dice_threshold": threshold,
            "ability": abilita or "",
            "reward_licenze": reward_licenze,
            "has_certification": has_cert,
            "difficulty": difficolta or "Media",
        })
    return cards


def parse_addon_cards(path: str) -> list[dict]:
    cards = []
    with open(path, encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n(?=### \d+\.)", content)
    for block in blocks:
        header = re.match(r"### (\d+)\.\s+(.+)", block.strip())
        if not header:
            continue
        number = int(header.group(1))
        name = header.group(2).strip()
        lines = block.splitlines()

        tipo = _field(lines, "Tipo")
        effetto = _field(lines, "Effetto")
        sinergia = _field(lines, "Sinergia") or None
        rarità_raw = _field(lines, "Rarità")
        rar = _rarity(rarità_raw)

        addon_type = AddonType.attivo if tipo.lower().strip() == "attivo" else AddonType.passivo

        cards.append({
            "number": number,
            "name": name,
            "addon_type": addon_type,
            "effect": effetto or "",
            "synergy": sinergia,
            "rarity": rar,
            "cost": 10,
        })
    return cards


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed():
    db = SessionLocal()
    try:
        existing_action = {c.number for c in db.query(ActionCard.number).all()}
        existing_boss = {c.number for c in db.query(BossCard.number).all()}
        existing_addon = {c.number for c in db.query(AddonCard.number).all()}

        # --- Action Cards ---
        action_path = os.path.join(CARDS_DIR, "action_cards.md")
        action_cards = parse_action_cards(action_path)
        inserted_action = 0
        for card in action_cards:
            if card["number"] in existing_action:
                continue
            db.add(ActionCard(**card))
            inserted_action += 1
        db.commit()
        print(f"Action cards: {inserted_action} inserted, {len(action_cards) - inserted_action} skipped")

        # --- Boss Cards ---
        boss_path = os.path.join(CARDS_DIR, "boss_cards.md")
        boss_cards = parse_boss_cards(boss_path)
        inserted_boss = 0
        updated_boss = 0
        for card in boss_cards:
            if card["number"] in existing_boss:
                # Update mutable balance fields (hp, dice_threshold) on existing records
                existing = db.query(BossCard).filter(BossCard.number == card["number"]).first()
                if existing and (
                    existing.hp != card["hp"]
                    or existing.dice_threshold != card["dice_threshold"]
                    or existing.has_certification != card["has_certification"]
                    or existing.reward_licenze != card["reward_licenze"]
                ):
                    existing.hp = card["hp"]
                    existing.dice_threshold = card["dice_threshold"]
                    existing.has_certification = card["has_certification"]
                    existing.reward_licenze = card["reward_licenze"]
                    updated_boss += 1
                continue
            db.add(BossCard(**card))
            inserted_boss += 1
        db.commit()
        print(f"Boss cards:   {inserted_boss} inserted, {updated_boss} updated, {len(boss_cards) - inserted_boss - updated_boss} skipped")

        # --- Addon Cards ---
        addon_path = os.path.join(CARDS_DIR, "addon_cards.md")
        addon_cards = parse_addon_cards(addon_path)
        inserted_addon = 0
        for card in addon_cards:
            if card["number"] in existing_addon:
                continue
            db.add(AddonCard(**card))
            inserted_addon += 1
        db.commit()
        print(f"Addon cards:  {inserted_addon} inserted, {len(addon_cards) - inserted_addon} skipped")

        total = inserted_action + inserted_boss + inserted_addon
        print(f"\nDone. Total inserted: {total}")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
