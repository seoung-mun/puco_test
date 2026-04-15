import asyncio
import copy
import json
import logging
from typing import Dict, List
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.redis import sync_redis_client as redis_client
from app.db.models import GameSession, GameLog, User
from app.services.engine_gateway import create_game_engine, EngineWrapper
from app.services.game_service_support import (
    build_model_versions_snapshot,
    build_player_control_modes,
    build_replay_players_snapshot,
    build_rich_state,
    resolve_actor_model_info,
    resolve_player_names_and_bots,
)
from app.schemas.game import GameRoomCreate
from app.services.ws_manager import manager
from app.services.state_serializer import (
    serialize_compact_summary,
    serialize_game_state_from_engine,
)
from app.services.replay_logger import (
    ReplayLogger,
    build_final_scores_payload,
    build_replay_entry,
    summarize_transition_state,
)
logger = logging.getLogger(__name__)

class GameService:
    # In-memory store for active engines (Class variable to persist between requests)
    active_engines: Dict[UUID, EngineWrapper] = {}
    _bot_tasks = set()
    _bot_stall_watchdogs: Dict[str, asyncio.Task] = {}
    game_session_model = GameSession

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
        return resolve_player_names_and_bots(self.db, room)

    def _build_player_control_modes(self, room: GameSession) -> List[int]:
        return build_player_control_modes(room)

    def _build_rich_state(self, game_id: UUID, engine: EngineWrapper, room: GameSession) -> Dict:
        return build_rich_state(self.db, game_id, engine, room)

    def _build_replay_players_snapshot(self, room: GameSession, player_names: list[str]) -> list[dict]:
        return build_replay_players_snapshot(room, player_names)

    def _build_model_versions_snapshot(self, room: GameSession) -> Dict[str, Dict]:
        return build_model_versions_snapshot(room)

    def _resolve_actor_model_info(self, room: GameSession | None, actor_id: str) -> Dict | None:
        return resolve_actor_model_info(room, actor_id)

    def start_game(self, game_id: UUID):
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        if not room:
            raise ValueError("Game not found")

        actual_players = len(room.players or [])
        if actual_players < 3:
            raise ValueError(f"Need at least 3 players to start, currently {actual_players}")

        # Initialize engine with actual number of players
        engine = create_game_engine(
            num_players=actual_players,
            player_control_modes=build_player_control_modes(room),
        )
        GameService.active_engines[game_id] = engine

        room.status = "PROGRESS"
        room.model_versions = build_model_versions_snapshot(room)
        self.db.commit()

        # Build rich state and broadcast
        rich_state = build_rich_state(self.db, game_id, engine, room)
        action_mask = rich_state.get("action_mask", engine.get_action_mask())
        self._store_game_meta(game_id, room)
        self._sync_to_redis(game_id, rich_state)
        player_names, _ = resolve_player_names_and_bots(self.db, room)
        ReplayLogger.initialize_game(
            game_id=game_id,
            title=room.title,
            status=room.status,
            host_id=str(room.host_id) if room.host_id else None,
            players=build_replay_players_snapshot(room, player_names),
            model_versions=dict(room.model_versions or {}),
            initial_state_summary=summarize_transition_state(engine.get_state()),
        )

        # Trigger Bot if first player is a bot
        self._schedule_next_bot_turn_if_needed(game_id, room, engine)

        return {"state": rich_state, "action_mask": action_mask}

    def process_action(self, game_id: UUID, actor_id: str, action: int, suppress_broadcast: bool = False):
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
                if actor_id != expected_actor:
                    raise ValueError(f"Not your turn. Current player: {current_idx}")

        # TDD Defense: Validate action against the current action mask
        current_mask = engine.get_action_mask()
        current_player_idx = engine.env.game.current_player_idx
        current_phase_id = engine.last_info.get("current_phase_id") if engine.last_info else None
        actor_model_info = resolve_actor_model_info(room, actor_id)
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
        player_names, _ = resolve_player_names_and_bots(self.db, room) if room else ([], {})
        actor_name = (
            player_names[current_player_idx]
            if current_player_idx is not None and 0 <= current_player_idx < len(player_names)
            else actor_id
        )
        replay_entry = build_replay_entry(
            actor_id=actor_id,
            actor_name=actor_name,
            player_index=current_player_idx,
            action=action,
            reward=result["reward"],
            done=result["done"],
            info=result["info"],
            state_before=copy.deepcopy(result["state_before"]),
            state_after=copy.deepcopy(result["state_after"]),
            action_mask_before=copy.deepcopy(current_mask),
            model_info=copy.deepcopy(actor_model_info),
        )

        # Async MLOps Logging
        from app.services.ml_logger import MLLogger
        
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
                    info=copy.deepcopy(result["info"]),
                    action_mask_before=copy.deepcopy(current_mask),
                    phase_id_before=current_phase_id,
                    current_player_idx_before=current_player_idx,
                    model_info=copy.deepcopy(actor_model_info),
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
            action_data={
                "action": action,
                "model_info": actor_model_info,
            },
            available_options=current_mask,
            state_before=result["state_before"],
            state_after=result["state_after"],
            state_summary=summary,
        )
        self.db.add(game_log)
        
        # Load the room to check players (for bot scheduling)
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        replay_status = room.status if room else None
        replay_final_scores = None
        replay_result_summary = None
        if result.get("terminated", result["done"]) and room:
            room.status = "FINISHED"
            replay_status = "FINISHED"
            replay_final_scores, replay_result_summary = build_final_scores_payload(
                game=engine.env.game,
                player_names=player_names,
                actor_ids=[str(player_id) for player_id in (room.players or [])],
            )
            winner_entry = next(
                (s for s in replay_final_scores if s.get("winner")),
                None,
            )
            if winner_entry and winner_entry.get("actor_id"):
                room.winner_id = str(winner_entry["actor_id"])
            # Update Redis meta to reflect finished status
            try:
                redis_client.hset(f"game:{game_id}:meta", "status", "FINISHED")
                redis_client.expire(f"game:{game_id}:meta", 300)
            except Exception as e:
                logger.warning("Redis meta update failed: %s", e)

        self.db.commit()

        terminated = result.get("terminated", result["done"])
        if room:
            rich_state = build_rich_state(self.db, game_id, engine, room)
        else:
            rich_state = result["state_after"]
        new_action_mask = rich_state.get("action_mask", engine.get_action_mask()) if isinstance(rich_state, dict) else engine.get_action_mask()

        if room:
            ReplayLogger.append_entry(
                game_id=game_id,
                title=room.title,
                status=replay_status,
                host_id=str(room.host_id) if room.host_id else None,
                players=build_replay_players_snapshot(room, player_names),
                model_versions=dict(room.model_versions or {}),
                entry=replay_entry,
                rich_state=rich_state if not suppress_broadcast else None,
                final_scores=replay_final_scores,
                result_summary=replay_result_summary,
            )

        if not suppress_broadcast:
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

            def sync_callback(bg_game_id, bg_actor_id, bg_action, suppress_broadcast=False):
                logger.warning(
                    "[BOT_TRACE] callback_enter game=%s actor=%s action=%s suppress_broadcast=%s",
                    bg_game_id,
                    bg_actor_id,
                    bg_action,
                    suppress_broadcast,
                )
                with SessionLocal() as bg_db:
                    bg_service = GameService(bg_db)
                    try:
                        bg_service.process_action(bg_game_id, bg_actor_id, bg_action, suppress_broadcast=suppress_broadcast)
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
        redis_published = False
        logger.warning(
            "[STATE_TRACE] sync_to_redis_start game=%s finished=%s ttl=%s",
            game_id,
            finished,
            ttl,
        )
        try:
            redis_client.set(f"game:{game_id}:state", json.dumps(state), ex=ttl)
            redis_client.publish(f"game:{game_id}:events", json.dumps(data))
            redis_published = True
            logger.warning("[STATE_TRACE] sync_to_redis_end game=%s", game_id)
        except Exception as e:
            logger.warning("[STATE_TRACE] sync_to_redis_error game=%s error=%s", game_id, e, exc_info=True)
            logger.warning("Redis sync failed: %s", e)

        if redis_published:
            return

        # 2. Direct In-Memory Broadcast (Fallback when Redis publish is unavailable)
        try:
            loop = asyncio.get_running_loop()
            logger.warning("[STATE_TRACE] ws_broadcast_fallback_start game=%s", game_id)
            loop.create_task(manager.broadcast_to_game(str(game_id), data))
            logger.warning("[STATE_TRACE] ws_broadcast_fallback_end game=%s", game_id)
        except RuntimeError:
            logger.warning("[STATE_TRACE] ws_broadcast_fallback_error game=%s error=no_running_loop", game_id)
            pass  # No running loop (sync context)
        except Exception as e:
            logger.warning("[STATE_TRACE] ws_broadcast_fallback_error game=%s error=%s", game_id, e, exc_info=True)
            logger.warning("Direct broadcast failed: %s", e)

    def get_room_list(self) -> List[GameSession]:
        return self.db.query(GameSession).all()
