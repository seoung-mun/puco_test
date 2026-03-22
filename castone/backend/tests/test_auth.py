from datetime import timedelta, datetime
from jose import jwt
from uuid import uuid4

from app.core.security import create_access_token, SECRET_KEY, ALGORITHM
from app.db.models import User

def test_create_access_token():
    user_id = str(uuid4())
    token = create_access_token(subject=user_id)
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == user_id
    assert "exp" in decoded

def test_perform_action_auth_success(client, db):
    # 1. Create a user
    user_id = uuid4()
    user = User(id=user_id, google_id="google_123", nickname="Tester")
    db.add(user)
    db.commit()

    # 2. Create a room and start game
    room_data = {"title": "Auth Test Room", "agent_count": 0, "max_players": 3}
    res = client.post("/api/v1/rooms/", json=room_data)
    game_id = res.json()["id"]
    client.post(f"/api/v1/game/{game_id}/start")

    # 3. Create valid token
    access_token = create_access_token(subject=str(user_id))
    headers = {"Authorization": f"Bearer {access_token}"}

    # 4. Perform action
    action_data = {
        "game_id": game_id,
        "action_type": "DISCRETE",
        "payload": {"action_index": 0}
    }
    response = client.post(f"/api/v1/game/{game_id}/action", json=action_data, headers=headers)
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_perform_action_auth_expired(client, db):
    user_id = str(uuid4())
    # Create an already expired token
    expire = datetime.utcnow() - timedelta(minutes=10)
    to_encode = {"exp": expire, "sub": user_id}
    expired_token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    headers = {"Authorization": f"Bearer {expired_token}"}
    action_data = {"game_id": str(uuid4()), "action_type": "DISCRETE", "payload": {"action_index": 0}}
    
    response = client.post(f"/api/v1/game/{str(uuid4())}/action", json=action_data, headers=headers)
    assert response.status_code == 401
    assert "credentials" in response.json()["detail"].lower()

def test_perform_action_no_auth(client):
    action_data = {"game_id": str(uuid4()), "action_type": "DISCRETE", "payload": {"action_index": 0}}
    response = client.post(f"/api/v1/game/{str(uuid4())}/action", json=action_data)
    # FastAPI OAuth2PasswordBearer returns 401 if header missing
    assert response.status_code == 401
