"""Action request ingress: canonical_id mismatch returns 422 with structured body.

Spec: docs/superpowers/specs/2026-04-27-action-index-contract-fix-design.md
RED phase — tests must currently FAIL.
"""
from __future__ import annotations

import uuid

from app.core.security import create_access_token
from app.db.models import GameSession, User


def _bootstrap_progress_game(db, num_players: int = 3):
    """Create users + a PROGRESS game and start it. Returns (game_id, current_user, action_mask, current_player_idx)."""
    users = []
    for idx in range(num_players):
        user = User(
            id=uuid.uuid4(),
            google_id=f"gid_{uuid.uuid4().hex}",
            nickname=f"CanonicalTester{idx}",
        )
        db.add(user)
        users.append(user)

    game = GameSession(
        id=uuid.uuid4(),
        title="Canonical Guard Room",
        status="WAITING",
        num_players=num_players,
        players=[str(u.id) for u in users],
        host_id=str(users[0].id),
    )
    db.add(game)
    db.flush()
    return game, users


def _start_and_pick_user(client, db, game, users):
    start_headers = {
        "Authorization": f"Bearer {create_access_token(subject=str(users[0].id))}"
    }
    start_res = client.post(f"/api/puco/game/{game.id}/start", headers=start_headers)
    assert start_res.status_code == 200, start_res.text
    body = start_res.json()
    action_mask = body["action_mask"]
    current_player_idx = int(body["state"]["meta"]["active_player"].split("_")[1])
    current_user = users[current_player_idx]
    return action_mask, current_user


def test_canonical_id_mismatch_returns_422(client, db):
    game, users = _bootstrap_progress_game(db)
    _, current_user = _start_and_pick_user(client, db, game, users)

    headers = {
        "Authorization": f"Bearer {create_access_token(subject=str(current_user.id))}"
    }
    payload = {
        "payload": {
            "schema_version": "action-request.v1",
            "action_index": 8,
            "canonical_id": "settler:tile_type:corn",  # mismatch (engine action 8 == coffee)
        }
    }
    res = client.post(
        f"/api/puco/game/{game.id}/action",
        json=payload,
        headers=headers,
    )
    assert res.status_code == 422
    body = res.json()
    # 구조화된 detail dict 기대 — 현재는 Pydantic이 list를 돌려주므로 RED.
    assert isinstance(body["detail"], dict)
    assert body["detail"]["error"] == "canonical_id_mismatch"
    assert body["detail"]["submitted_canonical_id"] == "settler:tile_type:corn"
    assert body["detail"]["decoded_canonical_id"] == "settler:tile_type:coffee"


def test_canonical_id_match_processes_action(client, db):
    game, users = _bootstrap_progress_game(db)
    _, current_user = _start_and_pick_user(client, db, game, users)

    headers = {
        "Authorization": f"Bearer {create_access_token(subject=str(current_user.id))}"
    }
    payload = {
        "payload": {
            "schema_version": "action-request.v1",
            "action_index": 8,
            "canonical_id": "settler:tile_type:coffee",
        }
    }
    res = client.post(
        f"/api/puco/game/{game.id}/action",
        json=payload,
        headers=headers,
    )
    # match라면 422가 아니어야 한다. 200/400 모두 허용 (mask 충족 여부와 무관).
    assert res.status_code != 422, res.text


def test_canonical_id_omitted_processes_action(client, db):
    game, users = _bootstrap_progress_game(db)
    _, current_user = _start_and_pick_user(client, db, game, users)

    headers = {
        "Authorization": f"Bearer {create_access_token(subject=str(current_user.id))}"
    }
    payload = {
        "payload": {
            "schema_version": "action-request.v1",
            "action_index": 8,
        }
    }
    res = client.post(
        f"/api/puco/game/{game.id}/action",
        json=payload,
        headers=headers,
    )
    # canonical_id 미제공: 기존 대로 422 아니게 동작해야 한다.
    assert res.status_code != 422, res.text
