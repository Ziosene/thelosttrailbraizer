from sqlalchemy import String, Integer, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from app.database import Base


class Rarity(str, enum.Enum):
    comune = "Comune"
    non_comune = "Non comune"
    raro = "Raro"
    leggendario = "Leggendario"


class ActionCardType(str, enum.Enum):
    offensiva = "Offensiva"
    difensiva = "Difensiva"
    economica = "Economica"
    manipolazione = "Manipolazione dado"
    interferenza = "Interferenza"
    utilita = "Utilità"


class AddonType(str, enum.Enum):
    passivo = "Passivo"
    attivo = "Attivo"


class ActionCard(Base):
    __tablename__ = "action_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    card_type: Mapped[str] = mapped_column(String(50), nullable=False)
    when: Mapped[str] = mapped_column(String(200), nullable=False)
    effect: Mapped[str] = mapped_column(Text, nullable=False)
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity), nullable=False)
    # copies in the shared deck: Comune=3, Non comune=2, Raro=1, Leggendario=1
    copies: Mapped[int] = mapped_column(Integer, default=2)


class BossCard(Base):
    __tablename__ = "boss_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hp: Mapped[int] = mapped_column(Integer, nullable=False)
    dice_threshold: Mapped[int] = mapped_column(Integer, nullable=False)  # e.g. 6 means "6+"
    ability: Mapped[str] = mapped_column(Text, nullable=False)
    reward_licenze: Mapped[int] = mapped_column(Integer, nullable=False)
    has_certification: Mapped[bool] = mapped_column(default=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False)  # Facile/Media/Alta/Leggendaria


class AddonCard(Base):
    __tablename__ = "addon_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    addon_type: Mapped[AddonType] = mapped_column(Enum(AddonType), nullable=False)
    effect: Mapped[str] = mapped_column(Text, nullable=False)
    synergy: Mapped[str | None] = mapped_column(Text, nullable=True)
    rarity: Mapped[Rarity] = mapped_column(Enum(Rarity), nullable=False)
    cost: Mapped[int] = mapped_column(Integer, default=10)
