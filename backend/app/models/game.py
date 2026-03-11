from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.database import Base


class GameStatus(str, enum.Enum):
    waiting = "waiting"      # in lobby, waiting for players
    in_progress = "in_progress"
    finished = "finished"


class TurnPhase(str, enum.Enum):
    draw = "draw"            # mandatory draw
    action = "action"        # play cards / buy addons
    combat = "combat"        # fighting a boss
    end = "end"              # player declared end of turn


class Seniority(str, enum.Enum):
    junior = "Junior"
    experienced = "Experienced"
    senior = "Senior"
    evangelist = "Evangelist"


SENIORITY_HP = {
    Seniority.junior: 1,
    Seniority.experienced: 2,
    Seniority.senior: 3,
    Seniority.evangelist: 4,
}


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, nullable=False)  # invite code
    status: Mapped[GameStatus] = mapped_column(Enum(GameStatus), default=GameStatus.waiting)
    max_players: Mapped[int] = mapped_column(Integer, default=4)
    current_turn_index: Mapped[int] = mapped_column(Integer, default=0)  # index in turn_order
    turn_number: Mapped[int] = mapped_column(Integer, default=0)
    current_phase: Mapped[TurnPhase] = mapped_column(Enum(TurnPhase), default=TurnPhase.draw)
    # JSON arrays of card IDs representing the shared decks
    action_deck: Mapped[list] = mapped_column(JSON, default=list)   # ordered list of ActionCard.id
    boss_deck: Mapped[list] = mapped_column(JSON, default=list)     # ordered list of BossCard.id
    addon_deck: Mapped[list] = mapped_column(JSON, default=list)    # ordered list of AddonCard.id
    action_discard: Mapped[list] = mapped_column(JSON, default=list)
    boss_discard: Mapped[list] = mapped_column(JSON, default=list)
    addon_discard: Mapped[list] = mapped_column(JSON, default=list)
    turn_order: Mapped[list] = mapped_column(JSON, default=list)    # list of GamePlayer.id in turn order
    winner_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("game_players.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    players: Mapped[list["GamePlayer"]] = relationship(
        back_populates="game",
        foreign_keys="GamePlayer.game_id",
    )


class GamePlayer(Base):
    """Represents a player's state within a specific game session."""
    __tablename__ = "game_players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_id: Mapped[int] = mapped_column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # Character
    seniority: Mapped[Seniority] = mapped_column(Enum(Seniority), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Platform Developer I"

    # Resources
    hp: Mapped[int] = mapped_column(Integer, nullable=False)        # current HP
    max_hp: Mapped[int] = mapped_column(Integer, nullable=False)    # base HP from seniority
    licenze: Mapped[int] = mapped_column(Integer, default=3)
    certificazioni: Mapped[int] = mapped_column(Integer, default=0)

    # Cards & state
    cards_played_this_turn: Mapped[int] = mapped_column(Integer, default=0)
    is_in_combat: Mapped[bool] = mapped_column(Boolean, default=False)
    current_boss_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("boss_cards.id"), nullable=True)
    current_boss_hp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    combat_round: Mapped[int] = mapped_column(Integer, default=0)

    # Score (for ELO calculation at end)
    score: Mapped[int] = mapped_column(Integer, default=0)
    bosses_defeated: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    game: Mapped["GameSession"] = relationship(back_populates="players", foreign_keys=[game_id])
    user: Mapped["User"] = relationship(back_populates="game_players")
    addons: Mapped[list["PlayerAddon"]] = relationship(back_populates="player")
    hand: Mapped[list["PlayerHandCard"]] = relationship(back_populates="player")


class PlayerAddon(Base):
    """An AddOn card owned by a player in a game."""
    __tablename__ = "player_addons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("game_players.id"), nullable=False)
    addon_id: Mapped[int] = mapped_column(Integer, ForeignKey("addon_cards.id"), nullable=False)
    is_tapped: Mapped[bool] = mapped_column(Boolean, default=False)  # tap/untap mechanic

    player: Mapped["GamePlayer"] = relationship(back_populates="addons")


class PlayerHandCard(Base):
    """An action card in a player's hand."""
    __tablename__ = "player_hand_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int] = mapped_column(Integer, ForeignKey("game_players.id"), nullable=False)
    action_card_id: Mapped[int] = mapped_column(Integer, ForeignKey("action_cards.id"), nullable=False)

    player: Mapped["GamePlayer"] = relationship(back_populates="hand")
