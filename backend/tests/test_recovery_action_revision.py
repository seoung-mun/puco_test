"""Spec Section 8.2: process_action writes atomic recovery journal revisions."""

import uuid

from app.db.models import GameLog, GameSession, User
from app.services.game_service import GameService


def _make_started_three_human_game(db):
    users = []
    for idx in range(3):
        user = User(
            id=uuid.uuid4(),
            google_id=f"recovery_action_gid_{idx}_{uuid.uuid4().hex}",
            nickname=f"RecoveryAction{idx}",
        )
        db.add(user)
        users.append(user)
    db.flush()

    room = GameSession(
        id=uuid.uuid4(),
        title="Recovery Action Room",
        status="WAITING",
        num_players=3,
        players=[str(user.id) for user in users],
        host_id=str(users[0].id),
    )
    db.add(room)
    db.commit()

    service = GameService(db)
    service.start_game(room.id)
    engine = GameService.active_engines[room.id]
    action_mask = engine.get_action_mask()
    legal_action_idx = next(idx for idx, valid in enumerate(action_mask) if valid)
    current_player_idx = engine.env.game.current_player_idx
    actor_id = str(users[current_player_idx].id)
    return room.id, actor_id, legal_action_idx


def test_action_apply_increments_revision_atomically(db):
    game_id, actor_id, legal_action_idx = _make_started_three_human_game(db)

    service = GameService(db)
    service.process_action(game_id, actor_id, legal_action_idx, canonical_id=None)

    db.expire_all()
    game = db.query(GameSession).filter(GameSession.id == game_id).first()
    log = (
        db.query(GameLog)
        .filter(GameLog.game_id == game_id)
        .order_by(GameLog.id.desc())
        .first()
    )

    assert game is not None
    assert log is not None
    assert game.state_revision == 1
    assert log.revision == 1
    assert log.phase_before is not None
    assert log.active_player_before is not None
    assert log.action_data["action_index"] == legal_action_idx
    assert "canonical_id" in log.action_data
