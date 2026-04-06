import os
import sys
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_channel_mayor_route.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.api.channel.game import perform_mayor_distribution


class _FakeQuery:
    def __init__(self, room):
        self._room = room

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._room


class _FakeDb:
    def __init__(self, room):
        self._room = room

    def query(self, _model):
        return _FakeQuery(self._room)


@pytest.mark.asyncio
async def test_channel_mayor_distribute_accepts_placements_payload(monkeypatch):
    game_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    room = SimpleNamespace(id=game_id, players=[user_id, "BOT_random", "BOT_random"])

    captured = {}

    class _FakeService:
        def __init__(self, _db):
            pass

        def process_mayor_distribution(self, gid, actor_id, placements):
            captured["gid"] = gid
            captured["actor_id"] = actor_id
            captured["placements"] = placements
            return {"state": {"ok": True}, "action_mask": [1, 0, 0]}

    monkeypatch.setattr("app.api.channel.game.GameService", _FakeService)

    res = await perform_mayor_distribution(
        game_id=game_id,
        body=SimpleNamespace(placements=[SimpleNamespace(slot_id="island:corn:0", count=1)]),
        db=_FakeDb(room),
        current_user=SimpleNamespace(id=user_id),
    )

    assert res["status"] == "success"
    assert res["state"]["ok"] is True
    assert captured["gid"] == game_id
    assert captured["actor_id"] == user_id
    assert captured["placements"][0].slot_id == "island:corn:0"


@pytest.mark.asyncio
async def test_channel_mayor_distribute_rejects_invalid_slot_id(monkeypatch):
    game_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    room = SimpleNamespace(id=game_id, players=[user_id, "BOT_random", "BOT_random"])

    class _FakeService:
        def __init__(self, _db):
            pass

        def process_mayor_distribution(self, _gid, _actor_id, _placements):
            raise ValueError("Unknown Mayor slot_id: city:nope:99")

    monkeypatch.setattr("app.api.channel.game.GameService", _FakeService)

    with pytest.raises(HTTPException) as exc:
        await perform_mayor_distribution(
            game_id=game_id,
            body=SimpleNamespace(placements=[SimpleNamespace(slot_id="city:nope:99", count=1)]),
            db=_FakeDb(room),
            current_user=SimpleNamespace(id=user_id),
        )

    assert exc.value.status_code == 400
    assert "Unknown Mayor slot_id" in exc.value.detail
