import uuid

from app.core.security import create_access_token
from app.db.models import GameSession, User
from app.engine_wrapper.wrapper import create_game_engine
from app.services.game_service import GameService


def _make_user(db, nickname: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    db.add(User(id=user_id, google_id=f"gid_{uuid.uuid4().hex}", nickname=nickname))
    db.flush()
    return user_id


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(subject=str(user_id))}"}


def test_final_score_allows_host_spectator_for_bot_game(client, db):
    host_id = _make_user(db, "Host")
    game_id = uuid.uuid4()
    db.add(
        GameSession(
            id=game_id,
            title="Bot Spectator Game",
            status="FINISHED",
            num_players=3,
            players=["BOT_random", "BOT_random", "BOT_random"],
            host_id=str(host_id),
        )
    )
    db.flush()

    GameService.active_engines[game_id] = create_game_engine(num_players=3)
    try:
        response = client.get(
            f"/api/puco/game/{game_id}/final-score",
            headers=_auth_headers(host_id),
        )
    finally:
        GameService.active_engines.pop(game_id, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"scores", "winner", "player_order", "display_names"}
    assert len(body["player_order"]) == 3
    assert body["player_order"] == ["player_0", "player_1", "player_2"]
    assert list(body["display_names"].values()) == ["Bot (random)", "Bot (random)", "Bot (random)"]


def test_final_score_still_rejects_non_member_non_host(client, db):
    host_id = _make_user(db, "Host")
    stranger_id = _make_user(db, "Stranger")
    game_id = uuid.uuid4()
    db.add(
        GameSession(
            id=game_id,
            title="Private Final Score",
            status="FINISHED",
            num_players=3,
            players=["BOT_random", "BOT_random", "BOT_random"],
            host_id=str(host_id),
        )
    )
    db.flush()

    GameService.active_engines[game_id] = create_game_engine(num_players=3)
    try:
        response = client.get(
            f"/api/puco/game/{game_id}/final-score",
            headers=_auth_headers(stranger_id),
        )
    finally:
        GameService.active_engines.pop(game_id, None)

    assert response.status_code == 403, response.text
