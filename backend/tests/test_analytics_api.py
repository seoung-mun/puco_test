import uuid
from datetime import datetime, timezone, timedelta

from app.core.security import create_access_token
from app.db.models import GameSession, Replay, User


def _make_user(db, nickname: str) -> User:
    user = User(
        id=uuid.uuid4(),
        google_id=f"gid_{uuid.uuid4().hex}",
        nickname=nickname,
    )
    db.add(user)
    db.flush()
    return user


def _make_game(
    db,
    *,
    players: list[str],
    winner_id: str | None,
    created_at: datetime,
) -> GameSession:
    game = GameSession(
        id=uuid.uuid4(),
        title=f"Game_{uuid.uuid4().hex[:6]}",
        status="FINISHED",
        num_players=len(players),
        players=players,
        winner_id=winner_id,
        created_at=created_at,
    )
    db.add(game)
    db.flush()
    return game


def _make_replay(db, game_id, final_scores: list[dict]) -> Replay:
    replay = Replay(
        game_id=game_id,
        payload={
            "format": "backend-replay.v2",
            "game_id": str(game_id),
            "entries": [],
            "final_scores": final_scores,
        },
    )
    db.add(replay)
    db.flush()
    return replay


def _auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user.id))}"}


def _base_ts(offset_seconds: int = 0) -> datetime:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return base + timedelta(seconds=offset_seconds)


def test_lineup_summary_requires_auth(client):
    response = client.get("/api/puco/analytics/me/lineup-summary")
    assert response.status_code == 401


def test_lineup_summary_returns_current_user_rows_only(client, db):
    viewer = _make_user(db, "Alice")
    other = _make_user(db, "Bob")
    outsider = _make_user(db, "Carol")

    game = _make_game(
        db,
        players=[str(viewer.id), str(other.id), "BOT_ppo"],
        winner_id=str(viewer.id),
        created_at=_base_ts(10),
    )
    _make_replay(
        db,
        game.id,
        final_scores=[
            {"actor_id": str(viewer.id), "display_name": viewer.nickname, "vp": 35, "tiebreaker": 3, "winner": True},
            {"actor_id": str(other.id), "display_name": other.nickname, "vp": 31, "tiebreaker": 2, "winner": False},
            {"actor_id": "BOT_ppo", "display_name": "ppo", "vp": 25, "tiebreaker": 1, "winner": False},
        ],
    )
    _make_game(
        db,
        players=[str(outsider.id), str(other.id), "BOT_ppo"],
        winner_id=str(outsider.id),
        created_at=_base_ts(20),
    )
    db.commit()

    response = client.get(
        "/api/puco/analytics/me/lineup-summary",
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["ordered_players"] == [viewer.nickname, other.nickname, "ppo"]
    assert body[0]["my_seat"] == 1
    assert body[0]["games"] == 1


def test_recent_games_respects_limit_and_returns_enriched_three_player_rows(client, db):
    viewer = _make_user(db, "Alice")
    other = _make_user(db, "Bob")

    older = _make_game(
        db,
        players=[str(viewer.id), "BOT_ppo", str(other.id)],
        winner_id=str(viewer.id),
        created_at=_base_ts(10),
    )
    newer = _make_game(
        db,
        players=[str(other.id), str(viewer.id), "BOT_action_value"],
        winner_id=str(other.id),
        created_at=_base_ts(20),
    )

    _make_replay(
        db,
        older.id,
        final_scores=[
            {"actor_id": str(viewer.id), "display_name": viewer.nickname, "vp": 34, "tiebreaker": 3, "winner": True},
            {"actor_id": str(other.id), "display_name": other.nickname, "vp": 30, "tiebreaker": 2, "winner": False},
            {"actor_id": "BOT_ppo", "display_name": "ppo", "vp": 28, "tiebreaker": 1, "winner": False},
        ],
    )
    _make_replay(
        db,
        newer.id,
        final_scores=[
            {"actor_id": str(other.id), "display_name": other.nickname, "vp": 36, "tiebreaker": 4, "winner": True},
            {"actor_id": str(viewer.id), "display_name": viewer.nickname, "vp": 32, "tiebreaker": 3, "winner": False},
            {"actor_id": "BOT_action_value", "display_name": "action_value", "vp": 24, "tiebreaker": 1, "winner": False},
        ],
    )
    db.commit()

    response = client.get(
        "/api/puco/analytics/me/recent-games?limit=1",
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["game_id"] == str(newer.id)
    assert body[0]["ordered_players"] == [other.nickname, viewer.nickname, "action_value"]
    assert body[0]["my_seat"] == 2
    assert body[0]["my_rank"] == 2
    assert body[0]["winner_display_name"] == other.nickname
    assert body[0]["score_data_available"] is True
