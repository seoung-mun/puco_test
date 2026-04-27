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
            "artifact_name": "ppo-pr-server-semantic293-20260419",
            "metadata_source": "bundle_v2",
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
    assert matching[-1]["model_info"]["metadata_source"] == "bundle_v2"
    assert matching[-1]["model_info"]["fingerprint"]["action_space"] == model_registry.ACTION_SPACE_FINGERPRINT_V1


@pytest.mark.asyncio
async def test_log_transition_includes_transition_contract_metadata():
    game_id = uuid4()
    actor_id = f"test_actor_contract_{uuid4().hex}"

    await MLLogger.log_transition(
        game_id=game_id,
        actor_id=actor_id,
        state_before={"schema_version": "model-observation.v1", "state_kind": "model-observation"},
        action=15,
        reward=0.0,
        done=False,
        state_after={"schema_version": "model-observation.v1", "state_kind": "model-observation"},
        info={"round": 1, "step": 2},
        trace_id="trace-123",
    )

    log_file = MLLogger.get_log_file_path(game_id)

    with open(log_file, "r") as f:
        matching = [json.loads(line) for line in f]

    assert matching[-1]["schema_version"] == "transition-envelope.v1"
    assert matching[-1]["trace_id"] == "trace-123"
    assert matching[-1]["state_before_kind"] == "model-observation"
    assert matching[-1]["state_after_kind"] == "model-observation"


def test_get_log_file_path_uses_per_game_jsonl_layout():
    game_id = uuid4()
    log_path = MLLogger.get_log_file_path(game_id)

    assert log_path.endswith(f"/games/{game_id}.jsonl")


@pytest.mark.asyncio
async def test_transition_envelope_includes_canonical_decoded():
    """RED: log_transition envelope must carry submitted/decoded canonical_id and match flag."""
    game_id = uuid4()
    actor_id = f"test_actor_canonical_{uuid4().hex}"

    await MLLogger.log_transition(
        game_id=game_id,
        actor_id=actor_id,
        state_before={"schema_version": "model-observation.v1", "state_kind": "model-observation"},
        action=8,
        reward=0.0,
        done=False,
        state_after={"schema_version": "model-observation.v1", "state_kind": "model-observation"},
        info={"round": 1, "step": 1},
        trace_id="trace-canonical-1",
        submitted_canonical_id="settler:tile_type:coffee",
        decoded_canonical_id="settler:tile_type:coffee",
    )

    log_file = MLLogger.get_log_file_path(game_id)
    with open(log_file, "r") as f:
        matching = [json.loads(line) for line in f]

    assert matching, "기록된 transition이 없습니다"
    env = matching[-1]
    assert env["schema_version"] == "transition-envelope.v1"
    assert env["submitted_action_index"] == 8
    assert env["submitted_canonical_id"] == "settler:tile_type:coffee"
    assert env["decoded_canonical_id"] == "settler:tile_type:coffee"
    assert env["canonical_id_match"] is True


@pytest.mark.asyncio
async def test_transition_envelope_marks_canonical_mismatch():
    """RED: when submitted/decoded canonical_id differ, canonical_id_match must be False."""
    game_id = uuid4()
    actor_id = f"test_actor_mismatch_{uuid4().hex}"

    await MLLogger.log_transition(
        game_id=game_id,
        actor_id=actor_id,
        state_before={"schema_version": "model-observation.v1", "state_kind": "model-observation"},
        action=8,
        reward=0.0,
        done=False,
        state_after={"schema_version": "model-observation.v1", "state_kind": "model-observation"},
        info={"round": 1, "step": 1},
        trace_id="trace-canonical-2",
        submitted_canonical_id="settler:tile_type:corn",
        decoded_canonical_id="settler:tile_type:coffee",
    )

    log_file = MLLogger.get_log_file_path(game_id)
    with open(log_file, "r") as f:
        matching = [json.loads(line) for line in f]

    env = matching[-1]
    assert env["submitted_canonical_id"] == "settler:tile_type:corn"
    assert env["decoded_canonical_id"] == "settler:tile_type:coffee"
    assert env["canonical_id_match"] is False
