from pydantic import BaseModel, field_validator
from datetime import datetime


class UserRegister(BaseModel):
    nickname: str
    password: str

    @field_validator("nickname")
    @classmethod
    def nickname_length(cls, v: str) -> str:
        if not 3 <= len(v) <= 50:
            raise ValueError("nickname must be 3–50 characters")
        return v

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("password must be at least 6 characters")
        return v


class UserLogin(BaseModel):
    nickname: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserPublic(BaseModel):
    id: int
    nickname: str
    elo_rating: int
    games_played: int
    games_won: int
    created_at: datetime

    model_config = {"from_attributes": True}
