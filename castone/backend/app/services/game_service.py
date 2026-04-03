import asyncio
import json
import logging
from typing import Dict, List
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.redis import sync_redis_client as redis_client
from app.db.models import GameSession, GameLog, User
from app.engine_wrapper.wrapper import create_game_engine, EngineWrapper
from app.schemas.game import GameRoomCreate
from app.services.ws_manager import manager
from app.services.state_serializer import serialize_compact_summary, serialize_game_state_from_engine

logger = logging.getLogger(__name__)

class GameService:
    # In-memory store for active engines (Class variable to persist between requests)
    active_engines: Dict[UUID, EngineWrapper] = {}
    _bot_tasks = set()
    _bot_stall_watchdogs: Dict[str, asyncio.Task] = {}

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

    def _resolve_player_names_and_bots(self, room: GameSession):
        """room.players 목록에서 player_names 리스트와 bot_players 딕셔너리를 반환한다."""
        players = room.players or []
        player_names: List[str] = []
        bot_players: Dict[int, str] = {}
        for i, player_id in enumerate(players):
            pid = str(player_id)
            if pid.startswith("BOT_"):
                bot_type = pid.split("_", 1)[1].lower() if "_" in pid else "random"
                player_names.append(f"Bot ({bot_type})")
                bot_players[i] = bot_type
            else:
                user = self.db.query(User).filter(User.id == player_id).first()
                name = (user.nickname or user.email or f"Player {i}") if user else f"Player {i}"
                player_names.append(name)
        return player_names, bot_players

    def _build_rich_state(self, game_id: UUID, engine: EngineWrapper, room: GameSession) -> Dict:
        """serialize_game_state_from_engine()으로 rich GameState JSON을 생성한다."""
        player_names, bot_players = self._resolve_player_names_and_bots(room)
        return serialize_game_state_from_engine(
            engine=engine,
            player_names=player_names,
            game_id=str(game_id),
            bot_players=bot_players,
        )

    def start_game(self, game_id: UUID):
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        if not room:
            raise ValueError("Game not found")

        actual_players = len(room.players or [])
        if actual_players < 3:
            raise ValueError(f"Need at least 3 players to start, currently {actual_players}")

        # Initialize engine with actual number of players
        engine = create_game_engine(num_players=actual_players)
        GameService.active_engines[game_id] = engine

        room.status = "PROGRESS"
        self.db.commit()

        # Build rich state and broadcast
        rich_state = self._build_rich_state(game_id, engine, room)
        action_mask = rich_state.get("action_mask", engine.get_action_mask())
        self._store_game_meta(game_id, room)
        self._sync_to_redis(game_id, rich_state)

        # Trigger Bot if first player is a bot
        self._schedule_next_bot_turn_if_needed(game_id, room, engine)

        return {"state": rich_state, "action_mask": action_mask}

    def process_action(self, game_id: UUID, actor_id: str, action: int):
        logger.warning(
            "[STATE_TRACE] process_action_enter game=%s actor=%s action=%s",
            game_id,
            actor_id,
            action,
        )
        logger.warning(
            "[BOT_TRACE] process_action_enter game=%s actor=%s action=%s",
            game_id,
            actor_id,
            action,
        )
        engine = GameService.active_engines.get(game_id)
        if not engine:
            raise ValueError(f"Active game engine not found for game {game_id}")

        # Turn validation: actor_id must be the current turn player
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        if room and room.players:
            current_idx = engine.env.game.current_player_idx
            if current_idx < len(room.players):
                expected_actor = str(room.players[current_idx])
                logger.warning(
                    "[BOT_TRACE] process_action_turn_check game=%s actor=%s expected_actor=%s current_idx=%d governor_idx=%s agent_selection=%s",
                    game_id,
                    actor_id,
                    expected_actor,
                    current_idx,
                    getattr(engine.env.game, "governor_idx", None),
                    getattr(engine.env, "agent_selection", None),
                )
                if not expected_actor.startswith("BOT_") and actor_id != expected_actor:
                    raise ValueError(f"Not your turn. Current player: {current_idx}")

        # TDD Defense: Validate action against the current action mask
        current_mask = engine.get_action_mask()
        logger.warning(
            "[BOT_TRACE] process_action_mask game=%s actor=%s action=%s valid=%s mask_len=%d",
            game_id,
            actor_id,
            action,
            (0 <= action < len(current_mask) and bool(current_mask[action])) if current_mask else False,
            len(current_mask),
        )
        if not (0 <= action < len(current_mask)) or not current_mask[action]:
            raise ValueError(f"Action {action} is invalid for the current state.")

        # Step through engine (wrapper handles snapshot & logging prep)
        result = engine.step(action)
        
        # Async MLOps Logging
        from app.services.ml_logger import MLLogger
        import copy
        
        # Keep strong references to background logging tasks to prevent GC dropping them
        if not hasattr(GameService, "_background_log_tasks"):
            GameService._background_log_tasks = set()
            
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
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
            GameService._background_log_tasks.add(task)
            task.add_done_callback(GameService._background_log_tasks.discard)
        except RuntimeError:
            pass # No running loop (e.g. synch fallback test scripts)
        
        # Save Log to DB (with human-readable summary for Adminer)
        try:
            summary = serialize_compact_summary(engine)
        except Exception:
            summary = None
        game_log = GameLog(
            game_id=game_id,
            round=result["info"].get("round", 0),
            step=result["info"].get("step", 0),
            actor_id=actor_id,
            action_data={"action": action},
            available_options=result["action_mask"],
            state_before=result["state_before"],
            state_after=result["state_after"],
            state_summary=summary,
        )
        self.db.add(game_log)
        
        # Load the room to check players (for bot scheduling)
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        if result.get("terminated", result["done"]) and room:
            room.status = "FINISHED"
            # Update Redis meta to reflect finished status
            try:
                redis_client.hset(f"game:{game_id}:meta", "status", "FINISHED")
                redis_client.expire(f"game:{game_id}:meta", 300)
            except Exception as e:
                logger.warning("Redis meta update failed: %s", e)

        self.db.commit()

        # Update Redis for WebSocket broadcast (Bot actions are also blasted through this channel)
        terminated = result.get("terminated", result["done"])
        if room:
            rich_state = self._build_rich_state(game_id, engine, room)
        else:
            rich_state = result["state_after"]
        new_action_mask = rich_state.get("action_mask", engine.get_action_mask()) if isinstance(rich_state, dict) else engine.get_action_mask()
        self._sync_to_redis(game_id, rich_state, finished=terminated)

        # Trigger Bot if next player is bot
        if not terminated and room:
            self._schedule_next_bot_turn_if_needed(game_id, room, engine)

        logger.warning(
            "[STATE_TRACE] process_action_exit game=%s actor=%s action=%s terminated=%s next_player_idx=%s",
            game_id,
            actor_id,
            action,
            terminated,
            getattr(engine.env.game, "current_player_idx", None),
        )
        logger.warning(
            "[BOT_TRACE] process_action_exit game=%s actor=%s action=%s terminated=%s next_player_idx=%s governor_idx=%s agent_selection=%s",
            game_id,
            actor_id,
            action,
            terminated,
            getattr(engine.env.game, "current_player_idx", None),
            getattr(engine.env.game, "governor_idx", None),
            getattr(engine.env, "agent_selection", None),
        )
        return {"state": rich_state, "action_mask": new_action_mask}

    def _schedule_next_bot_turn_if_needed(self, game_id: UUID, room: GameSession, engine: EngineWrapper):
        next_idx = engine.env.game.current_player_idx
        players = room.players or []
        logger.warning(
            "[BOT_TRACE] schedule_check game=%s next_idx=%d current_player_idx=%d governor_idx=%d agent_selection=%s players=%s",
            game_id,
            next_idx,
            engine.env.game.current_player_idx,
            engine.env.game.governor_idx,
            getattr(engine.env, "agent_selection", None),
            players,
        )

        if not players or next_idx >= len(players):
            logger.warning(
                "[BOT_TRACE] schedule_abort game=%s reason=idx_out_of_range next_idx=%d players_len=%d",
                game_id,
                next_idx,
                len(players),
            )
            return
            
        next_actor = players[next_idx]
        if str(next_actor).startswith("BOT_"):
            logger.warning(
                "[BOT_TRACE] schedule_bot game=%s next_actor=%s idx=%d",
                game_id,
                next_actor,
                next_idx,
            )
            from app.services.bot_service import BotService
            from app.dependencies import SessionLocal

            def sync_callback(bg_game_id, bg_actor_id, bg_action):
                logger.warning(
                    "[BOT_TRACE] callback_enter game=%s actor=%s action=%s",
                    bg_game_id,
                    bg_actor_id,
                    bg_action,
                )
                with SessionLocal() as bg_db:
                    bg_service = GameService(bg_db)
                    try:
                        bg_service.process_action(bg_game_id, bg_actor_id, bg_action)
                        logger.warning(
                            "[BOT_TRACE] callback_exit game=%s actor=%s action=%s",
                            bg_game_id,
                            bg_actor_id,
                            bg_action,
                        )
                    except Exception as exc:
                        logger.warning(
                            "[BOT_TRACE] callback_error game=%s actor=%s action=%s error=%s",
                            bg_game_id,
                            bg_actor_id,
                            bg_action,
                            exc,
                            exc_info=True,
                        )
                        raise

            # Store reference to prevent GC reaping the task
            try:
                task = asyncio.create_task(
                    BotService.run_bot_turn(
                        game_id=game_id, 
                        engine=engine, 
                        actor_id=next_actor, 
                        process_action_callback=sync_callback
                    )
                )
            except RuntimeError as exc:
                logger.warning(
                    "[BOT_TRACE] schedule_failed game=%s next_actor=%s reason=no_running_loop error=%s",
                    game_id,
                    next_actor,
                    exc,
                )
                return

            self._bot_tasks.add(task)
            task.add_done_callback(self._make_bot_task_done_callback(game_id, next_actor))
            self._start_bot_stall_watchdog(game_id, next_actor)
            logger.warning(
                "[BOT_TRACE] task_created game=%s next_actor=%s task_id=%s active_bot_tasks=%d",
                game_id,
                next_actor,
                id(task),
                len(self._bot_tasks),
            )
        else:
            logger.warning(
                "[BOT_TRACE] schedule_human game=%s next_actor=%s idx=%d",
                game_id,
                next_actor,
                next_idx,
            )

    def _make_bot_task_done_callback(self, game_id: UUID, actor_id: str):
        def _done(task: asyncio.Task):
            self._bot_tasks.discard(task)
            key = f"{game_id}:{actor_id}"
            watchdog = self._bot_stall_watchdogs.pop(key, None)
            if watchdog:
                watchdog.cancel()

            cancelled = task.cancelled()
            exc = None
            if not cancelled:
                try:
                    exc = task.exception()
                except Exception as callback_exc:
                    exc = callback_exc

            logger.warning(
                "[BOT_TRACE] task_done game=%s actor=%s task_id=%s cancelled=%s exception=%r active_bot_tasks=%d",
                game_id,
                actor_id,
                id(task),
                cancelled,
                exc,
                len(self._bot_tasks),
            )
        return _done

    def _start_bot_stall_watchdog(self, game_id: UUID, actor_id: str) -> None:
        key = f"{game_id}:{actor_id}"
        old_watchdog = self._bot_stall_watchdogs.pop(key, None)
        if old_watchdog:
            old_watchdog.cancel()

        async def _watch():
            try:
                await asyncio.sleep(5)
                logger.warning(
                    "[BOT_STALL] watchdog_timeout game=%s actor=%s threshold_seconds=5",
                    game_id,
                    actor_id,
                )
            except asyncio.CancelledError:
                return

        self._bot_stall_watchdogs[key] = asyncio.create_task(_watch())

    def _store_game_meta(self, game_id: UUID, room: GameSession):
        """Store game metadata in Redis for disconnect/timeout logic."""
        players = room.players or []
        human_count = sum(1 for p in players if not str(p).startswith("BOT_"))
        try:
            redis_client.hset(f"game:{game_id}:meta", mapping={
                "status": room.status,
                "human_count": str(human_count),
                "num_players": str(room.num_players),
            })
            redis_client.expire(f"game:{game_id}:meta", 900)
        except Exception as e:
            logger.warning("Redis meta store failed: %s", e)

    def _sync_to_redis(self, game_id: UUID, state: Dict, finished: bool = False):
        ttl = 300 if finished else 900  # 5 min after game end, 15 min during play
        data = {"type": "STATE_UPDATE", "data": state}
        logger.warning(
            "[STATE_TRACE] sync_to_redis_start game=%s finished=%s ttl=%s",
            game_id,
            finished,
            ttl,
        )
        try:
            redis_client.set(f"game:{game_id}:state", json.dumps(state), ex=ttl)
            redis_client.publish(f"game:{game_id}:events", json.dumps(data))
            logger.warning("[STATE_TRACE] sync_to_redis_end game=%s", game_id)
        except Exception as e:
            logger.warning("[STATE_TRACE] sync_to_redis_error game=%s error=%s", game_id, e, exc_info=True)
            logger.warning("Redis sync failed: %s", e)

        # 2. Direct In-Memory Broadcast (Fallback for single-instance development)
        try:
            loop = asyncio.get_running_loop()
            logger.warning("[STATE_TRACE] ws_broadcast_start game=%s", game_id)
            loop.create_task(manager.broadcast_to_game(str(game_id), data))
            logger.warning("[STATE_TRACE] ws_broadcast_end game=%s", game_id)
        except RuntimeError:
            logger.warning("[STATE_TRACE] ws_broadcast_error game=%s error=no_running_loop", game_id)
            pass  # No running loop (sync context)
        except Exception as e:
            logger.warning("[STATE_TRACE] ws_broadcast_error game=%s error=%s", game_id, e, exc_info=True)
            logger.warning("Direct broadcast failed: %s", e)

    def get_room_list(self) -> List[GameSession]:
        return self.db.query(GameSession).all()
