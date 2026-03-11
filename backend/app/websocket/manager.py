from fastapi import WebSocket
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections grouped by game session."""

    def __init__(self):
        # { game_code: { user_id: WebSocket } }
        self.rooms: dict[str, dict[int, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, game_code: str, user_id: int):
        await websocket.accept()
        if game_code not in self.rooms:
            self.rooms[game_code] = {}
        self.rooms[game_code][user_id] = websocket
        logger.info(f"User {user_id} connected to game {game_code}")

    def disconnect(self, game_code: str, user_id: int):
        if game_code in self.rooms:
            self.rooms[game_code].pop(user_id, None)
            if not self.rooms[game_code]:
                del self.rooms[game_code]
        logger.info(f"User {user_id} disconnected from game {game_code}")

    async def send_to_player(self, game_code: str, user_id: int, message: dict):
        ws = self.rooms.get(game_code, {}).get(user_id)
        if ws:
            await ws.send_text(json.dumps(message))

    async def broadcast(self, game_code: str, message: dict, exclude_user: int | None = None):
        """Send a message to all players in a game room."""
        for uid, ws in self.rooms.get(game_code, {}).items():
            if uid != exclude_user:
                try:
                    await ws.send_text(json.dumps(message))
                except Exception:
                    logger.warning(f"Failed to send to user {uid} in game {game_code}")

    async def broadcast_all(self, game_code: str, message: dict):
        await self.broadcast(game_code, message, exclude_user=None)

    def get_connected_users(self, game_code: str) -> list[int]:
        return list(self.rooms.get(game_code, {}).keys())


manager = ConnectionManager()
