import json
import uuid

from app.core.security import create_access_token
from app.db.models import GameSession, User


def test_action_request_writes_replay_json(client, db, tmp_path, monkeypatch):
    replay_dir = tmp_path / "replay"
    replay_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.services.replay_logger.REPLAY_LOG_DIR", str(replay_dir))

    users = []
    for idx in range(3):
        user_id = uuid.uuid4()
        user = User(id=user_id, google_id=f"gid_{uuid.uuid4().hex}", nickname=f"ReplayTester{idx}")
        db.add(user)
        users.append(user)
    db.flush()

    game = GameSession(
        id=uuid.uuid4(),
        title="Replay Integration Room",
        status="WAITING",
        num_players=3,
        players=[str(user.id) for user in users],
        host_id=str(users[0].id),
    )
    db.add(game)
    db.flush()

    start_headers = {"Authorization": f"Bearer {create_access_token(subject=str(users[0].id))}"}
    start_res = client.post(f"/api/puco/game/{game.id}/start", headers=start_headers)
    assert start_res.status_code == 200

    action_mask = start_res.json()["action_mask"]
    valid_action = next(i for i, flag in enumerate(action_mask) if flag == 1)
    current_player_idx = int(start_res.json()["state"]["meta"]["active_player"].split("_")[1])
    current_user = users[current_player_idx]
    action_headers = {"Authorization": f"Bearer {create_access_token(subject=str(current_user.id))}"}
    response = client.post(
        f"/api/puco/game/{game.id}/action",
        json={"payload": {"action_index": valid_action}},
        headers=action_headers,
    )

    assert response.status_code == 200

    replay_path = replay_dir / f"{game.id}.json"
    assert replay_path.exists()

    data = json.loads(replay_path.read_text(encoding="utf-8"))
    assert data["game_id"] == str(game.id)
    assert data["title"] == "Replay Integration Room"
    assert data["players"][current_player_idx]["display_name"] == current_user.nickname
    assert data["entries"]
    assert data["entries"][0]["action_id"] == valid_action
    assert data["entries"][0]["actor_id"] == str(current_user.id)
    assert isinstance(data["entries"][0]["commentary"], str)
