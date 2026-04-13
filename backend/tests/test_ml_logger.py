import json
import os
import pytest
import asyncio
from uuid import uuid4

from app.services import model_registry
from app.services.ml_logger import MLLogger


@pytest.fixture(autouse=True)
def isolate_ml_log_dir(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    game_dir = log_dir / "games"
    game_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.services.ml_logger.LOG_DIR", str(log_dir))
    monkeypatch.setattr("app.services.ml_logger.GAME_LOG_DIR", str(game_dir))


@pytest.mark.asyncio
async def test_log_transition_concurrency():
    """Test that multiple concurrent logs do not interleave or corrupt data."""
    game_id = uuid4()
    actor_id = f"test_actor_concurrent_{uuid4().hex}"
    
    # We will simulate 100 concurrent writes
    tasks = []
    for i in range(100):
        tasks.append(
            MLLogger.log_transition(
                game_id=game_id,
                actor_id=actor_id,
                state_before={"step": i},
                action=1,
                reward=0.0,
                done=False,
                state_after={"step": i+1},
                info={"round": 1}
            )
        )
    
    # Run all writes concurrently
    await asyncio.gather(*tasks)
    
    log_file = MLLogger.get_log_file_path(game_id)
    
    # Verify the file exists and all 100 lines are valid JSON
    assert os.path.exists(log_file)
    
    valid_lines = 0
    with open(log_file, "r") as f:
        for line in f:
            data = json.loads(line)
            assert "state_before" in data
            valid_lines += 1
                
    assert valid_lines == 100, f"Expected 100 valid lines, got {valid_lines}!"


@pytest.mark.asyncio
async def test_log_transition_includes_action_mask_when_provided():
    game_id = uuid4()
    actor_id = f"test_actor_mask_{uuid4().hex}"

    await MLLogger.log_transition(
        game_id=game_id,
        actor_id=actor_id,
        state_before={"step": 1},
        action=15,
        reward=0.0,
        done=False,
        state_after={"step": 2},
        info={"round": 1, "step": 2},
        action_mask_before=[0, 1, 0, 1],
    )

    log_file = MLLogger.get_log_file_path(game_id)

    with open(log_file, "r") as f:
        matching = [json.loads(line) for line in f]

    assert matching, "기록된 transition이 없습니다"
    assert matching[-1]["action_mask_before"] == [0, 1, 0, 1]


@pytest.mark.asyncio
async def test_log_transition_includes_model_info_when_provided():
    game_id = uuid4()
    actor_id = f"test_actor_model_{uuid4().hex}"

    await MLLogger.log_transition(
        game_id=game_id,
        actor_id=actor_id,
        state_before={"step": 3},
        action=7,
        reward=1.0,
        done=False,
        state_after={"step": 4},
        info={"round": 1, "step": 4},
        model_info={
            "actor_type": "bot",
            "bot_type": "ppo",
            "artifact_name": "PPO_PR_Server_hybrid_selfplay_curriculum_5billion_from_scratch_20260412_122638_step_481689600",
            "metadata_source": "bootstrap_derived",
            "fingerprint": {
                "action_space": model_registry.ACTION_SPACE_FINGERPRINT_V1,
                "mayor_semantics": model_registry.MAYOR_SEMANTICS_FINGERPRINT_V1,
                "env": "puco-upstream/main@4949773",
            },
        },
    )

    log_file = MLLogger.get_log_file_path(game_id)

    with open(log_file, "r") as f:
        matching = [json.loads(line) for line in f]

    assert matching, "기록된 transition이 없습니다"
    assert matching[-1]["model_info"]["bot_type"] == "ppo"
    assert matching[-1]["model_info"]["metadata_source"] == "bootstrap_derived"
    assert matching[-1]["model_info"]["fingerprint"]["action_space"] == model_registry.ACTION_SPACE_FINGERPRINT_V1


def test_get_log_file_path_uses_per_game_jsonl_layout():
    game_id = uuid4()
    log_path = MLLogger.get_log_file_path(game_id)

    assert log_path.endswith(f"/games/{game_id}.jsonl")
