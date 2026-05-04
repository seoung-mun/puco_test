"""Spec Section 8.2: blocked lazy-recovery states."""

import uuid

import pytest

from app.db.models import GameLog, GameSession, User
from app.services.canonical_action import _describe_action
from app.services.engine_gateway import factory as engine_factory
from app.services.game_service import GameService


def _make_started_game_with_actions(db, action_count: int = 2):
    users = []
    for idx in range(3):
        user = User(
            id=uuid.uuid4(),
            google_id=f"blocked_recovery_gid_{idx}_{uuid.uuid4().hex}",
            nickname=f"BlockedRecovery{idx}",
        )
        db.add(user)
        users.append(user)
    db.flush()

    room = GameSession(
        id=uuid.uuid4(),
        title="Blocked Recovery Room",
        status="WAITING",
        num_players=3,
        players=[str(user.id) for user in users],
        host_id=str(users[0].id),
    )
    db.add(room)
    db.commit()

    service = GameService(db)
    service.start_game(room.id)

    for _ in range(action_count):
        engine = GameService.active_engines[room.id]
        action_mask = engine.get_action_mask()
        action_index = next(idx for idx, valid in enumerate(action_mask) if valid)
        actor_id = str(users[engine.env.game.current_player_idx].id)
        decoded = _describe_action(action_index, state={})
        service.process_action(
            room.id,
            actor_id,
            action_index,
            canonical_id=decoded["canonical_id"] if decoded else None,
        )

    return room.id


@pytest.mark.asyncio
async def test_recovery_blocked_when_metadata_absent(db):
    game_id = uuid.uuid4()
    row = GameSession(
        id=game_id,
        title="No Metadata Recovery",
        status="PROGRESS",
        num_players=3,
        players=[str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())],
        host_id=str(uuid.uuid4()),
        game_seed=None,
        engine_compat_version=None,
        state_revision=0,
    )
    db.add(row)
    db.commit()

    service = GameService(db)
    result = await service.ensure_engine_loaded(game_id)

    assert result.state == "blocked"
    assert result.reason == "no_metadata"

    db.expire_all()
    row = db.query(GameSession).filter(GameSession.id == game_id).first()
    assert row is not None
    assert row.status == "RECOVERY_BLOCKED"
    assert row.recovery_blocked_reason == "no_metadata"


@pytest.mark.asyncio
async def test_recovery_blocked_when_engine_version_mismatch(db):
    game_id = uuid.uuid4()
    row = GameSession(
        id=game_id,
        title="Version Mismatch Recovery",
        status="PROGRESS",
        num_players=3,
        players=[str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())],
        host_id=str(uuid.uuid4()),
        game_seed=12345,
        governor_idx=1,
        engine_compat_version=getattr(engine_factory, "ENGINE_COMPAT_VERSION", 0) + 99,
        state_revision=0,
        model_versions={"__engine__": {"compat_version": -1, "action_space": "x", "mayor_semantics": "y"}},
    )
    db.add(row)
    db.commit()

    service = GameService(db)
    result = await service.ensure_engine_loaded(game_id)

    assert result.state == "blocked"
    assert result.reason == "engine_version_mismatch"


@pytest.mark.asyncio
async def test_recovery_blocked_when_journal_validation_fails(db):
    game_id = _make_started_game_with_actions(db, action_count=2)
    GameService.active_engines.pop(game_id, None)
    GameService._engine_revision.pop(game_id, None)

    log = (
        db.query(GameLog)
        .filter(GameLog.game_id == game_id)
        .order_by(GameLog.id.desc())
        .first()
    )
    assert log is not None
    log.phase_before = "definitely_not_a_real_phase"
    db.commit()

    service = GameService(db)
    result = await service.ensure_engine_loaded(game_id)

    assert result.state == "blocked"
    assert result.reason == "replay_validation_failed"

    db.expire_all()
    row = db.query(GameSession).filter(GameSession.id == game_id).first()
    assert row is not None
    assert row.status == "RECOVERY_BLOCKED"
    assert row.recovery_blocked_reason == "replay_validation_failed"
