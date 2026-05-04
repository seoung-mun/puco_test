"""Spec §8.2 (v2) test: expected_state_revision mismatch is rejected."""

from __future__ import annotations

from uuid import uuid4

from app.core.security import create_access_token
from app.db.models import GameSession
from app.services.canonical_action import _describe_action
from app.services.game_service import GameService

from .test_recovery_action_revision import _make_started_three_human_game


def test_human_action_stale_revision_is_rejected(client, db):
    """Out-of-date expected_state_revision should return 409 stale_state and not advance revision."""
    game_id, actor_id, legal_action_idx = _make_started_three_human_game(db)
    headers = {"Authorization": f"Bearer {create_access_token(subject=actor_id)}"}

    first = client.post(
        f"/api/puco/game/{game_id}/action",
        json={
            "payload": {
                "schema_version": "action-request.v1",
                "action_index": legal_action_idx,
                "canonical_id": _describe_action(legal_action_idx, state={}).get("canonical_id"),
                "action_intent_id": str(uuid4()),
                "expected_state_revision": 0,
            }
        },
        headers=headers,
    )
    assert first.status_code == 200, first.text

    db.expire_all()
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    assert room is not None
    assert room.state_revision == 1

    service = GameService(db)
    engine = GameService.active_engines[game_id]
    current_idx = engine.env.game.current_player_idx
    next_actor_id = str(room.players[current_idx])
    next_headers = {
        "Authorization": f"Bearer {create_access_token(subject=next_actor_id)}"
    }
    next_action_idx = next(
        idx for idx, valid in enumerate(engine.get_action_mask()) if valid
    )

    response = client.post(
        f"/api/puco/game/{game_id}/action",
        json={
            "payload": {
                "schema_version": "action-request.v1",
                "action_index": next_action_idx,
                "canonical_id": _describe_action(next_action_idx, state={}).get("canonical_id"),
                "action_intent_id": str(uuid4()),
                "expected_state_revision": 0,
            }
        },
        headers=next_headers,
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["detail"]["error"] == "stale_state"
    assert body["detail"]["expected_state_revision"] == 0
    assert body["detail"]["current_state_revision"] == 1
