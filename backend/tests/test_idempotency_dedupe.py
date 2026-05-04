"""Spec §8.2 (v2) test: same action_intent_id is not applied twice."""

from __future__ import annotations

from uuid import uuid4

from app.core.security import create_access_token
from app.db.models import GameLog, GameSession
from app.services.canonical_action import _describe_action

from .test_recovery_action_revision import _make_started_three_human_game


def test_human_action_duplicate_intent_is_not_applied_twice(client, db):
    """Same action_intent_id submitted twice should not advance revision twice."""
    game_id, actor_id, legal_action_idx = _make_started_three_human_game(db)
    headers = {"Authorization": f"Bearer {create_access_token(subject=actor_id)}"}
    intent = str(uuid4())
    payload = {
        "payload": {
            "schema_version": "action-request.v1",
            "action_index": legal_action_idx,
            "canonical_id": _describe_action(legal_action_idx, state={}).get("canonical_id"),
            "action_intent_id": intent,
            "expected_state_revision": 0,
        }
    }

    first = client.post(
        f"/api/puco/game/{game_id}/action",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert first_body.get("duplicate") is not True

    second = client.post(
        f"/api/puco/game/{game_id}/action",
        json=payload,
        headers=headers,
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body.get("duplicate") is True

    db.expire_all()
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    assert room is not None
    assert room.state_revision == 1

    log_count = (
        db.query(GameLog)
        .filter(
            GameLog.game_id == game_id,
            GameLog.action_intent_id == intent,
        )
        .count()
    )
    assert log_count == 1
