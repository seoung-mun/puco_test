import json
import os
import uuid

import pytest

from app.services.replay_logger import (
    REPLAY_LOG_DIR,
    ReplayLogger,
    get_replay_file_path,
)


@pytest.fixture
def cleanup_replay_file():
    os.makedirs(REPLAY_LOG_DIR, exist_ok=True)
    created: list[str] = []
    yield created
    for path in created:
        try:
            os.remove(path)
        except OSError:
            pass


def _common_kwargs(game_id: uuid.UUID) -> dict:
    return {
        "game_id": game_id,
        "title": "t",
        "status": "PROGRESS",
        "host_id": None,
        "players": [],
        "model_versions": None,
    }


def test_append_entry_stores_rich_state_when_provided(cleanup_replay_file):
    gid = uuid.uuid4()
    path = get_replay_file_path(gid)
    cleanup_replay_file.append(path)

    ReplayLogger.append_entry(
        **_common_kwargs(gid),
        entry={"step": 1, "action": "x"},
        rich_state={"meta": {"round": 5}},
    )

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["format"] == "backend-replay.v2"
    assert data["entries"][0]["rich_state"] == {"meta": {"round": 5}}


def test_append_entry_rich_state_is_none_when_suppressed(cleanup_replay_file):
    gid = uuid.uuid4()
    path = get_replay_file_path(gid)
    cleanup_replay_file.append(path)

    ReplayLogger.append_entry(
        **_common_kwargs(gid),
        entry={"step": 1, "action": "batch"},
        rich_state=None,
    )

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert data["entries"][0]["rich_state"] is None


def test_append_entry_mixed_rich_states(cleanup_replay_file):
    gid = uuid.uuid4()
    path = get_replay_file_path(gid)
    cleanup_replay_file.append(path)

    ReplayLogger.append_entry(
        **_common_kwargs(gid),
        entry={"step": 1, "action": "a"},
        rich_state={"meta": {"phase": "role_selection"}},
    )
    ReplayLogger.append_entry(
        **_common_kwargs(gid),
        entry={"step": 2, "action": "b"},
        rich_state=None,
    )
    ReplayLogger.append_entry(
        **_common_kwargs(gid),
        entry={"step": 3, "action": "c"},
        rich_state={"meta": {"phase": "mayor_action"}},
    )

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    entries = data["entries"]
    assert len(entries) == 3
    assert entries[0]["rich_state"] is not None
    assert entries[1]["rich_state"] is None
    assert entries[2]["rich_state"] is not None
