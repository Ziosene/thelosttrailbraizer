import random
import string

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.game import GameSession, GamePlayer, GameStatus
from app.auth import get_current_user
from app.schemas.game import CreateGame, GameInfo

router = APIRouter(prefix="/games", tags=["games"])


def _generate_code(length: int = 8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


@router.post("", response_model=GameInfo, status_code=201)
def create_game(
    body: CreateGame,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not 2 <= body.max_players <= 4:
        raise HTTPException(status_code=400, detail="max_players must be 2–4")

    code = _generate_code()
    while db.query(GameSession).filter(GameSession.code == code).first():
        code = _generate_code()

    game = GameSession(code=code, max_players=body.max_players)
    db.add(game)
    db.commit()
    db.refresh(game)

    result = GameInfo(
        id=game.id,
        code=game.code,
        status=game.status,
        max_players=game.max_players,
        player_count=0,
    )
    return result


@router.get("", response_model=list[GameInfo])
def list_open_games(db: Session = Depends(get_db)):
    """Return all lobbies currently open (waiting for players)."""
    games = (
        db.query(GameSession)
        .filter(GameSession.status == GameStatus.waiting)
        .order_by(GameSession.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        GameInfo(
            id=g.id,
            code=g.code,
            status=g.status,
            max_players=g.max_players,
            player_count=len(g.players),
        )
        for g in games
    ]


@router.get("/{code}", response_model=GameInfo)
def get_game(code: str, db: Session = Depends(get_db)):
    game = db.query(GameSession).filter(GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return GameInfo(
        id=game.id,
        code=game.code,
        status=game.status,
        max_players=game.max_players,
        player_count=len(game.players),
    )
