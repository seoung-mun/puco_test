"""Spec Section 8.2: start_game persists recovery metadata."""

import uuid

from app.db.models import GameSession, User
from app.services import engine_gateway
from app.services.game_service import GameService


def test_start_game_persists_recovery_metadata(db):
    users = []
    for idx in range(3):
        user = User(
            id=uuid.uuid4(),
            google_id=f"recovery_start_gid_{idx}_{uuid.uuid4().hex}",
            nickname=f"RecoveryStart{idx}",
        )
        db.add(user)
        users.append(user)
    db.flush()

    room = GameSession(
        id=uuid.uuid4(),
        title="Recovery Start Room",
        status="WAITING",
        num_players=3,
        players=[str(user.id) for user in users],
        host_id=str(users[0].id),
    )
    db.add(room)
    db.commit()

    service = GameService(db)
    service.start_game(room.id)

    db.expire_all()
    row = db.query(GameSession).filter(GameSession.id == room.id).first()
    compat_version = getattr(engine_gateway.factory, "ENGINE_COMPAT_VERSION", None)

    assert row is not None
    assert row.game_seed is not None
    assert isinstance(row.game_seed, int)
    assert 0 <= row.game_seed < 2**63
    assert row.governor_idx in (0, 1, 2)
    assert row.engine_compat_version == compat_version
    assert row.state_revision == 0

    assert "__engine__" in (row.model_versions or {})
    engine_snapshot = row.model_versions["__engine__"]
    assert engine_snapshot["compat_version"] == compat_version
    assert "action_space" in engine_snapshot
    assert "mayor_semantics" in engine_snapshot
