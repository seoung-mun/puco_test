import uuid
from unittest.mock import MagicMock

from app.db.models import GameSession
from app.services.game_service import GameService


def _make_room(players):
    return GameSession(
        id=uuid.uuid4(),
        title="Snapshot Room",
        status="WAITING",
        num_players=len(players),
        players=players,
        host_id=str(uuid.uuid4()),
    )


def test_build_model_versions_snapshot_for_mixed_bot_room():
    service = GameService(MagicMock())
    room = _make_room(["BOT_ppo", "BOT_random", "BOT_ppo"])

    snapshot = service._build_model_versions_snapshot(room)

    assert snapshot["player_0"]["bot_type"] == "ppo"
    assert snapshot["player_0"]["artifact_name"] == "PPO_PR_Server_20260401_214532_step_99942400"
    assert snapshot["player_0"]["metadata_source"] == "bootstrap_derived"
    assert snapshot["player_1"]["bot_type"] == "random"
    assert snapshot["player_1"]["metadata_source"] == "builtin"
    assert snapshot["player_2"]["bot_type"] == "ppo"


def test_build_model_versions_snapshot_marks_humans_separately():
    service = GameService(MagicMock())
    human_id = str(uuid.uuid4())
    room = _make_room([human_id, "BOT_random", "BOT_ppo"])

    snapshot = service._build_model_versions_snapshot(room)

    assert snapshot["player_0"]["actor_type"] == "human"
    assert snapshot["player_0"]["player_id"] == human_id
    assert snapshot["player_1"]["actor_type"] == "bot"
    assert snapshot["player_2"]["bot_type"] == "ppo"


def test_build_rich_state_includes_model_versions(monkeypatch):
    service = GameService(MagicMock())
    room = _make_room(["BOT_ppo", "BOT_random", "BOT_ppo"])
    room.model_versions = service._build_model_versions_snapshot(room)

    monkeypatch.setattr(
        "app.services.game_service.serialize_game_state_from_engine",
        lambda **kwargs: {"meta": {"phase": "role_selection"}, "players": {}},
    )

    state = service._build_rich_state(room.id, engine=MagicMock(), room=room)

    assert state["model_versions"] == room.model_versions


def test_resolve_actor_model_info_uses_room_snapshot():
    service = GameService(MagicMock())
    room = _make_room(["BOT_ppo", "BOT_random", "BOT_ppo"])
    room.model_versions = service._build_model_versions_snapshot(room)

    model_info = service._resolve_actor_model_info(room, "BOT_ppo")

    assert model_info is not None
    assert model_info["artifact_name"] == "PPO_PR_Server_20260401_214532_step_99942400"
    assert model_info["bot_type"] == "ppo"
