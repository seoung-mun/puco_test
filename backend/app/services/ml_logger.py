import json
import os
import aiofiles
from datetime import datetime, timezone
from uuid import UUID

from app.services.contracts import (
    TRANSITION_ENVELOPE_SCHEMA_VERSION,
    extract_schema_version,
    extract_state_kind,
)
from app.services.model_registry import enrich_actor_snapshot
from app.services.log_paths import ensure_log_dir, resolve_log_dir

LOG_DIR = resolve_log_dir()
GAME_LOG_DIR = ensure_log_dir("games")

class MLLogger:
    """
    MLOps Logging Service:
    Appends raw (State, Action, Reward, NextState) transitions for offline RL (PPO) retraining.
    """
    @staticmethod
    def get_log_file_path(game_id: UUID | str) -> str:
        return os.path.join(GAME_LOG_DIR, f"{game_id}.jsonl")

    @staticmethod
    async def log_transition(
        game_id: UUID,
        actor_id: str,
        state_before: dict,
        action: int,
        reward: float,
        done: bool,
        state_after: dict,
        info: dict,
        action_mask_before: list[int] | None = None,
        phase_id_before: int | None = None,
        current_player_idx_before: int | None = None,
        model_info: dict | None = None,
        trace_id: str | None = None,
        submitted_canonical_id: str | None = None,
        decoded_canonical_id: str | None = None,
    ):
        log_file = MLLogger.get_log_file_path(game_id)

        if submitted_canonical_id is None:
            canonical_id_match: bool | None = None
        else:
            canonical_id_match = submitted_canonical_id == decoded_canonical_id

        record = {
            "schema_version": TRANSITION_ENVELOPE_SCHEMA_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "trace_id": trace_id,
            "game_id": str(game_id),
            "actor_id": actor_id,
            "state_before_kind": extract_state_kind(state_before),
            "state_after_kind": extract_state_kind(state_after),
            "state_before_schema_version": extract_schema_version(state_before),
            "state_after_schema_version": extract_schema_version(state_after),
            "state_before": state_before,
            "action": action,
            "submitted_action_index": action,
            "submitted_canonical_id": submitted_canonical_id,
            "decoded_canonical_id": decoded_canonical_id,
            "canonical_id_match": canonical_id_match,
            "reward": reward,
            "done": done,
            "state_after": state_after,
            "info": info,
        }
        if action_mask_before is not None:
            record["action_mask_before"] = action_mask_before
        if phase_id_before is not None:
            record["phase_id_before"] = phase_id_before
        if current_player_idx_before is not None:
            record["current_player_idx_before"] = current_player_idx_before
        if model_info is not None:
            record["model_info"] = enrich_actor_snapshot(model_info)

        # Async write to prevent blocking the WebSocket/Game event loop
        async with aiofiles.open(log_file, mode='a') as f:
            await f.write(json.dumps(record) + "\n")
