import uuid
from sqlalchemy import text
from app.db.models import GameLog, GameSession, User
from app.core.security import create_access_token


def test_game_action_logs_to_db(client, db):
    """Valid action must be logged to game_logs with correct JSONB structure."""
    # 1. Create user and game in DB
    user_id = uuid.uuid4()
    user = User(id=user_id, google_id=f"gid_{uuid.uuid4().hex}", nickname="ActionTester")
    db.add(user)
    game = GameSession(
        id=uuid.uuid4(),
        title="Log Test Room",
        status="WAITING",
        num_players=3,
        players=[str(user_id), "BOT_random", "BOT_random"],
        host_id=str(user_id),
    )
    db.add(game)
    db.flush()

    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user_id))}"}

    # 2. Start game
    start_res = client.post(f"/api/puco/game/{game.id}/start", headers=headers)
    assert start_res.status_code == 200

    # 3. Pick first valid action from mask
    action_mask = start_res.json()["action_mask"]
    valid_action = next(i for i, v in enumerate(action_mask) if v == 1)
    action_data = {"payload": {"action_index": valid_action}}

    response = client.post(
        f"/api/puco/game/{game.id}/action", json=action_data, headers=headers
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
