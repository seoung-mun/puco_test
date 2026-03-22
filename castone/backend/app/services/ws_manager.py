from fastapi import WebSocket
from typing import Dict, Set
import asyncio
import json
import redis.asyncio as async_redis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.redis = async_redis.from_url(REDIS_URL)

    async def connect(self, game_id: str, websocket: WebSocket):
        await websocket.accept()
        print(f"WS Connected: {game_id}")
        if game_id not in self.active_connections:
            self.active_connections[game_id] = set()
            # Start pub/sub listener for this game if this is the first connection
            asyncio.create_task(self._redis_listener(game_id))
        self.active_connections[game_id].add(websocket)

    def disconnect(self, game_id: str, websocket: WebSocket):
        print(f"WS Disconnected: {game_id}")
        if game_id in self.active_connections:
            self.active_connections[game_id].remove(websocket)
            if not self.active_connections[game_id]:
                del self.active_connections[game_id]

    async def _redis_listener(self, game_id: str):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"game:{game_id}:events")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"].decode("utf-8")
                    await self._broadcast(game_id, data)
                if game_id not in self.active_connections:
                    break
        except Exception as e:
            print(f"Redis Listener Error for {game_id}: {e}")
        finally:
            await pubsub.unsubscribe(f"game:{game_id}:events")
            print(f"Redis Listener Stopped: {game_id}")

    async def broadcast_to_game(self, game_id: str, message: dict):
        """Directly broadcast a message without Redis (Fallback)"""
        await self._broadcast(game_id, json.dumps(message))

    async def _broadcast(self, game_id: str, message: str):
        if game_id in self.active_connections:
            for connection in self.active_connections[game_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    # Connection closed or dead
                    pass

manager = ConnectionManager()
