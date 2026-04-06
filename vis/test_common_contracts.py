import json
from pathlib import Path

from common import discover_transition_files, load_context


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_discover_transition_files_includes_per_game_and_legacy_logs(monkeypatch, tmp_path):
    per_game = tmp_path / "games" / "game-1.jsonl"
    legacy = tmp_path / "transitions_2026-04-06.jsonl"
    _write_jsonl(per_game, [{"game_id": "game-1"}])
    _write_jsonl(legacy, [{"game_id": "game-1"}])

    monkeypatch.setattr("common.DEFAULT_LOG_DIR", tmp_path)

    files = discover_transition_files()

    assert files == [per_game, legacy]


def test_load_context_sorts_transition_rows_and_loads_replay(monkeypatch, tmp_path):
    monkeypatch.setattr("common.DEFAULT_LOG_DIR", tmp_path)

    _write_jsonl(
        tmp_path / "games" / "game-1.jsonl",
        [
            {
                "game_id": "game-1",
                "timestamp": "2026-04-06T00:00:02Z",
                "info": {"round": 0, "step": 2},
                "actor_id": "BOT_random",
                "action": 15,
            },
            {
                "game_id": "game-1",
                "timestamp": "2026-04-06T00:00:01Z",
                "info": {"round": 0, "step": 1},
                "actor_id": "BOT_random",
                "action": 0,
            },
        ],
    )

    replay_path = tmp_path / "replay" / "game-1.json"
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    replay_path.write_text(
        json.dumps(
            {
                "format": "backend-replay.v1",
                "game_id": "game-1",
                "total_steps": 2,
                "entries": [
                    {"round": 0, "step": 1, "actor_id": "BOT_random", "action_id": 0},
                    {"round": 0, "step": 2, "actor_id": "BOT_random", "action_id": 15},
                ],
            }
        ),
        encoding="utf-8",
    )

    ctx = load_context(game_id="game-1", db_url=None, jsonl_paths=None)

    assert [row["info"]["step"] for row in ctx.transitions] == [1, 2]
    assert ctx.replay_path == replay_path
    assert len(ctx.replay_entries) == 2
    assert ctx.replay_payload["format"] == "backend-replay.v1"
