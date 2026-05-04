"""Spec Section 8.2: replay_step must not persist or broadcast."""

import uuid
from unittest.mock import MagicMock

from app.db.models import GameLog, GameSession, User
from app.services.game_service import GameService


def test_replay_step_does_not_invoke_loggers_or_broadcast(db, monkeypatch):
    users = []
    for idx in range(3):
        user = User(
            id=uuid.uuid4(),
            google_id=f"replay_isolation_{idx}_{uuid.uuid4().hex}",
            nickname=f"ReplayIsolation{idx}",
        )
        db.add(user)
        users.append(user)
    db.flush()

    room = GameSession(
        id=uuid.uuid4(),
        title="Replay Isolation Room",
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
    action_index = next(idx for idx, valid in enumerate(engine.get_action_mask()) if valid)

    append_entry = MagicMock()
    ml_log_transition = MagicMock()
    publish = MagicMock()
    broadcast = MagicMock()

    monkeypatch.setattr("app.services.replay_logger.ReplayLogger.append_entry", append_entry)
    monkeypatch.setattr("app.services.ml_logger.MLLogger.log_transition", ml_log_transition)
    monkeypatch.setattr("app.services.game_service.redis_client.publish", publish)
    monkeypatch.setattr("app.services.ws_manager.manager.broadcast_to_game", broadcast)

    log_count_before = db.query(GameLog).filter(GameLog.game_id == room.id).count()
    engine.replay_step(action_index)
    log_count_after = db.query(GameLog).filter(GameLog.game_id == room.id).count()

    assert log_count_after == log_count_before
    append_entry.assert_not_called()
    ml_log_transition.assert_not_called()
    publish.assert_not_called()
    broadcast.assert_not_called()
