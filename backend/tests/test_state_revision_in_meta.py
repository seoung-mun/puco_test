"""Contract: rich state meta exposes state_revision for frontend resync."""

from __future__ import annotations

from app.db.models import GameSession
from app.services.game_service import GameService

from .test_recovery_action_revision import _make_started_three_human_game


def test_rich_state_includes_state_revision(db):
    game_id, _, _ = _make_started_three_human_game(db)
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    assert room is not None
    engine = GameService.active_engines[game_id]

    rich = GameService(db)._build_rich_state(game_id, engine, room)

    assert "state_revision" in rich["meta"]
    assert rich["meta"]["state_revision"] == 0
