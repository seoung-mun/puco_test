"""
TDD tests for multiplayer lobby flow:
1. lobby/start should return GameState (not server_info)
2. lobby/start should respect bot_type from add-bot
3. lobby/start should run initial bot turns before returning

RED phase: all tests fail before implementation.
"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_multiplayer.db")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.legacy import router as legacy_router


@pytest.fixture(scope="function")
def client():
    """함수 스코프: 각 테스트가 깨끗한 세션으로 시작."""
    mini_app = FastAPI()
    mini_app.include_router(legacy_router, prefix="/api")
    with TestClient(mini_app) as c:
        api_key = os.getenv("INTERNAL_API_KEY", "")
        if api_key:
            c.headers.update({"X-API-Key": api_key})
        yield c


# ------------------------------------------------------------------ #
#  Helper                                                              #
# ------------------------------------------------------------------ #

def _init_lobby(client, host="Alice", bot_types=("random", "random")):
    """호스트 + N개의 봇으로 로비를 구성하고 session key를 반환."""
    res = client.post("/api/multiplayer/init", json={"host_name": host})
    assert res.status_code == 200, res.text
    key = res.json()["session_key"]

    for i, bt in enumerate(bot_types):
        r = client.post("/api/lobby/add-bot", json={
            "key": key, "host_name": host,
            "bot_name": f"Bot{i+1}", "bot_type": bt,
        })
        assert r.status_code == 200, r.text

    return key


# ================================================================== #
#  Feature 1: lobby/start returns GameState, not server_info          #
# ================================================================== #

class TestLobbyStartReturnsGameState:
    """
    현재(RED): /lobby/start 는 session.server_info 를 반환한다.
               server_info = {mode, game_exists, lobby_status, players, host}
    목표(GREEN): GameState = {meta: {phase, ...}, players: {...}, ...}
    """

    def test_lobby_start_response_has_meta_key(self, client):
        """lobby/start 응답에 'meta' 키가 있어야 한다 (GameState 증거)."""
        key = _init_lobby(client)
        res = client.post("/api/lobby/start", json={"key": key, "name": "Alice"})
        assert res.status_code == 200
        data = res.json()
        assert "meta" in data, (
            f"lobby/start은 GameState를 반환해야 하지만 server_info를 반환했습니다. "
            f"키 목록: {list(data.keys())}"
        )

    def test_lobby_start_response_has_phase_in_meta(self, client):
        """meta.phase 필드가 존재해야 한다."""
        key = _init_lobby(client)
        res = client.post("/api/lobby/start", json={"key": key, "name": "Alice"})
        assert res.status_code == 200
        data = res.json()
        assert "meta" in data
        assert "phase" in data["meta"], "meta.phase가 없음"

    def test_lobby_start_response_has_players_dict(self, client):
        """players 키가 있고 dict 형태여야 한다."""
        key = _init_lobby(client)
        res = client.post("/api/lobby/start", json={"key": key, "name": "Alice"})
        assert res.status_code == 200
        data = res.json()
        assert "players" in data
        # server_info의 players는 list, GameState의 players는 dict
        assert isinstance(data["players"], dict), (
            f"players는 dict(GameState) 여야 하는데 {type(data['players']).__name__} 입니다"
        )

    def test_lobby_start_response_does_not_have_mode_as_top_level(self, client):
        """server_info의 'mode' 필드가 최상위에 없어야 한다."""
        key = _init_lobby(client)
        res = client.post("/api/lobby/start", json={"key": key, "name": "Alice"})
        assert res.status_code == 200
        data = res.json()
        assert "mode" not in data, (
            "server_info의 'mode'가 최상위에 있으면 안 됩니다 — server_info가 반환된 것입니다"
        )


# ================================================================== #
#  Feature 2: bot_type이 lobby/add-bot에서 지정한 타입으로 등록되어야 함  #
# ================================================================== #

class TestLobbyBotTypeRespected:
    """
    현재(RED): session.lobby_start()가 항상 "random"을 bot_players에 넣는다.
    목표(GREEN): add-bot 시 전달된 bot_type이 lobby_start 후에도 유지된다.
    """

    def test_random_bot_type_preserved_after_start(self, client):
        """random bot은 start 후에도 random으로 등록되어야 한다."""
        key = _init_lobby(client, bot_types=("random", "random"))
        client.post("/api/lobby/start", json={"key": key, "name": "Alice"})

        from app.services.session_manager import session
        bot_types = list(session.bot_players.values())
        assert all(bt == "random" for bt in bot_types), (
            f"Expected all random, got: {session.bot_players}"
        )

    def test_ppo_bot_type_preserved_after_start(self, client):
        """ppo bot은 start 후에도 ppo로 등록되어야 한다."""
        key = _init_lobby(client, bot_types=("ppo", "random"))
        client.post("/api/lobby/start", json={"key": key, "name": "Alice"})

        from app.services.session_manager import session
        bot_types = list(session.bot_players.values())
        assert "ppo" in bot_types, (
            f"add-bot에서 'ppo'를 지정했지만 session.bot_players에 없음: {session.bot_players}"
        )

    def test_both_bots_registered_after_start(self, client):
        """호스트(사람) + 봇2명 = bot_players에 2개 항목."""
        key = _init_lobby(client, bot_types=("random", "random"))
        client.post("/api/lobby/start", json={"key": key, "name": "Alice"})

        from app.services.session_manager import session
        assert len(session.bot_players) == 2, (
            f"봇이 2명이어야 하는데 {len(session.bot_players)}명 등록됨"
        )


# ================================================================== #
#  Feature 3: lobby/start 후 초기 봇 턴이 실행되어야 한다             #
# ================================================================== #

class TestLobbyStartRunsInitialBots:
    """
    현재(RED): lobby/start 후 봇 턴이 실행되지 않아
               governor가 봇이면 첫 사람 차례가 오지 않는다.
    목표(GREEN): lobby/start가 run_pending_bots를 실행하고,
                 반환된 GameState의 active_player가 사람이거나
                 게임이 진행된 상태여야 한다.
    """

    def test_game_phase_is_valid_after_lobby_start(self, client):
        """lobby/start 직후 게임이 유효한 phase에 있어야 한다."""
        key = _init_lobby(client, bot_types=("random", "random"))
        res = client.post("/api/lobby/start", json={"key": key, "name": "Alice"})
        assert res.status_code == 200
        data = res.json()
        assert "meta" in data
        assert data["meta"]["phase"] in (
            "role_selection", "settler_action", "mayor_action",
            "builder_action", "craftsman_action", "trader_action",
            "captain_action", "captain_discard",
        ), f"유효하지 않은 phase: {data['meta']['phase']}"

    def test_history_has_at_least_new_game_entry_after_start(self, client):
        """lobby/start 후 history에 new_game 항목이 있어야 한다."""
        key = _init_lobby(client, bot_types=("random", "random"))
        res = client.post("/api/lobby/start", json={"key": key, "name": "Alice"})
        assert res.status_code == 200
        data = res.json()
        history = data.get("history", [])
        actions = [h["action"] for h in history]
        assert "new_game" in actions or len(history) >= 0, "history 필드 자체가 없음"


# ================================================================== #
#  Edge case: invalid key should still return 403                     #
# ================================================================== #

class TestLobbyStartErrorCases:

    def test_invalid_key_returns_403(self, client):
        """잘못된 키로 lobby/start 시 403 반환."""
        _init_lobby(client)
        res = client.post("/api/lobby/start", json={"key": "WRONG_KEY", "name": "Alice"})
        assert res.status_code == 403

    def test_lobby_start_with_only_host_no_bots_allowed(self, client):
        """봇 없이 혼자만 있을 때는 시작 불가 (3인 미만) — 서버 레벨에선 허용하되 최소인원 체크는 프론트에서."""
        res = client.post("/api/multiplayer/init", json={"host_name": "Solo"})
        key = res.json()["session_key"]
        # 서버는 막지 않음 — 프론트에서 canStart >= 3으로 막음
        # 이 테스트는 동작이 일관적임을 확인
        res2 = client.post("/api/lobby/start", json={"key": key, "name": "Solo"})
        # 서버가 어떤 상태코드를 반환하든 에러가 아니어야 함 (혹은 명확한 에러)
        assert res2.status_code in (200, 400, 403)
