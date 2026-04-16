import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.core.security import create_access_token
from app.db.models import GameSession, User
from app.services.replay_logger import REPLAY_LOG_DIR, get_replay_file_path


@pytest.fixture(autouse=True)
def _clear_games_table(db):
    db.execute(text("DELETE FROM game_logs"))
    db.execute(text("DELETE FROM games"))
    db.flush()
    yield
    import glob
    for f in glob.glob(os.path.join(REPLAY_LOG_DIR, "*.json")):
        try:
            os.remove(f)
        except OSError:
            pass


def _make_user(db, nickname: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    db.add(User(id=user_id, google_id=f"gid_{uuid.uuid4().hex}", nickname=nickname))
    db.flush()
    return user_id


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user_id))}"}


def _make_finished_game(
    db,
    *,
    players: list[str],
    created_at: datetime,
    host_id: uuid.UUID | None = None,
    winner_id: str | None = None,
    write_replay: bool = True,
) -> uuid.UUID:
    game_id = uuid.uuid4()
    db.add(
        GameSession(
            id=game_id,
            title=f"G_{game_id}",
            status="FINISHED",
            num_players=len(players),
            players=players,
            host_id=str(host_id) if host_id else None,
            winner_id=winner_id,
            created_at=created_at,
        )
    )
    db.flush()
    if write_replay:
        _write_replay_file(game_id, [])
    return game_id


