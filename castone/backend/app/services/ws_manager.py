import logging
from fastapi import WebSocket
from typing import Dict, Optional, Set
import asyncio
import json
from itertools import count

from app.core.redis import async_redis_client
from app.dependencies import SessionLocal

logger = logging.getLogger(__name__)

DISCONNECT_TIMEOUT_SECONDS = 600  # 10 minutes


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.redis = async_redis_client
        # Track player_id -> websocket mapping per game
        self.player_connections: Dict[str, Dict[str, WebSocket]] = {}
        # Track disconnect timers per game:player
        self._disconnect_timers: Dict[str, asyncio.Task] = {}
        self._conn_ids: Dict[int, str] = {}
        self._conn_seq = count(1)

    def _get_connection_id(self, websocket: WebSocket) -> str:
        ws_key = id(websocket)
        existing = self._conn_ids.get(ws_key)
        if existing:
            return existing
        conn_id = f"ws-{next(self._conn_seq)}"
        self._conn_ids[ws_key] = conn_id
        return conn_id

    async def connect(self, game_id: str, websocket: WebSocket, player_id: Optional[str] = None):
        conn_id = self._get_connection_id(websocket)
        logger.warning("[WS_TRACE] ws_connect game=%s connection_id=%s user_id=%s", game_id, conn_id, player_id)

        if game_id not in self.active_connections:
            self.active_connections[game_id] = set()
            logger.warning("[WS_TRACE] ws_subscribe game_id=%s connection_id=%s user_id=%s", game_id, conn_id, player_id)
            asyncio.create_task(self._redis_listener(game_id))
        self.active_connections[game_id].add(websocket)

        # Track player connection
        if player_id:
            if game_id not in self.player_connections:
                self.player_connections[game_id] = {}
            self.player_connections[game_id][player_id] = websocket

            await self.redis.hset(f"game:{game_id}:players", player_id, "connected")
            await self.redis.expire(f"game:{game_id}:players", 900)

            # Cancel any pending disconnect timer for this player
            timer_key = f"{game_id}:{player_id}"
            if timer_key in self._disconnect_timers:
                self._disconnect_timers[timer_key].cancel()
                del self._disconnect_timers[timer_key]
                logger.info("Player reconnected, timer cancelled: game=%s player=%s", game_id, player_id)

    async def disconnect(self, game_id: str, websocket: WebSocket, player_id: Optional[str] = None):
        conn_id = self._get_connection_id(websocket)
        logger.warning("[WS_TRACE] ws_disconnect game=%s connection_id=%s user_id=%s", game_id, conn_id, player_id)

        if game_id in self.active_connections:
            self.active_connections[game_id].discard(websocket)
            if not self.active_connections[game_id]:
                del self.active_connections[game_id]
        self._conn_ids.pop(id(websocket), None)

        # Update player status and handle disconnect logic
        if player_id:
            if game_id in self.player_connections:
                self.player_connections[game_id].pop(player_id, None)
                if not self.player_connections[game_id]:
                    del self.player_connections[game_id]

            await self.redis.hset(f"game:{game_id}:players", player_id, "disconnected")
            await self._handle_player_disconnect(game_id, player_id)

    async def _handle_player_disconnect(self, game_id: str, disconnected_player_id: str):
        """Handle player disconnect: notify others and start auto-end timer."""
        try:
            meta = await self.redis.hgetall(f"game:{game_id}:meta")
            if not meta:
                return

            status = meta.get(b"status", b"").decode()
            if status != "PROGRESS":
                return

            human_count = int(meta.get(b"human_count", b"0").decode())

            # Notify remaining players about the disconnect
            disconnect_msg: dict[str, object] = {
                "type": "PLAYER_DISCONNECTED",
                "player_id": disconnected_player_id,
                "message": f"Player {disconnected_player_id} has disconnected.",
            }

            if human_count >= 2:
                # Multi-human game: ask remaining players if they want to end
                disconnect_msg["options"] = ["end_game", "wait"]
                disconnect_msg["timeout_seconds"] = DISCONNECT_TIMEOUT_SECONDS

            await self._broadcast(game_id, json.dumps(disconnect_msg))

            # Start auto-end timer
            timer_key = f"{game_id}:{disconnected_player_id}"
            if timer_key not in self._disconnect_timers:
                task = asyncio.create_task(
                    self._disconnect_timeout(game_id, disconnected_player_id)
                )
                self._disconnect_timers[timer_key] = task

        except Exception as e:
            logger.error("Error handling disconnect for game=%s player=%s: %s", game_id, disconnected_player_id, e)

    async def _disconnect_timeout(self, game_id: str, player_id: str):
        """Wait for timeout then auto-end the game."""
        try:
            await asyncio.sleep(DISCONNECT_TIMEOUT_SECONDS)

            logger.info("Disconnect timeout reached: game=%s player=%s, auto-ending game", game_id, player_id)

            # Check if player is still disconnected
            status = await self.redis.hget(f"game:{game_id}:players", player_id)
            if status and status.decode() == "connected":
                return  # Player reconnected

            # End the game via database update
            from app.db.models import GameSession

            with SessionLocal() as db:
                game = db.query(GameSession).filter(GameSession.id == game_id).first()
                if game and game.status == "PROGRESS":
                    game.status = "FINISHED"
                    game.winner_id = None  # No winner on timeout
                    db.commit()

            # Broadcast game end
            end_msg = {
                "type": "GAME_ENDED",
                "reason": "player_disconnect_timeout",
                "disconnected_player": player_id,
            }
            await self._broadcast(game_id, json.dumps(end_msg))

        except asyncio.CancelledError:
            logger.info("Disconnect timer cancelled: game=%s player=%s", game_id, player_id)
        except Exception as e:
            logger.error("Disconnect timeout error: game=%s player=%s: %s", game_id, player_id, e)
        finally:
            timer_key = f"{game_id}:{player_id}"
            self._disconnect_timers.pop(timer_key, None)

    async def handle_client_message(self, game_id: str, player_id: str, message: dict):
        """Handle incoming WebSocket messages from clients."""
        msg_type = message.get("type")
        logger.warning(
            "[WS_TRACE] ws_receive game=%s user_id=%s message_type=%s",
            game_id,
            player_id,
            msg_type,
        )

        if msg_type == "END_GAME_REQUEST":
            # Player requested to end the game immediately
            logger.info("Player requested game end: game=%s player=%s", game_id, player_id)

            # Cancel all disconnect timers for this game
            keys_to_remove = [k for k in self._disconnect_timers if k.startswith(f"{game_id}:")]
            for key in keys_to_remove:
                self._disconnect_timers[key].cancel()
                del self._disconnect_timers[key]

            # End the game
            from app.dependencies import SessionLocal
            from app.db.models import GameSession

            with SessionLocal() as db:
                game = db.query(GameSession).filter(GameSession.id == game_id).first()
                if game and game.status == "PROGRESS":
                    game.status = "FINISHED"
                    game.winner_id = None
                    db.commit()

            end_msg = {
                "type": "GAME_ENDED",
                "reason": "player_request",
                "requested_by": player_id,
            }
            await self._broadcast(game_id, json.dumps(end_msg))

    async def _redis_listener(self, game_id: str):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"game:{game_id}:events")
        logger.warning("[WS_TRACE] redis_listener_subscribed game_id=%s", game_id)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"].decode("utf-8")
                    logger.warning("[WS_TRACE] redis_listener_message_received game_id=%s", game_id)
                    logger.warning("[WS_TRACE] redis_listener_broadcast_dispatch game_id=%s", game_id)
                    await self._broadcast(game_id, data)
                if game_id not in self.active_connections:
                    break
        except Exception as e:
            logger.error("Redis listener error for %s: %s", game_id, e)
        finally:
            await pubsub.unsubscribe(f"game:{game_id}:events")
            logger.debug("Redis listener stopped: %s", game_id)

    async def broadcast_to_game(self, game_id: str, message: dict):
        """Directly broadcast a message without Redis (Fallback)"""
        message_type = message.get("type") if isinstance(message, dict) else None
        logger.warning("[WS_TRACE] ws_broadcast_start game_id=%s source=direct message_type=%s", game_id, message_type)
        await self._broadcast(game_id, json.dumps(message))
        logger.warning(
            "[WS_TRACE] ws_broadcast_end game_id=%s source=direct message_type=%s connection_count=%d",
            game_id,
            message_type,
            len(self.active_connections.get(game_id, set())),
        )

    async def _broadcast(self, game_id: str, message: str):
        message_type = None
        try:
            parsed = json.loads(message)
            if isinstance(parsed, dict):
                message_type = parsed.get("type")
        except Exception:
            pass
        if game_id in self.active_connections:
            logger.warning(
                "[WS_TRACE] ws_broadcast_start game_id=%s source=manager message_type=%s connection_count=%d",
                game_id,
                message_type,
                len(self.active_connections[game_id]),
            )
            for connection in self.active_connections[game_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    logger.warning("[WS_TRACE] ws_broadcast_error game_id=%s message_type=%s error=send_failed", game_id, message_type, exc_info=True)
            logger.warning(
                "[WS_TRACE] ws_broadcast_end game_id=%s source=manager message_type=%s connection_count=%d",
                game_id,
                message_type,
                len(self.active_connections[game_id]),
            )
        else:
            logger.warning("[WS_TRACE] ws_broadcast_end game_id=%s source=manager message_type=%s connection_count=0", game_id, message_type)


manager = ConnectionManager()
