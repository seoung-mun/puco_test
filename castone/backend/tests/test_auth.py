import uuid
from datetime import timedelta, datetime, timezone

import jwt as pyjwt
import pytest

from app.core.security import create_access_token, SECRET_KEY, ALGORITHM
from app.db.models import User, GameSession


def test_create_access_token():
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id)
    decoded = pyjwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == user_id
    assert "exp" in decoded


def test_perform_action_auth_success(client, db):
    # 1. Create user
    user_id = uuid.uuid4()
    user = User(id=user_id, google_id=f"gid_{uuid.uuid4().hex}", nickname="Tester")
    db.add(user)
    db.flush()

    # 2. Create game session with user as player_0
    game = GameSession(
        id=uuid.uuid4(),
        title="Auth Test Room",
        status="WAITING",
        num_players=3,
        players=[str(user_id), "BOT_random", "BOT_random"],
        host_id=str(user_id),
    )
    db.add(game)
    db.flush()

    # 3. Start game (requires JWT)
    access_token = create_access_token(subject=str(user_id))
    headers = {"Authorization": f"Bearer {access_token}"}
    start_res = client.post(f"/api/puco/game/{game.id}/start", headers=headers)
    assert start_res.status_code == 200

    # 4. Perform valid action (pick first valid action from mask)
    action_mask = start_res.json()["action_mask"]
    valid_action = next(i for i, v in enumerate(action_mask) if v == 1)
    action_data = {"payload": {"action_index": valid_action}}
    response = client.post(
        f"/api/puco/game/{game.id}/action", json=action_data, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_perform_action_auth_expired(client, db):
    """Expired JWT must return 401."""
    user_id = str(uuid.uuid4())
    expire = datetime.now(timezone.utc) - timedelta(minutes=10)
    expired_token = pyjwt.encode(
        {"exp": expire, "sub": user_id}, SECRET_KEY, algorithm=ALGORITHM
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    action_data = {"payload": {"action_index": 0}}
    response = client.post(
        f"/api/puco/game/{uuid.uuid4()}/action", json=action_data, headers=headers
    )
    assert response.status_code == 401
    assert "credentials" in response.json()["detail"].lower()


def test_perform_action_no_auth(client):
    """Missing Authorization header must return 401."""
    action_data = {"payload": {"action_index": 0}}
    response = client.post(
        f"/api/puco/game/{uuid.uuid4()}/action", json=action_data
    )
    assert response.status_code == 401
