"""
TDD tests for:
1. Governor-relative display numbering (compute_display_order)
2. Bot agent type config + validation
3. Game state display_number field
"""
import os
import sys

# Patch DB to SQLite before any app imports so PostgreSQL is not required
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_legacy.db")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import only the legacy router to avoid full DB setup
from app.api.legacy import router as legacy_router

# Minimal app fixture — no DB required (legacy API is in-memory)
@pytest.fixture(scope="module")
def client():
    mini_app = FastAPI()
    mini_app.include_router(legacy_router, prefix="/api")
    with TestClient(mini_app) as c:
        yield c


# ------------------------------------------------------------------ #
#  Helper: start a fresh single-player game                           #
# ------------------------------------------------------------------ #

def _start_game(client, num_players=3):
    client.post("/api/set-mode/single")
    resp = client.post("/api/new-game", json={"num_players": num_players,
                                               "player_names": [f"P{i}" for i in range(num_players)]})
    assert resp.status_code == 200
    return resp.json()


# ================================================================== #
#  Feature 1: compute_display_order()                                 #
# ================================================================== #

class TestComputeDisplayOrder:
    """Pure-function tests — no HTTP needed."""

    def _fn(self):
        from app.services.state_serializer import compute_display_order
        return compute_display_order

    def test_governor_at_0_three_players(self):
        result = self._fn()(governor_idx=0, num_players=3)
        assert result == {0: 1, 1: 2, 2: 3}

    def test_governor_at_1_three_players(self):
        result = self._fn()(governor_idx=1, num_players=3)
        assert result == {1: 1, 2: 2, 0: 3}

    def test_governor_at_last_wraps_around(self):
        result = self._fn()(governor_idx=2, num_players=3)
        assert result == {2: 1, 0: 2, 1: 3}

    def test_two_player_minimum(self):
        result = self._fn()(governor_idx=1, num_players=2)
        assert result == {1: 1, 0: 2}

    def test_five_players(self):
        result = self._fn()(governor_idx=3, num_players=5)
        assert result == {3: 1, 4: 2, 0: 3, 1: 4, 2: 5}

    def test_display_numbers_unique_and_sequential_for_all_configs(self):
        """Edge case: every (governor, num_players) combo produces 1..n exactly."""
        fn = self._fn()
        for n in range(2, 6):
            for gov in range(n):
                result = fn(governor_idx=gov, num_players=n)
                assert sorted(result.values()) == list(range(1, n + 1)), \
                    f"Failed for gov={gov}, n={n}: {result}"

    def test_all_internal_indices_covered(self):
        """Every internal player index 0..n-1 appears as a key."""
        fn = self._fn()
        for n in range(2, 6):
            for gov in range(n):
                result = fn(governor_idx=gov, num_players=n)
                assert sorted(result.keys()) == list(range(n))


# ================================================================== #
#  Feature 1 (API): game state includes display_number                #
# ================================================================== #

class TestGameStateDisplayNumber:

    def test_governor_has_display_number_1(self, client):
        state = _start_game(client, num_players=3)
        gov_key = state["meta"]["governor"]
        assert state["players"][gov_key]["display_number"] == 1, \
            f"Governor {gov_key} should have display_number=1, got {state['players'][gov_key]}"

    def test_all_players_have_display_number(self, client):
        state = _start_game(client, num_players=3)
        for pkey, pdata in state["players"].items():
            assert "display_number" in pdata, f"{pkey} missing display_number"

    def test_display_numbers_are_1_to_n(self, client):
        state = _start_game(client, num_players=3)
        nums = sorted(p["display_number"] for p in state["players"].values())
        assert nums == [1, 2, 3]

    def test_display_numbers_unique(self, client):
        state = _start_game(client, num_players=3)
        nums = [p["display_number"] for p in state["players"].values()]
        assert len(nums) == len(set(nums)), "display_numbers must be unique"

    def test_display_number_correct_for_five_player_game(self, client):
        state = _start_game(client, num_players=5)
        nums = sorted(p["display_number"] for p in state["players"].values())
        assert nums == [1, 2, 3, 4, 5]


# ================================================================== #
#  Feature 2: /api/bot-types endpoint                                 #
# ================================================================== #

class TestBotTypesEndpoint:

    def test_returns_200(self, client):
        res = client.get("/api/bot-types")
        assert res.status_code == 200

    def test_returns_list(self, client):
        res = client.get("/api/bot-types")
        data = res.json()
        assert isinstance(data, list), "Response should be a list"

    def test_contains_random(self, client):
        res = client.get("/api/bot-types")
        types = [b["type"] for b in res.json()]
        assert "random" in types, "'random' bot type must be present"

    def test_contains_ppo(self, client):
        res = client.get("/api/bot-types")
        types = [b["type"] for b in res.json()]
        assert "ppo" in types, "'ppo' bot type must be present"

    def test_each_entry_has_type_and_name(self, client):
        res = client.get("/api/bot-types")
        for entry in res.json():
            assert "type" in entry, f"Missing 'type' key: {entry}"
            assert "name" in entry, f"Missing 'name' key: {entry}"

    def test_not_empty(self, client):
        res = client.get("/api/bot-types")
        assert len(res.json()) >= 1


# ================================================================== #
#  Feature 2: bot type validation in /api/bot/set                     #
# ================================================================== #

class TestBotSetValidation:

    def test_valid_random_bot_type_accepted(self, client):
        _start_game(client, num_players=3)
        res = client.post("/api/bot/set", json={"player": "player_1", "bot_type": "random"})
        assert res.status_code == 200

    def test_valid_ppo_bot_type_accepted(self, client):
        _start_game(client, num_players=3)
        res = client.post("/api/bot/set", json={"player": "player_2", "bot_type": "ppo"})
        assert res.status_code == 200

    def test_invalid_bot_type_rejected(self, client):
        """Edge case: arbitrary string not in config → 400."""
        _start_game(client, num_players=3)
        res = client.post("/api/bot/set", json={"player": "player_1", "bot_type": "gpt4_turbo"})
        assert res.status_code == 400, \
            f"Unknown bot type should be rejected with 400, got {res.status_code}"

    def test_empty_string_bot_type_rejected(self, client):
        """Edge case: empty string is not a valid bot type."""
        _start_game(client, num_players=3)
        res = client.post("/api/bot/set", json={"player": "player_1", "bot_type": ""})
        assert res.status_code == 400

    def test_case_sensitive_bot_type(self, client):
        """Edge case: 'Random' (capital) should not match 'random'."""
        _start_game(client, num_players=3)
        res = client.post("/api/bot/set", json={"player": "player_1", "bot_type": "Random"})
        assert res.status_code == 400, "Bot type matching must be case-sensitive"

    def test_out_of_range_player_rejected(self, client):
        """Edge case: player index beyond num_players."""
        _start_game(client, num_players=3)
        res = client.post("/api/bot/set", json={"player": "player_9", "bot_type": "random"})
        assert res.status_code == 400, "Out-of-range player index should return 400"
