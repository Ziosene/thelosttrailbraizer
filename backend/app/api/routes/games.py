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


@router.get("/mine", response_model=list[GameInfo])
def list_my_games(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return in_progress games where the current user is a player."""
    players = (
        db.query(GamePlayer)
        .filter(GamePlayer.user_id == current_user.id)
        .all()
    )
    game_ids = [p.game_id for p in players]
    if not game_ids:
        return []
    games = (
        db.query(GameSession)
        .filter(
            GameSession.id.in_(game_ids),
            GameSession.status.in_([GameStatus.waiting, GameStatus.in_progress]),
        )
        .order_by(GameSession.created_at.desc())
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


@router.delete("/{code}", status_code=204)
def cancel_game(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a waiting game. Only the host can do this, and only if alone."""
    game = db.query(GameSession).filter(GameSession.code == code).first()
    if not game:
        raise HTTPException(status_code=404, detail="Partita non trovata")
    if game.status != GameStatus.waiting:
        raise HTTPException(status_code=400, detail="Solo le partite in attesa possono essere annullate")
    players = list(game.players)
    if len(players) > 1:
        raise HTTPException(status_code=400, detail="Non puoi annullare una partita con altri giocatori")
    if players and players[0].user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Solo il creatore può annullare la partita")
    db.delete(game)
    db.commit()


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
