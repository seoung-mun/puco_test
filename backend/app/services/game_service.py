import asyncio
import copy
import json
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.redis import sync_redis_client as redis_client
from app.dependencies import SessionLocal
from app.db.models import GameSession, GameLog, User
from app.services.engine_gateway import create_game_engine, EngineWrapper
from app.services.game_service_support import (
    _action_space_fingerprint,
    _mayor_semantics_fingerprint,
    build_model_versions_snapshot,
    build_player_control_modes,
    build_replay_players_snapshot,
    build_rich_state,
    resolve_actor_model_info,
    resolve_player_names_and_bots,
    shuffle_start_player_order,
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
    load_replay_payload,
    summarize_transition_state,
)
from app.services.contracts import MODEL_OBSERVATION_STATE_KIND, extract_state_kind
logger = logging.getLogger(__name__)

_recovery_locks_meta_lock = asyncio.Lock()


@dataclass
class EngineLoadResult:
    state: Literal["ready", "blocked"]
    reason: Optional[str] = None
    state_revision: Optional[int] = None


class StaleRevisionError(Exception):
    """Raised when the client's expected revision no longer matches server state."""

    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(f"stale_state expected={expected} current={current}")


class GameService:
    # In-memory store for active engines (Class variable to persist between requests)
    active_engines: Dict[UUID, EngineWrapper] = {}
    _bot_tasks: Dict[UUID, asyncio.Task] = {}
    _engine_revision: Dict[UUID, int] = {}
    _recovery_locks: Dict[UUID, asyncio.Lock] = {}
    _bot_stall_watchdogs: Dict[str, asyncio.Task] = {}
    _bot_stall_watchdog_meta: Dict[UUID, dict] = {}
    _game_speed: Dict[UUID, int] = {}      # game_id -> 1 | 2 | 4
    _game_paused: Dict[UUID, bool] = {}    # game_id -> True | False
    # Track scheduler skip reasons for liveness diagnostics (Task 2A §1.2.1)
    # Shape: {"reason": str, "actor": str, "at": float, "current_idx": int, ...}
    _last_skip_reason: Dict[UUID, dict] = {}
    # Track when bot tasks were started (for "seconds_since_existing_task_started")
    _bot_task_started_at: Dict[UUID, float] = {}
    game_session_model = GameSession

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    async def _log_transition_safely(**kwargs):
        from app.services.ml_logger import MLLogger

        trace_id = kwargs.get("trace_id")
        try:
            await MLLogger.log_transition(**kwargs)
        except Exception as exc:
            logger.warning(
                "[ML_TRACE] log_transition_failed trace_id=%s error=%s",
                trace_id,
                exc,
                exc_info=True,
            )

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

    async def _get_or_create_recovery_lock(self, game_id: UUID) -> asyncio.Lock:
        global _recovery_locks_meta_lock
        async with _recovery_locks_meta_lock:
            lock = GameService._recovery_locks.get(game_id)
            if lock is None:
                lock = asyncio.Lock()
                GameService._recovery_locks[game_id] = lock
            return lock

    async def ensure_engine_loaded(self, game_id: UUID) -> EngineLoadResult:
        if game_id in GameService.active_engines:
            return EngineLoadResult(
                state="ready",
                state_revision=GameService._engine_revision.get(game_id, 0),
            )

        lock = await self._get_or_create_recovery_lock(game_id)
        async with lock:
            if game_id in GameService.active_engines:
                return EngineLoadResult(
                    state="ready",
                    state_revision=GameService._engine_revision.get(game_id, 0),
                )
            if self.db is not None:
                result = self._recover_with_db(self.db, game_id)
            else:
                result = await asyncio.to_thread(self._do_recovery_sync, game_id)
            if result.state == "ready":
                await self._resume_bot_after_recovery(game_id)
            return result

    def start_game(self, game_id: UUID):
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        if not room:
            raise ValueError("Game not found")

        actual_players = len(room.players or [])
        if actual_players < 3:
            raise ValueError(f"Need at least 3 players to start, currently {actual_players}")

        game_seed = secrets.randbits(63)
        start_players = shuffle_start_player_order(room.players or [], game_seed=game_seed)
        player_control_modes = [1 if str(player_id).startswith("BOT_") else 0 for player_id in start_players]
        engine = create_game_engine(
            num_players=actual_players,
            game_seed=game_seed,
            player_control_modes=player_control_modes,
        )
        GameService.active_engines[game_id] = engine
        GameService._engine_revision[game_id] = 0

        from app.services.engine_gateway.factory import ENGINE_COMPAT_VERSION
        try:
            start_room = copy.copy(room)
            start_room.players = list(start_players)
            model_versions = build_model_versions_snapshot(start_room)

            room.players = list(start_players)
            room.status = "PROGRESS"
            room.model_versions = model_versions
            room.game_seed = game_seed
            room.governor_idx = engine.initial_governor_idx
            room.engine_compat_version = ENGINE_COMPAT_VERSION
            room.state_revision = 0
            self.db.commit()
        except Exception:
            GameService.active_engines.pop(game_id, None)
            GameService._engine_revision.pop(game_id, None)
            self.db.rollback()
            raise

        # Build rich state and broadcast
        rich_state = build_rich_state(self.db, game_id, engine, room)
        action_mask = rich_state.get("action_mask", engine.get_action_mask())
        self._store_game_meta(game_id, room)
        GameService._sync_to_redis(game_id, rich_state)
        player_names, _ = resolve_player_names_and_bots(self.db, room)
        ReplayLogger.initialize_game(
            game_id=game_id,
            title=room.title,
            status=room.status,
            host_id=str(room.host_id) if room.host_id else None,
            players=build_replay_players_snapshot(room, player_names),
            model_versions=dict(room.model_versions or {}),
            initial_state_summary=summarize_transition_state(engine.get_state()),
            db=self.db,
        )
        self.db.commit()

        # Trigger Bot if first player is a bot
        self._schedule_next_bot_turn_if_needed(game_id, room, engine)

        return {"state": rich_state, "action_mask": action_mask}

    def process_action(
        self,
        game_id: UUID,
        actor_id: str,
        action: int,
        canonical_id: Optional[str] = None,
        action_intent_id: Optional[str] = None,
        expected_state_revision: Optional[int] = None,
        suppress_broadcast: bool = False,
    ):
        trace_id = uuid4().hex
        logger.warning(
            "[STATE_TRACE] process_action_enter trace_id=%s game=%s actor=%s action=%s",
            trace_id,
            game_id,
            actor_id,
            action,
        )
        logger.warning(
            "[BOT_TRACE] process_action_enter trace_id=%s game=%s actor=%s action=%s",
            trace_id,
            game_id,
            actor_id,
            action,
        )
        engine = GameService.active_engines.get(game_id)
        if not engine:
            raise ValueError(f"Active game engine not found for game {game_id}")

        prior = None
        if action_intent_id is not None:
            prior = self._lookup_prior_intent(game_id, action_intent_id)
            if prior is not None:
                return {**prior, "duplicate": True}

        current_revision = GameService._engine_revision.get(game_id, 0)
        if (
            expected_state_revision is not None
            and expected_state_revision != current_revision
        ):
            raise StaleRevisionError(
                expected=expected_state_revision,
                current=current_revision,
            )

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

        phase_before_step = engine.current_phase
        active_player_before_step = engine.active_player

        # Step through engine (wrapper handles snapshot & logging prep)
        result = engine.step(action)
        result["info"]["trace_id"] = trace_id
        player_names, _ = resolve_player_names_and_bots(self.db, room) if room else ([], {})
        actor_name = (
            player_names[current_player_idx]
            if current_player_idx is not None and 0 <= current_player_idx < len(player_names)
            else actor_id
        )
        try:
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
        except Exception as exc:
            logger.warning(
                "[REPLAY_TRACE] build_replay_entry_failed trace_id=%s game=%s actor=%s error=%s",
                trace_id,
                game_id,
                actor_id,
                exc,
                exc_info=True,
            )
            replay_entry = {
                "step": result["info"].get("step"),
                "round": result["info"].get("round"),
                "actor_id": actor_id,
                "actor_name": actor_name,
                "player": current_player_idx,
                "action_id": action,
                "reward": result["reward"],
                "done": result["done"],
                "commentary": None,
                "commentary_status": "degraded",
                "summary_validation_status": "degraded",
                "degraded_replay_used": True,
                "state_before_kind": extract_state_kind(result["state_before"], MODEL_OBSERVATION_STATE_KIND),
                "state_after_kind": extract_state_kind(result["state_after"], MODEL_OBSERVATION_STATE_KIND),
            }

        # Async MLOps Logging
        # Keep strong references to background logging tasks to prevent GC dropping them
        if not hasattr(GameService, "_background_log_tasks"):
            GameService._background_log_tasks = set()
            
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                GameService._log_transition_safely(
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
                    trace_id=trace_id,
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
        new_revision = GameService._engine_revision.get(game_id, 0) + 1
        game_log = GameLog(
            game_id=game_id,
            round=result["info"].get("round", 0),
            step=result["info"].get("step", 0),
            actor_id=actor_id,
            action_data={
                "action_index": action,
                "canonical_id": canonical_id,
                "action_intent_id": action_intent_id,
                "expected_state_revision": expected_state_revision,
                "model_info": actor_model_info,
            },
            available_options=current_mask,
            state_before=result["state_before"],
            state_after=result["state_after"],
            state_summary=summary,
            revision=new_revision,
            action_intent_id=action_intent_id,
            phase_before=phase_before_step,
            active_player_before=active_player_before_step,
        )
        self.db.add(game_log)

        # Load the room to check players (for bot scheduling)
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        replay_status = room.status if room else None
        replay_final_scores = None
        replay_result_summary = None
        if result.get("terminated", result["done"]) and room:
            room.status = "FINISHED"
            GameService.clear_playback_state(game_id)
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

        if room:
            room.state_revision = new_revision
        GameService._engine_revision[game_id] = new_revision
        try:
            self.db.commit()
        except IntegrityError as exc:
            if action_intent_id is not None and "ux_game_logs_game_intent" in str(exc.orig):
                self.db.rollback()
                GameService._engine_revision[game_id] = max(new_revision - 1, 0)
                if room:
                    room.state_revision = max(new_revision - 1, 0)
                prior = self._lookup_prior_intent(game_id, action_intent_id)
                if prior is not None:
                    return {**prior, "duplicate": True}
            raise

        terminated = result.get("terminated", result["done"])
        if room:
            rich_state = build_rich_state(self.db, game_id, engine, room)
        else:
            rich_state = result["state_after"]
        new_action_mask = rich_state.get("action_mask", engine.get_action_mask()) if isinstance(rich_state, dict) else engine.get_action_mask()

        if room:
            try:
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
                    db=self.db,
                )
                self.db.commit()
            except Exception as exc:
                logger.warning(
                    "[REPLAY_TRACE] append_entry_failed trace_id=%s game=%s actor=%s error=%s",
                    trace_id,
                    game_id,
                    actor_id,
                    exc,
                    exc_info=True,
                )

        if not suppress_broadcast:
            GameService._sync_to_redis(game_id, rich_state, finished=terminated)

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

    def _lookup_prior_intent(self, game_id: UUID, intent_id: str) -> Optional[Dict]:
        """Return the already-committed result shape for a prior human action intent."""
        log = (
            self.db.query(GameLog)
            .filter(
                GameLog.game_id == game_id,
                GameLog.action_intent_id == intent_id,
            )
            .order_by(GameLog.id.desc())
            .first()
        )
        if log is None:
            return None

        engine = GameService.active_engines.get(game_id)
        room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
        if engine is None or room is None:
            return None

        rich_state = build_rich_state(self.db, game_id, engine, room)
        return {
            "state": rich_state,
            "action_mask": rich_state.get("action_mask", engine.get_action_mask()),
        }

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

        if GameService.get_game_paused(game_id):
            GameService._last_skip_reason[game_id] = {
                "reason": "paused",
                "actor": None,
                "at": time.time(),
                "current_idx": next_idx,
            }
            logger.warning("[BOT_TRACE] schedule_skipped_paused game=%s", game_id)
            return

        if not players or next_idx >= len(players):
            GameService._last_skip_reason[game_id] = {
                "reason": "idx_out_of_range",
                "actor": None,
                "at": time.time(),
                "current_idx": next_idx,
                "players_len": len(players),
            }
            logger.warning(
                "[BOT_TRACE] schedule_abort game=%s reason=idx_out_of_range next_idx=%d players_len=%d",
                game_id,
                next_idx,
                len(players),
            )
            return

        next_actor = players[next_idx]
        if str(next_actor).startswith("BOT_"):
            existing = GameService._bot_tasks.get(game_id)
            if existing is not None and not existing.done():
                started_at = GameService._bot_task_started_at.get(game_id)
                seconds_since = (time.time() - started_at) if started_at is not None else None
                engine_revision = GameService._engine_revision.get(game_id)
                skip_at = time.time()
                # Try to surface the existing task's actor (best effort)
                existing_task_actor = getattr(existing, "_bot_actor_id", None)
                GameService._last_skip_reason[game_id] = {
                    "reason": "in_flight_self",
                    "actor": next_actor,
                    "existing_task_actor": existing_task_actor,
                    "at": skip_at,
                    "current_idx": next_idx,
                    "engine_revision": engine_revision,
                    "seconds_since_existing_task_started": seconds_since,
                }
                self._start_bot_stall_watchdog(
                    game_id,
                    str(next_actor),
                    started_at=skip_at,
                    source="schedule_skip",
                )
                logger.warning(
                    "[BOT_TRACE] schedule_skip_existing_task game=%s next_actor=%s task_id=%s "
                    "existing_task_actor=%s engine_revision=%s current_player_idx=%d "
                    "seconds_since_existing_task_started=%s",
                    game_id,
                    next_actor,
                    id(existing),
                    existing_task_actor,
                    engine_revision,
                    next_idx,
                    seconds_since,
                )
                return
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
                        bg_service.process_action(
                            bg_game_id,
                            bg_actor_id,
                            bg_action,
                            suppress_broadcast=suppress_broadcast,
                        )
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
                loop = asyncio.get_running_loop()
                task = loop.create_task(
                    BotService.run_bot_turn(
                        game_id=game_id,
                        engine=engine,
                        actor_id=next_actor,
                        process_action_callback=sync_callback,
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

            # Tag the task with its actor so future skip events can report it.
            try:
                setattr(task, "_bot_actor_id", next_actor)
            except Exception:
                pass
            prior_skip_reason = copy.deepcopy(GameService._last_skip_reason.get(game_id))
            self._bot_tasks[game_id] = task
            task_started_at = time.time()
            GameService._bot_task_started_at[game_id] = task_started_at
            # Clear any stale skip reason since a new task is now active.
            GameService._last_skip_reason.pop(game_id, None)
            task.add_done_callback(self._make_bot_task_done_callback(game_id, next_actor))
            self._start_bot_stall_watchdog(
                game_id,
                next_actor,
                started_at=task_started_at,
                source="task_created",
                last_skip_reason_snapshot=prior_skip_reason,
            )
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
            # IMPORTANT: clear the slot BEFORE attempting to reschedule so that the
            # follow-up scheduler call does not skip itself with `in_flight_self`.
            if self._bot_tasks.get(game_id) is task:
                self._bot_tasks.pop(game_id, None)
                GameService._bot_task_started_at.pop(game_id, None)
            key = GameService._bot_stall_watchdog_key(game_id)
            watchdog = self._bot_stall_watchdogs.get(key)
            watchdog_meta = GameService._bot_stall_watchdog_meta.get(game_id)
            if (
                watchdog is not None
                and watchdog_meta is not None
                and watchdog_meta.get("source") == "task_created"
                and watchdog_meta.get("actor_id") == actor_id
            ):
                self._bot_stall_watchdogs.pop(key, None)
                GameService._bot_stall_watchdog_meta.pop(game_id, None)
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

            # Step 1 — Re-trigger the next bot turn if the deterministic deadlock
            # described in §1.2.1 of the plan would otherwise leave a bot-only
            # game frozen. We intentionally only reschedule for *cleanly finished*
            # tasks: cancelled/exception tasks are surfaced with a structured
            # log line and skipped to avoid infinite reschedule loops.
            if cancelled or exc is not None:
                last_revision = GameService._engine_revision.get(game_id)
                logger.warning(
                    "[BOT_TRACE] scheduler_skipped_failed_task game=%s actor_id=%s "
                    "last_revision=%s exception_repr=%r cancelled=%s",
                    game_id,
                    actor_id,
                    last_revision,
                    exc,
                    cancelled,
                )
                return

            # Don't reschedule if the game is paused / finished / lost its engine.
            if GameService.get_game_paused(game_id):
                return
            active_engine = GameService.active_engines.get(game_id)
            if active_engine is None:
                return

            try:
                next_idx = active_engine.env.game.current_player_idx
            except Exception:
                logger.warning(
                    "[BOT_TRACE] task_done_reschedule_engine_inspect_failed game=%s actor=%s",
                    game_id,
                    actor_id,
                    exc_info=True,
                )
                return

            def _reschedule_next_bot_turn() -> None:
                # Don't trust the engine pointer / players list across a session
                # boundary — re-fetch the room from a fresh DB session, since the
                # original caller's session is closed by the time this callback
                # runs. We execute directly from the done-callback tick so the
                # follow-up task exists within a single `await asyncio.sleep(0)`
                # after awaiting the finished bot task.
                try:
                    current_engine = GameService.active_engines.get(game_id)
                    if current_engine is None or current_engine is not active_engine:
                        return
                    if GameService.get_game_paused(game_id):
                        return
                    try:
                        idx = current_engine.env.game.current_player_idx
                    except Exception:
                        logger.warning(
                            "[BOT_TRACE] reschedule_engine_inspect_failed game=%s",
                            game_id,
                            exc_info=True,
                        )
                        return
                    with SessionLocal() as fresh_db:
                        fresh_room = (
                            fresh_db.query(GameSession)
                            .filter(GameSession.id == game_id)
                            .first()
                        )
                        if fresh_room is None:
                            return
                        if fresh_room.status not in ("PROGRESS",):
                            # Game over / blocked / waiting — no follow-up.
                            return
                        players = fresh_room.players or []
                        if not players or idx >= len(players):
                            return
                        next_actor = players[idx]
                        if not str(next_actor).startswith("BOT_"):
                            return
                        # Already replaced by some other code path? Don't clobber.
                        if GameService._bot_tasks.get(game_id) is not None:
                            return
                        fresh_service = GameService(fresh_db)
                        fresh_service._schedule_next_bot_turn_if_needed(
                            game_id, fresh_room, current_engine
                        )
                except Exception:
                    logger.warning(
                        "[BOT_TRACE] task_done_reschedule_failed game=%s actor=%s",
                        game_id,
                        actor_id,
                        exc_info=True,
                    )

            _reschedule_next_bot_turn()
        return _done

    def _clear_recovery_runtime_state(self, game_id: UUID) -> None:
        GameService.active_engines.pop(game_id, None)
        GameService._engine_revision.pop(game_id, None)
        GameService._bot_tasks.pop(game_id, None)
        GameService._bot_task_started_at.pop(game_id, None)
        GameService._last_skip_reason.pop(game_id, None)
        GameService._recovery_locks.pop(game_id, None)
        self._cancel_bot_stall_watchdog(game_id)
        GameService.clear_playback_state(game_id)

    def _mark_blocked_in_db(
        self,
        db: Session,
        game_id: UUID,
        reason: str,
        room: Optional[GameSession] = None,
    ) -> None:
        room = room or db.query(GameSession).filter(GameSession.id == game_id).first()
        if room is not None:
            room.status = "RECOVERY_BLOCKED"
            room.recovery_blocked_reason = reason
            db.commit()

        self._clear_recovery_runtime_state(game_id)

        try:
            redis_client.hset(
                f"game:{game_id}:meta",
                mapping={"status": "RECOVERY_BLOCKED"},
            )
            redis_client.expire(f"game:{game_id}:meta", 900)
        except Exception:
            logger.warning("[RECOVERY] could not update redis meta for blocked game=%s", game_id, exc_info=True)

        logger.warning("[RECOVERY] blocked game=%s reason=%s", game_id, reason)

    def _mark_blocked(self, game_id: UUID, reason: str) -> None:
        with SessionLocal() as db:
            self._mark_blocked_in_db(db, game_id, reason)

    def _broadcast_recovery_started(self, game_id: UUID) -> None:
        try:
            redis_client.publish(
                f"game:{game_id}:events",
                json.dumps({"type": "RECOVERY_STARTED"}),
            )
        except Exception:
            logger.warning(
                "[RECOVERY] could not broadcast RECOVERY_STARTED game=%s",
                game_id,
                exc_info=True,
            )

    def _recover_with_db(self, db: Session, game_id: UUID) -> EngineLoadResult:
        from app.services.engine_gateway.factory import ENGINE_COMPAT_VERSION

        game = db.query(GameSession).filter(GameSession.id == game_id).first()
        if not game:
            return EngineLoadResult(state="blocked", reason="not_recoverable")
        if game.status == "RECOVERY_BLOCKED":
            return EngineLoadResult(
                state="blocked",
                reason=game.recovery_blocked_reason or "not_recoverable",
            )
        if game.status != "PROGRESS":
            return EngineLoadResult(state="blocked", reason="not_recoverable")

        if (
            game.game_seed is None
            or game.engine_compat_version is None
            or game.governor_idx is None
        ):
            self._mark_blocked_in_db(db, game_id, "no_metadata", room=game)
            return EngineLoadResult(state="blocked", reason="no_metadata")

        if game.engine_compat_version != ENGINE_COMPAT_VERSION:
            self._mark_blocked_in_db(db, game_id, "engine_version_mismatch", room=game)
            return EngineLoadResult(state="blocked", reason="engine_version_mismatch")

        stored_engine = (game.model_versions or {}).get("__engine__", {})
        if (
            stored_engine.get("action_space") != _action_space_fingerprint()
            or stored_engine.get("mayor_semantics") != _mayor_semantics_fingerprint()
        ):
            self._mark_blocked_in_db(db, game_id, "fingerprint_mismatch", room=game)
            return EngineLoadResult(state="blocked", reason="fingerprint_mismatch")

        engine = create_game_engine(
            num_players=game.num_players,
            game_seed=game.game_seed,
        )
        if engine.initial_governor_idx != game.governor_idx:
            self._mark_blocked_in_db(db, game_id, "replay_validation_failed", room=game)
            return EngineLoadResult(state="blocked", reason="replay_validation_failed")

        entries = (
            db.query(GameLog)
            .filter(GameLog.game_id == game_id, GameLog.revision.isnot(None))
            .order_by(GameLog.revision)
            .all()
        )

        expected_rev = 0
        for entry in entries:
            expected_rev += 1
            if entry.revision != expected_rev:
                self._mark_blocked_in_db(db, game_id, "journal_corrupt", room=game)
                return EngineLoadResult(state="blocked", reason="journal_corrupt")

        if len(entries) >= 30:
            self._broadcast_recovery_started(game_id)

        for entry in entries:
            if engine.current_phase != entry.phase_before:
                self._mark_blocked_in_db(db, game_id, "replay_validation_failed", room=game)
                return EngineLoadResult(state="blocked", reason="replay_validation_failed")
            if engine.active_player != entry.active_player_before:
                self._mark_blocked_in_db(db, game_id, "replay_validation_failed", room=game)
                return EngineLoadResult(state="blocked", reason="replay_validation_failed")
            try:
                action_data = entry.action_data or {}
                engine.replay_step(int(action_data["action_index"]))
            except Exception:
                logger.exception(
                    "[RECOVERY] replay_step failed game=%s revision=%s",
                    game_id,
                    entry.revision,
                )
                self._mark_blocked_in_db(db, game_id, "replay_validation_failed", room=game)
                return EngineLoadResult(state="blocked", reason="replay_validation_failed")

        if game.state_revision != len(entries):
            self._mark_blocked_in_db(db, game_id, "replay_validation_failed", room=game)
            return EngineLoadResult(state="blocked", reason="replay_validation_failed")

        GameService.active_engines[game_id] = engine
        GameService._engine_revision[game_id] = game.state_revision

        rich_state = build_rich_state(db, game_id, engine, game)
        GameService._sync_to_redis(game_id, rich_state)
        self._store_game_meta(game_id, game)

        return EngineLoadResult(
            state="ready",
            state_revision=game.state_revision,
        )

    def _do_recovery_sync(self, game_id: UUID) -> EngineLoadResult:
        with SessionLocal() as db:
            return self._recover_with_db(db, game_id)

    def _maybe_resume_bot(self, game_id: UUID, room: GameSession, engine: EngineWrapper) -> None:
        if room.status != "PROGRESS":
            return
        if GameService.get_game_paused(game_id):
            return

        players = list(room.players or [])
        active_idx = engine.env.game.current_player_idx
        if active_idx >= len(players):
            return
        if not str(players[active_idx]).startswith("BOT_"):
            return

        existing = GameService._bot_tasks.get(game_id)
        if existing is not None and not existing.done():
            return

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return

        self._schedule_next_bot_turn_if_needed(game_id, room, engine)

    async def _resume_bot_after_recovery(self, game_id: UUID) -> None:
        engine = GameService.active_engines.get(game_id)
        if engine is None:
            return
        if self.db is not None:
            room = self.db.query(GameSession).filter(GameSession.id == game_id).first()
            if room is not None:
                self._maybe_resume_bot(game_id, room, engine)
            return

        with SessionLocal() as db:
            room = db.query(GameSession).filter(GameSession.id == game_id).first()
            if room is not None:
                self._maybe_resume_bot(game_id, room, engine)

    async def _fetch_last_rich_state(self, game_id: UUID) -> Optional[Dict]:
        cached = redis_client.get(f"game:{game_id}:state")
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                logger.warning("[RECOVERY] invalid cached rich state game=%s", game_id, exc_info=True)
        return await asyncio.to_thread(self._read_last_rich_state_from_replay_payload, game_id)

    def _read_last_rich_state_from_replay_payload(self, game_id: UUID) -> Optional[Dict]:
        with SessionLocal() as db:
            payload = load_replay_payload(game_id=game_id, db=db)
        if not isinstance(payload, dict):
            return None
        for entry in reversed(payload.get("entries") or []):
            rich_state = entry.get("rich_state")
            if isinstance(rich_state, dict):
                return rich_state
        return None

    async def _fetch_or_build_rich_state(self, game_id: UUID) -> Dict:
        engine = GameService.active_engines.get(game_id)
        if engine is not None:
            return await asyncio.to_thread(GameService._build_rich_state_sync, game_id, engine)

        cached = redis_client.get(f"game:{game_id}:state")
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                logger.warning("[RECOVERY] invalid cached rich state game=%s", game_id, exc_info=True)
        return {}

    @staticmethod
    def _build_rich_state_sync(game_id: UUID, engine: EngineWrapper) -> Dict:
        with SessionLocal() as db:
            room = db.query(GameSession).filter(GameSession.id == game_id).first()
            if room is None:
                return {}
            return build_rich_state(db, game_id, engine, room)

    @staticmethod
    def _bot_stall_watchdog_key(game_id: UUID) -> str:
        return str(game_id)

    @staticmethod
    def _cancel_bot_stall_watchdog(game_id: UUID) -> None:
        key = GameService._bot_stall_watchdog_key(game_id)
        watchdog = GameService._bot_stall_watchdogs.pop(key, None)
        GameService._bot_stall_watchdog_meta.pop(game_id, None)
        if watchdog:
            watchdog.cancel()

    def _start_bot_stall_watchdog(
        self,
        game_id: UUID,
        actor_id: str,
        *,
        started_at: Optional[float] = None,
        source: str = "task_created",
        last_skip_reason_snapshot: Optional[dict] = None,
    ) -> None:
        key = GameService._bot_stall_watchdog_key(game_id)
        old_watchdog = self._bot_stall_watchdogs.pop(key, None)
        if old_watchdog:
            old_watchdog.cancel()
        started_at = started_at if started_at is not None else time.time()
        skip_context = copy.deepcopy(
            last_skip_reason_snapshot
            if last_skip_reason_snapshot is not None
            else GameService._last_skip_reason.get(game_id)
        )
        GameService._bot_stall_watchdog_meta[game_id] = {
            "actor_id": actor_id,
            "source": source,
            "started_at": started_at,
            "last_skip_reason": skip_context,
            "last_skip_at": skip_context.get("at") if isinstance(skip_context, dict) else None,
        }

        watchdog_task: asyncio.Task | None = None

        async def _watch():
            try:
                elapsed = max(0.0, time.time() - started_at)
                await asyncio.sleep(max(0.0, 5 - elapsed))
                logger.warning(
                    "[BOT_STALL] watchdog_timeout game=%s actor=%s threshold_seconds=5 "
                    "source=%s last_skip_reason=%r",
                    game_id,
                    actor_id,
                    source,
                    skip_context,
                )
            except asyncio.CancelledError:
                return
            finally:
                if watchdog_task is not None and self._bot_stall_watchdogs.get(key) is watchdog_task:
                    self._bot_stall_watchdogs.pop(key, None)
                    GameService._bot_stall_watchdog_meta.pop(game_id, None)

        watchdog_task = asyncio.create_task(_watch())
        self._bot_stall_watchdogs[key] = watchdog_task

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

    @staticmethod
    def broadcast_current_state(game_id: UUID) -> bool:
        """Publish a fresh STATE_UPDATE for ``game_id`` without advancing the engine.

        Used as the compensating flush when a bot's mayor batch ends after one or
        more suppressed placements without ever emitting a public broadcast — the
        engine state has moved on, but the UI never saw it. Returns True iff a
        publish was actually attempted.
        """
        engine = GameService.active_engines.get(game_id)
        if engine is None:
            logger.warning(
                "[STATE_TRACE] broadcast_current_state_skip game=%s reason=engine_missing",
                game_id,
            )
            return False

        try:
            rich_state = GameService._build_rich_state_sync(game_id, engine)
        except Exception as exc:
            logger.warning(
                "[STATE_TRACE] broadcast_current_state_build_failed game=%s error=%s",
                game_id,
                exc,
                exc_info=True,
            )
            return False

        GameService._sync_to_redis(game_id, rich_state, finished=False)
        return True

    @staticmethod
    def _sync_to_redis(game_id: UUID, state: Dict, finished: bool = False):
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

    @staticmethod
    def get_game_speed(game_id: UUID) -> int:
        return GameService._game_speed.get(game_id, 1)

    @staticmethod
    def set_game_speed(game_id: UUID, speed: int) -> None:
        GameService._game_speed[game_id] = speed

    @staticmethod
    def get_game_paused(game_id: UUID) -> bool:
        return GameService._game_paused.get(game_id, False)

    @staticmethod
    def set_game_paused(game_id: UUID, paused: bool) -> None:
        GameService._game_paused[game_id] = paused

    @staticmethod
    def clear_playback_state(game_id: UUID) -> None:
        GameService._game_speed.pop(game_id, None)
        GameService._game_paused.pop(game_id, None)
