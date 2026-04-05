import json
import os
import aiofiles
from datetime import datetime, timezone
from uuid import UUID

LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../data/logs"))
os.makedirs(LOG_DIR, exist_ok=True)

class MLLogger:
    """
    MLOps Logging Service:
    Appends raw (State, Action, Reward, NextState) transitions for offline RL (PPO) retraining.
    """
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
    ):
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(LOG_DIR, f"transitions_{date_str}.jsonl")
        
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "game_id": str(game_id),
            "actor_id": actor_id,
            "state_before": state_before,
            "action": action,
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
        
        # Async write to prevent blocking the WebSocket/Game event loop
        async with aiofiles.open(log_file, mode='a') as f:
            await f.write(json.dumps(record) + "\n")
