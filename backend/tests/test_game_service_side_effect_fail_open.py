import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.services.game_service import GameService


def _mock_process_action_dependencies(monkeypatch, *, replay_append_entry=None):
    game_id = uuid4()
    actor_id = "actor-1"

    engine = MagicMock()
    engine.get_action_mask.return_value = [1, 0, 0]
    engine.last_info = {"current_phase_id": 8}
    engine.env.game.current_player_idx = 0
    engine.env.game.current_phase = 8
    engine.env.game.governor_idx = 0
    engine.step.return_value = {
        "reward": 0.0,
        "done": False,
        "terminated": False,
        "truncated": False,
        "info": {"round": 1, "step": 1},
        "state_before": {
            "schema_version": "model-observation.v1",
            "state_kind": "model-observation",
            "global_state": {"current_phase": 8, "current_player": 0, "governor_idx": 0},
            "players": {},
        },
        "state_after": {
            "schema_version": "model-observation.v1",
            "state_kind": "model-observation",
            "global_state": {"current_phase": 2, "current_player": 1, "governor_idx": 0},
            "players": {},
        },
    }
    GameService.active_engines[game_id] = engine

    room = SimpleNamespace(
        players=[actor_id, "actor-2", "actor-3"],
        title="Fail Open Room",
        status="PROGRESS",
        host_id=actor_id,
        model_versions={},
        winner_id=None,
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = room

    monkeypatch.setattr(
        "app.services.game_service.build_rich_state",
        lambda _db, _game_id, _engine, _room: {
            "schema_version": "rich-game-state.v1",
            "state_kind": "rich-game-state",
            "meta": {"active_player": "player_1"},
            "action_mask": [1, 0, 0],
        },
    )
    monkeypatch.setattr(
        "app.services.game_service.resolve_player_names_and_bots",
        lambda _db, _room: (["Alice", "Bob", "Carol"], {}),
    )
    monkeypatch.setattr(
        "app.services.game_service.resolve_actor_model_info",
        lambda _room, _actor_id: {"actor_type": "human"},
    )
    monkeypatch.setattr(
        "app.services.game_service.serialize_compact_summary",
        lambda _engine: {"phase": "role_selection"},
    )
    monkeypatch.setattr(
        "app.services.game_service.build_replay_entry",
        lambda **_kwargs: {"step": 1, "commentary": "ok"},
    )
    monkeypatch.setattr(
        "app.services.game_service.GameLog",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        GameService,
        "_sync_to_redis",
        lambda self, _game_id, _state, finished=False: None,
    )
    monkeypatch.setattr(
        GameService,
        "_schedule_next_bot_turn_if_needed",
        lambda self, _game_id, _room, _engine: None,
    )

    if replay_append_entry is None:
        replay_append_entry = lambda **_kwargs: "ok"
    monkeypatch.setattr(
        "app.services.game_service.ReplayLogger.append_entry",
        replay_append_entry,
    )

    return game_id, actor_id, db


def test_process_action_keeps_success_when_replay_append_entry_fails(monkeypatch):
    def explode(**_kwargs):
        raise OSError("disk full")

    game_id, actor_id, db = _mock_process_action_dependencies(
        monkeypatch,
        replay_append_entry=explode,
    )
    service = GameService(db)

    try:
        result = service.process_action(game_id, actor_id, 0)
    finally:
        GameService.active_engines.pop(game_id, None)

    assert result["state"]["state_kind"] == "rich-game-state"
    assert result["action_mask"] == [1, 0, 0]


def test_process_action_keeps_success_when_ml_logger_raises(monkeypatch):
    class _ImmediateTask:
        def add_done_callback(self, callback):
            callback(self)

    class _ImmediateLoop:
        def create_task(self, coro):
            asyncio.run(coro)
            return _ImmediateTask()

    async def explode(**_kwargs):
        raise RuntimeError("sink offline")

    game_id, actor_id, db = _mock_process_action_dependencies(monkeypatch)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: _ImmediateLoop())
    monkeypatch.setattr("app.services.ml_logger.MLLogger.log_transition", explode)

    service = GameService(db)

    try:
        result = service.process_action(game_id, actor_id, 0)
    finally:
        GameService.active_engines.pop(game_id, None)

    assert result["state"]["state_kind"] == "rich-game-state"
    assert result["action_mask"] == [1, 0, 0]
