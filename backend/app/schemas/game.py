from pydantic import BaseModel
from typing import Optional
from app.models.game import GameStatus, TurnPhase, Seniority


class CreateGame(BaseModel):
    max_players: int = 4


class JoinGame(BaseModel):
    code: str


class GameInfo(BaseModel):
    id: int
    code: str
    status: GameStatus
    max_players: int
    player_count: int

    model_config = {"from_attributes": True}


class PlayerState(BaseModel):
    id: int
    user_id: int
    nickname: str
    seniority: Optional[Seniority] = None
    role: Optional[str] = None
    hp: int
    max_hp: int
    licenze: int
    certificazioni: int
    hand_count: int
    addon_count: int
    is_in_combat: bool
    bosses_defeated: int

    model_config = {"from_attributes": True}


class GameState(BaseModel):
    id: int
    code: str
    status: GameStatus
    current_phase: TurnPhase
    turn_number: int
    current_player_id: Optional[int]
    players: list[PlayerState]
    action_deck_count: int
    boss_deck_count: int
    addon_deck_count: int

    model_config = {"from_attributes": True}
