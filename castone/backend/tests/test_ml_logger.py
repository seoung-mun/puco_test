import json
import os
import pytest
import asyncio
from uuid import uuid4
from datetime import datetime

from app.services.ml_logger import MLLogger, LOG_DIR

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
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"transitions_{date_str}.jsonl")
    
    # Verify the file exists and all 100 lines are valid JSON
    assert os.path.exists(log_file)
    
    valid_lines = 0
    with open(log_file, "r") as f:
        for line in f:
            if actor_id in line:
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

    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"transitions_{date_str}.jsonl")

    with open(log_file, "r") as f:
        matching = [json.loads(line) for line in f if actor_id in line]

    assert matching, "기록된 transition이 없습니다"
    assert matching[-1]["action_mask_before"] == [0, 1, 0, 1]
