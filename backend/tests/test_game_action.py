import uuid
from sqlalchemy import text
from app.db.models import GameLog, GameSession, User
from app.core.security import create_access_token
from app.services.game_service import GameService


def test_game_action_logs_to_db(client, db):
    """Valid action must be logged to game_logs with correct JSONB structure."""
    # 1. Create users and game in DB
    users = []
    for idx in range(3):
        user_id = uuid.uuid4()
        user = User(id=user_id, google_id=f"gid_{uuid.uuid4().hex}", nickname=f"ActionTester{idx}")
        db.add(user)
        users.append(user)

    game = GameSession(
        id=uuid.uuid4(),
        title="Log Test Room",
        status="WAITING",
        num_players=3,
        players=[str(user.id) for user in users],
        host_id=str(users[0].id),
    )
    db.add(game)
    db.flush()

    start_headers = {"Authorization": f"Bearer {create_access_token(subject=str(users[0].id))}"}

    # 2. Start game
    start_res = client.post(f"/api/puco/game/{game.id}/start", headers=start_headers)
    assert start_res.status_code == 200

    # 3. Pick first valid action from mask
    action_mask = start_res.json()["action_mask"]
    valid_action = next(i for i, v in enumerate(action_mask) if v == 1)
    current_player_idx = int(start_res.json()["state"]["meta"]["active_player"].split("_")[1])
    current_user = users[current_player_idx]
    action_headers = {"Authorization": f"Bearer {create_access_token(subject=str(current_user.id))}"}
    action_data = {"payload": {"action_index": valid_action}}

    response = client.post(
        f"/api/puco/game/{game.id}/action", json=action_data, headers=action_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # 4. Verify DB log entry
    log_count = db.query(GameLog).filter(GameLog.game_id == game.id).count()
    assert log_count == 1

    # 5. Verify JSONB structure of available_options
    sql = text(
        "SELECT available_options FROM game_logs "
        "WHERE game_id = :gid ORDER BY timestamp DESC LIMIT 1"
    )
    result = db.execute(sql, {"gid": str(game.id)}).fetchone()
    assert result is not None
    mask_from_db = result[0]
    assert isinstance(mask_from_db, list)
    assert len(mask_from_db) > 0
    assert all(x in [0, 1] for x in mask_from_db)


def test_channel_action_endpoint_passes_exact_action_index_to_game_service(client, db, monkeypatch):
    user_id = uuid.uuid4()
    user = User(id=user_id, google_id=f"gid_{uuid.uuid4().hex}", nickname="TraceTester")
    db.add(user)

    game = GameSession(
        id=uuid.uuid4(),
        title="Trace Room",
        status="PROGRESS",
        num_players=3,
        players=[str(user.id), "BOT_random", "BOT_random"],
        host_id=str(user.id),
    )
    db.add(game)
    db.flush()

    captured = {}

    def fake_process_action(self, game_id, actor_id, action, suppress_broadcast=False):
        captured["game_id"] = game_id
        captured["actor_id"] = actor_id
        captured["action"] = action
        captured["suppress_broadcast"] = suppress_broadcast
        return {"state": {"meta": {"phase": "role_selection", "active_player": "player_0"}}, "action_mask": [0] * 200}

    monkeypatch.setattr(GameService, "process_action", fake_process_action)

    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}
    response = client.post(
        f"/api/puco/game/{game.id}/action",
        json={"payload": {"action_index": "39"}},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert captured["game_id"] == game.id
    assert captured["actor_id"] == str(user.id)
    assert captured["action"] == 39
    assert isinstance(captured["action"], int)
