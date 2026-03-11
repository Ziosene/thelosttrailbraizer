from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserPublic

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/leaderboard", response_model=list[UserPublic])
def leaderboard(limit: int = 20, db: Session = Depends(get_db)):
    return (
        db.query(User)
        .order_by(User.elo_rating.desc())
        .limit(limit)
        .all()
    )


@router.get("/{nickname}", response_model=UserPublic)
def get_user(nickname: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.nickname == nickname).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
