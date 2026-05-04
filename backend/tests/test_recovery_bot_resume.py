"""Spec Section 8.2: bot resume after lazy recovery."""

import asyncio
import uuid

import pytest

from app.db.models import GameSession, User
from app.services.game_service import GameService


def _make_bot_room(db) -> uuid.UUID:
    host = User(
        id=uuid.uuid4(),
        google_id=f"bot_resume_host_{uuid.uuid4().hex}",
        nickname="BotResumeHost",
    )
    db.add(host)
    db.flush()

    room = GameSession(
        id=uuid.uuid4(),
        title="Bot Resume Room",
        status="WAITING",
        num_players=3,
        players=["BOT_random", "BOT_random", "BOT_random"],
        host_id=str(host.id),
    )
    db.add(room)
    db.commit()
    return room.id


def _make_human_room(db) -> uuid.UUID:
    users = []
    for idx in range(3):
        user = User(
            id=uuid.uuid4(),
            google_id=f"human_resume_{idx}_{uuid.uuid4().hex}",
            nickname=f"HumanResume{idx}",
        )
        db.add(user)
        users.append(user)
    db.flush()

    room = GameSession(
        id=uuid.uuid4(),
        title="Human Resume Room",
        status="WAITING",
        num_players=3,
        players=[str(user.id) for user in users],
        host_id=str(users[0].id),
    )
    db.add(room)
    db.commit()
    return room.id


@pytest.mark.asyncio
async def test_recovery_resumes_bot_turn_exactly_once(db, monkeypatch):
    gate = asyncio.Event()

    async def fake_run_bot_turn(*args, **kwargs):
        await gate.wait()

    from app.services.bot_service import BotService

    monkeypatch.setattr(BotService, "run_bot_turn", fake_run_bot_turn)

    room_id = _make_bot_room(db)
    service = GameService(db)
    service.start_game(room_id)

    existing = GameService._bot_tasks.pop(room_id, None)
    if existing is not None:
        existing.cancel()
        await asyncio.gather(existing, return_exceptions=True)

    GameService.active_engines.pop(room_id, None)
    GameService._engine_revision.pop(room_id, None)
    GameService._recovery_locks.pop(room_id, None)

    await service.ensure_engine_loaded(room_id)

    task = GameService._bot_tasks.get(room_id)
    assert task is not None
    assert not task.done()

    await service.ensure_engine_loaded(room_id)
    assert GameService._bot_tasks.get(room_id) is task

    gate.set()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    GameService._bot_tasks.pop(room_id, None)


@pytest.mark.asyncio
async def test_bot_resume_does_not_trigger_when_human_turn_active(db):
    room_id = _make_human_room(db)
    service = GameService(db)
    service.start_game(room_id)

    GameService.active_engines.pop(room_id, None)
    GameService._engine_revision.pop(room_id, None)
    GameService._recovery_locks.pop(room_id, None)
    GameService._bot_tasks.pop(room_id, None)

    await service.ensure_engine_loaded(room_id)

    assert GameService._bot_tasks.get(room_id) is None
