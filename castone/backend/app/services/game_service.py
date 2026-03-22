import json
import logging
from uuid import UUID, uuid4
from typing import Dict, List
import redis
import os
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.engine_wrapper.wrapper import create_game_engine, EngineWrapper
from app.db.models import GameSession, GameLog
from app.schemas.game import GameRoomCreate
from app.services.ws_manager import manager
import asyncio

# Redis setup
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL)

class GameService:
    # In-memory store for active engines (Class variable to persist between requests)
    active_engines: Dict[UUID, EngineWrapper] = {}

    def __init__(self, db: Session):
        self.db = db

    def create_room(self, room_info: GameRoomCreate) -> GameSession:
        room = GameSession(
            id=uuid4(),
            title=room_info.title,
            status="WAITING",
            num_players=room_info.max_players
        )
        self.db.add(room)
        self.db.commit()
        self.db.refresh(room)
        return room

    def start_game(self, game_id: UUID):
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        if not room:
            raise ValueError("Game not found")
        
        # Initialize engine
        engine = create_game_engine(num_players=room.num_players)
        GameService.active_engines[game_id] = engine
        
        room.status = "PROGRESS"
        self.db.commit()
        
        # Store initial state in Redis if needed for websocket
        state = engine.get_state()
        action_mask = engine.get_action_mask()
        self._sync_to_redis(game_id, state, action_mask)

        # Trigger Bot if first player is a bot
        self._schedule_next_bot_turn_if_needed(game_id, room, engine)

        return {"state": state, "action_mask": action_mask}

    def process_action(self, game_id: UUID, actor_id: str, action: int):
        engine = GameService.active_engines.get(game_id)
        if not engine:
            raise ValueError(f"Active game engine not found for game {game_id}")

        # TDD Defense: Validate action against the current action mask
        current_mask = engine.get_action_mask()
        if not (0 <= action < len(current_mask)) or not current_mask[action]:
            raise ValueError(f"Action {action} is invalid for the current state.")

        # Step through engine (wrapper handles snapshot & logging prep)
        result = engine.step(action)
        
        # Async MLOps Logging
        from app.services.ml_logger import MLLogger
        import asyncio
        import copy
        
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                MLLogger.log_transition(
                    game_id=game_id,
                    actor_id=actor_id,
                    state_before=copy.deepcopy(result["state_before"]),
                    action=action,
                    reward=result["reward"],
                    done=result["done"],
                    state_after=copy.deepcopy(result["state_after"]),
                    info=copy.deepcopy(result["info"])
                )
            )
        except RuntimeError:
            pass # No running loop (e.g. synch fallback test scripts)
        
        # Save Log to DB
        game_log = GameLog(
            game_id=game_id,
            round=result["info"].get("round", 0),
            step=result["info"].get("step", 0),
            actor_id=actor_id,
            action_data={"action": action},
            available_options=result["action_mask"],
            state_before=result["state_before"],
            state_after=result["state_after"]
        )
        self.db.add(game_log)
        
        # Load the room to check players (for bot scheduling)
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        if result["done"] and room:
            room.status = "FINISHED"
            
            # Simple tie-break for MVP winner storing: 
            # We assume engine.get_scores() or similar exists. For now just set FINISHED.

        self.db.commit()

        # Update Redis for WebSocket broadcast (Bot actions are also blasted through this channel)
        new_action_mask = engine.get_action_mask()
        self._sync_to_redis(game_id, result["state_after"], new_action_mask)

        # Trigger Bot if next player is bot
        if not result["done"] and room:
            self._schedule_next_bot_turn_if_needed(game_id, room, engine)

        return {"state": result["state_after"], "action_mask": new_action_mask}
        
    def _schedule_next_bot_turn_if_needed(self, game_id: UUID, room: GameSession, engine: EngineWrapper):
        next_idx = engine.env.game.current_player_idx
        if not room.players or next_idx >= len(room.players):
            return
            
        next_actor = room.players[next_idx]
        if str(next_actor).startswith("BOT_"):
            from app.services.bot_service import BotService
            from app.dependencies import SessionLocal
            import asyncio

            def sync_callback(bg_game_id, bg_actor_id, bg_action):
                with SessionLocal() as bg_db:
                    bg_service = GameService(bg_db)
                    bg_service.process_action(bg_game_id, bg_actor_id, bg_action)

            asyncio.create_task(
                BotService.run_bot_turn(
                    game_id=game_id, 
                    engine=engine, 
                    actor_id=next_actor, 
                    process_action_callback=sync_callback
                )
            )

    def _sync_to_redis(self, game_id: UUID, state: Dict, action_mask=None):
        data = {"type": "STATE_UPDATE", "data": state, "action_mask": action_mask or []}
        # 1. Redis sync (Will fail gracefully if Redis is down)
        try:
            redis_client.set(f"game:{game_id}:state", json.dumps(state))
            redis_client.publish(f"game:{game_id}:events", json.dumps(data))
        except Exception as e:
            logger.warning("Redis sync failed: %s", e)

        # 2. Direct In-Memory Broadcast (Fallback for single-instance development)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast_to_game(str(game_id), data))
        except Exception as e:
            logger.warning("Direct broadcast failed: %s", e)

    def get_room_list(self) -> List[GameSession]:
        return self.db.query(GameSession).all()