def _write_replay_file(game_id: uuid.UUID, entries: list[dict]) -> str:
    os.makedirs(REPLAY_LOG_DIR, exist_ok=True)
    path = get_replay_file_path(game_id)
    payload = {
        "format": "backend-replay.v2",
        "game_id": str(game_id),
        "entries": entries,
        "final_scores": [],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


@pytest.fixture
def cleanup_replay_files():
    created: list[str] = []
    yield created
    for path in created:
        try:
            os.remove(path)
        except OSError:
            pass


def test_list_requires_auth(client):
    response = client.get("/api/puco/replays/")
    assert response.status_code == 401


def test_list_returns_only_finished(client, db):
    user_id = _make_user(db, "viewer")
    now = datetime.now(timezone.utc)
    _make_finished_game(
        db,
        players=["BOT_random", "BOT_random", str(user_id)],
        created_at=now,
    )
    # WAITING room should NOT appear
    db.add(
        GameSession(
            id=uuid.uuid4(),
            title="Waiting Room",
            status="WAITING",
            num_players=3,
            players=["BOT_random", "BOT_random", str(user_id)],
            host_id=str(user_id),
            created_at=now,
        )
    )
    db.flush()

    response = client.get("/api/puco/replays/", headers=_auth_headers(user_id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_items"] == 1
    assert len(body["replays"]) == 1
    assert body["replays"][0]["num_players"] == 3


def test_list_sorted_by_created_at_desc(client, db):
    user_id = _make_user(db, "viewer")
    t0 = datetime.now(timezone.utc)
    older = _make_finished_game(
        db,
        players=["BOT_random", "BOT_ppo", str(user_id)],
        created_at=t0 - timedelta(hours=2),
    )
    newer = _make_finished_game(
        db,
        players=["BOT_random", "BOT_ppo", str(user_id)],
        created_at=t0,
    )

    response = client.get("/api/puco/replays/", headers=_auth_headers(user_id))
    body = response.json()
    ids = [r["game_id"] for r in body["replays"]]
    assert ids == [str(newer), str(older)]
    assert body["replays"][0]["index"] == 1
    assert body["replays"][1]["index"] == 2


def test_list_pagination(client, db):
    user_id = _make_user(db, "viewer")
    now = datetime.now(timezone.utc)
    for i in range(12):
        _make_finished_game(
            db,
            players=["BOT_random", "BOT_random", str(user_id)],
            created_at=now - timedelta(minutes=i),
        )

    r1 = client.get("/api/puco/replays/?page=1&size=10", headers=_auth_headers(user_id))
    b1 = r1.json()
    assert b1["total_items"] == 12
    assert b1["total_pages"] == 2
    assert b1["page"] == 1
    assert len(b1["replays"]) == 10
    assert b1["replays"][0]["index"] == 1

    r2 = client.get("/api/puco/replays/?page=2&size=10", headers=_auth_headers(user_id))
    b2 = r2.json()
    assert len(b2["replays"]) == 2
    assert b2["replays"][0]["index"] == 11


def test_list_page_beyond_total_returns_empty(client, db):
    user_id = _make_user(db, "viewer")
    now = datetime.now(timezone.utc)
    _make_finished_game(
        db,
        players=["BOT_random", "BOT_random", str(user_id)],
        created_at=now,
    )

    response = client.get(
        "/api/puco/replays/?page=5&size=10", headers=_auth_headers(user_id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["replays"] == []
    assert body["total_items"] == 1


def test_search_by_human_nickname(client, db):
    viewer = _make_user(db, "viewer")
    seoungmun = _make_user(db, "seoungmun")
    jimin = _make_user(db, "jimin")
    now = datetime.now(timezone.utc)
    g_seoungmun = _make_finished_game(
        db,
        players=["BOT_random", "BOT_ppo", str(seoungmun)],
        created_at=now,
    )
    _make_finished_game(
        db,
        players=["BOT_random", "BOT_ppo", str(jimin)],
        created_at=now - timedelta(minutes=1),
    )

    response = client.get(
        "/api/puco/replays/?player=seoungmun", headers=_auth_headers(viewer)
    )
    body = response.json()
    assert body["total_items"] == 1
    assert body["replays"][0]["game_id"] == str(g_seoungmun)


def test_search_by_bot_type_case_insensitive(client, db):
    viewer = _make_user(db, "viewer")
    now = datetime.now(timezone.utc)
    ppo_game = _make_finished_game(
        db,
        players=["BOT_ppo", "BOT_random", str(viewer)],
        created_at=now,
    )
    _make_finished_game(
        db,
        players=["BOT_random", "BOT_random", str(viewer)],
        created_at=now - timedelta(minutes=1),
    )

    response = client.get(
        "/api/puco/replays/?player=PPO", headers=_auth_headers(viewer)
    )
    body = response.json()
    assert body["total_items"] == 1
    assert body["replays"][0]["game_id"] == str(ppo_game)


def test_search_no_results(client, db):
    viewer = _make_user(db, "viewer")
    now = datetime.now(timezone.utc)
    _make_finished_game(
        db,
        players=["BOT_random", "BOT_random", str(viewer)],
        created_at=now,
    )
    response = client.get(
        "/api/puco/replays/?player=nobody", headers=_auth_headers(viewer)
    )
    body = response.json()
    assert body["total_items"] == 0
    assert body["replays"] == []


def test_human_player_names_sorted_alphabetically(client, db):
    viewer = _make_user(db, "viewer")
    zeta = _make_user(db, "zeta")
    alpha = _make_user(db, "alpha")
    now = datetime.now(timezone.utc)
    _make_finished_game(
        db,
        players=["BOT_random", str(zeta), str(alpha)],
        created_at=now,
    )
    response = client.get("/api/puco/replays/", headers=_auth_headers(viewer))
    body = response.json()
    assert body["replays"][0]["human_player_names"] == ["alpha", "zeta"]


def test_display_label_format_with_nn(client, db):
    viewer = _make_user(db, "viewer")
    human = _make_user(db, "seoungmun")
    day = datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc)
    _make_finished_game(
        db,
        players=["BOT_random", "BOT_ppo", str(human)],
        created_at=day,
    )
    _make_finished_game(
        db,
        players=["BOT_random", "BOT_ppo", str(human)],
        created_at=day + timedelta(hours=1),
    )
    response = client.get("/api/puco/replays/", headers=_auth_headers(viewer))
    body = response.json()
    labels = sorted(r["display_label"] for r in body["replays"])
    assert labels == [
        "04_13_Random_Ppo_seoungmun_01",
        "04_13_Random_Ppo_seoungmun_02",
    ]


def test_winner_resolved_to_display_name(client, db):
    viewer = _make_user(db, "viewer")
    human = _make_user(db, "seoungmun")
    now = datetime.now(timezone.utc)
    _make_finished_game(
        db,
        players=["BOT_random", "BOT_ppo", str(human)],
        created_at=now,
        winner_id=str(human),
    )
    response = client.get("/api/puco/replays/", headers=_auth_headers(viewer))
    body = response.json()
    assert body["replays"][0]["winner"] == "seoungmun"


def test_detail_returns_replay_frames_filtered_by_rich_state(
    client, db, cleanup_replay_files
):
    viewer = _make_user(db, "viewer")
    now = datetime.now(timezone.utc)
    game_id = _make_finished_game(
        db,
        players=["BOT_random", "BOT_random", str(viewer)],
        created_at=now,
    )
    entries = [
        {"step": 0, "action": "Select Role", "rich_state": {"meta": {"round": 1}}},
        {"step": 1, "action": "Mayor batch", "rich_state": None},
        {"step": 2, "action": "Builder", "rich_state": {"meta": {"round": 2}}},
    ]
    cleanup_replay_files.append(_write_replay_file(game_id, entries))

    response = client.get(
        f"/api/puco/replays/{game_id}", headers=_auth_headers(viewer)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_frames"] == 2
    assert len(body["replay_frames"]) == 2
    assert body["replay_frames"][0]["frame_index"] == 0
    assert body["replay_frames"][1]["frame_index"] == 1
    assert body["replay_frames"][0]["step"] == 0
    assert body["replay_frames"][1]["step"] == 2


def test_detail_404_when_game_missing(client, db):
    viewer = _make_user(db, "viewer")
    response = client.get(
        f"/api/puco/replays/{uuid.uuid4()}", headers=_auth_headers(viewer)
    )
    assert response.status_code == 404


def test_detail_404_when_status_not_finished(client, db):
    viewer = _make_user(db, "viewer")
    game_id = uuid.uuid4()
    db.add(
        GameSession(
            id=game_id,
            title="Still Going",
            status="PROGRESS",
            num_players=3,
            players=["BOT_random", "BOT_random", str(viewer)],
            host_id=str(viewer),
        )
    )
    db.flush()
    response = client.get(
        f"/api/puco/replays/{game_id}", headers=_auth_headers(viewer)
    )
    assert response.status_code == 404


def test_detail_404_when_replay_file_missing(client, db):
    viewer = _make_user(db, "viewer")
    now = datetime.now(timezone.utc)
    game_id = _make_finished_game(
        db,
        players=["BOT_random", "BOT_random", str(viewer)],
        created_at=now,
    )
    # Ensure file does NOT exist
    path = get_replay_file_path(game_id)
    if os.path.exists(path):
        os.remove(path)

    response = client.get(
        f"/api/puco/replays/{game_id}", headers=_auth_headers(viewer)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "replay_file_not_found"


def test_detail_empty_replay_frames_when_no_rich_state(
    client, db, cleanup_replay_files
):
    viewer = _make_user(db, "viewer")
    now = datetime.now(timezone.utc)
    game_id = _make_finished_game(
        db,
        players=["BOT_random", "BOT_random", str(viewer)],
        created_at=now,
    )
    entries = [{"step": 0, "action": "x", "rich_state": None}]
    cleanup_replay_files.append(_write_replay_file(game_id, entries))

    response = client.get(
        f"/api/puco/replays/{game_id}", headers=_auth_headers(viewer)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_frames"] == 0
    assert body["replay_frames"] == []
