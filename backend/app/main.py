from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models.user import User
from app.websocket.manager import manager
from app.websocket.game_handler import handle_message
from app.api.routes import auth, users, games

app = FastAPI(title="The Lost Trailbraizer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(games.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/{game_code}")
async def websocket_endpoint(
    websocket: WebSocket,
    game_code: str,
    token: str,
    db: Session = Depends(get_db),
):
    # Authenticate via query param ?token=...
    try:
        from jose import jwt, JWTError
        from app.config import settings
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = int(payload["sub"])
        user = db.get(User, user_id)
        if not user:
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await manager.connect(game_code, user_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            await handle_message(game_code, user_id, raw, db)
    except WebSocketDisconnect:
        manager.disconnect(game_code, user_id)
        await manager.broadcast(game_code, {
            "type": "player_left",
            "user_id": user_id,
        })
