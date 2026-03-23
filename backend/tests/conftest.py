"""
Configurazione pytest globale.

IMPORTANTE: le variabili d'ambiente devono essere settate PRIMA di qualsiasi
import di `app.*` perché pydantic-settings legge DATABASE_URL a tempo di import.
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SECRET_KEY", "pytest-secret-key")

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import pytest

from app.database import Base
# Importa i modelli reali PRIMA che test_engine.py possa iniettare il suo mock via sys.modules
import app.models.game  # noqa: F401 — side effect: registra le tabelle e blocca il mock
from app.models.card import ActionCard, BossCard, AddonCard
from app.models.game import GameSession, GamePlayer, PlayerAddon, PlayerHandCard

# Engine SQLite in-memory condiviso da tutti i test (StaticPool = stessa connessione)
_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    """Crea le tabelle e fa il seed delle carte reali una sola volta per sessione."""
    Base.metadata.create_all(_TEST_ENGINE)
    _seed_cards_into_test_db()
    yield
    Base.metadata.drop_all(_TEST_ENGINE)


def _seed_cards_into_test_db():
    """
    Popola il DB di test con le carte reali dai file .md.
    Riusa i parser del seed script senza toccare il DB di produzione.
    """
    # Import del parser (non del seed che usa SessionLocal di prod)
    from scripts.seed_cards import (
        parse_action_cards, parse_boss_cards, parse_addon_cards, CARDS_DIR
    )
    import os as _os

    action_path = _os.path.join(CARDS_DIR, "action_cards.md")
    boss_path = _os.path.join(CARDS_DIR, "boss_cards.md")
    addon_path = _os.path.join(CARDS_DIR, "addon_cards.md")

    with Session(_TEST_ENGINE) as db:
        if not _os.path.exists(action_path):
            return  # carta dir non disponibile (CI senza volume cards)

        for card in parse_action_cards(action_path):
            if not db.query(ActionCard).filter_by(number=card["number"]).first():
                db.add(ActionCard(**card))
        for card in parse_boss_cards(boss_path):
            if not db.query(BossCard).filter_by(number=card["number"]).first():
                db.add(BossCard(**card))
        if _os.path.exists(addon_path):
            from scripts.seed_cards import parse_addon_cards as _parse_addon
            for card in _parse_addon(addon_path):
                if not db.query(AddonCard).filter_by(number=card["number"]).first():
                    db.add(AddonCard(**card))
        db.commit()


@pytest.fixture
def db(_create_schema):
    """
    Session SQLAlchemy per un singolo test.
    Fa rollback automatico alla fine per isolare i test.
    """
    with Session(_TEST_ENGINE) as session:
        yield session
        session.rollback()
