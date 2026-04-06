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
        api_key = os.getenv("INTERNAL_API_KEY", "")
        if api_key:
            c.headers.update({"X-API-Key": api_key})
        yield c


# ------------------------------------------------------------------ #
#  Helper: start a fresh single-player game                           #
# ------------------------------------------------------------------ #

def _api_key_headers():
    key = os.getenv("INTERNAL_API_KEY", "")
    return {"X-API-Key": key} if key else {}


def _start_game(client, num_players=3):
    headers = _api_key_headers()
    client.post("/api/set-mode/single", headers=headers)
    resp = client.post("/api/new-game", json={"num_players": num_players,
                                               "player_names": [f"P{i}" for i in range(num_players)]},
                       headers=headers)
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


# ================================================================== #
#  Feature 4: mayor-distribute 에러 응답 구조화                         #
# ================================================================== #

def _enter_mayor_phase(client):
    """게임을 시작하고 Mayor 역할을 선택하여 mayor_action 페이즈로 진입.
    Returns (state_after_mayor_select,) or raises pytest.skip if Mayor not available.
    """
    headers = _api_key_headers()
    _start_game(client, num_players=3)
    # Role selection: select Mayor (role name = "mayor")
    # actions router prefix = /action
    res = client.post("/api/action/select-role", json={"player": "P0", "role": "mayor"}, headers=headers)
    if res.status_code != 200:
        import pytest as _pytest
        _pytest.skip(f"Mayor role selection failed: {res.json()}")
    state = res.json()
    if state["meta"]["phase"] != "mayor_action":
        import pytest as _pytest
        _pytest.skip(f"Expected mayor_action phase, got {state['meta']['phase']}")
    return state


def _make_invalid_legacy_distribution(state):
    """실제 현재 상태를 보고, 명시적으로 capacity를 초과하는 배치를 만든다."""
    active_player = state["meta"]["active_player"]
    player_data = state["players"][active_player]
    distribution = [0] * 24

    for idx, plantation in enumerate(player_data["island"]["plantations"]):
        capacity = plantation.get("capacity", 1)
        if capacity < 3:
            distribution[idx] = capacity + 1
            return distribution

    for idx, building in enumerate(player_data["city"]["buildings"]):
        capacity = building.get("capacity", 0)
        if capacity < 3:
            distribution[12 + idx] = capacity + 1
            return distribution

    pytest.skip("명시적으로 over-capacity를 만들 수 있는 Mayor 슬롯이 없습니다.")


class TestMayorDistributeErrorFormat:
    """
    TDD: mayor-distribute 슬롯 검증 실패 시 응답이 진단 정보를 포함한
    구조화된 dict 여야 한다.

    현재(RED): detail이 문자열 "슬롯 N: M명 배치 불가. 유효한 값: [...]"
    목표(GREEN): detail이 dict — slot, attempted, valid_amounts,
                 slot_capacity, slot_info, unplaced_colonists,
                 distribution_received 포함
    """

    def test_slot_capacity_error_returns_400(self, client):
        """실제로 존재하는 슬롯에 capacity 초과 배치를 보내면 400 반환."""
        state = _enter_mayor_phase(client)
        distribution = _make_invalid_legacy_distribution(state)
        res = client.post("/api/action/mayor-distribute", json={
            "player": "P0",
            "distribution": distribution,
        })
        assert res.status_code == 400

    def test_slot_capacity_error_detail_is_dict(self, client):
        """400 응답의 detail은 문자열이 아닌 dict여야 한다."""
        state = _enter_mayor_phase(client)
        distribution = _make_invalid_legacy_distribution(state)
        res = client.post("/api/action/mayor-distribute", json={
            "player": "P0",
            "distribution": distribution,
        })
        assert res.status_code == 400
        detail = res.json()["detail"]
        assert isinstance(detail, dict), (
            f"detail은 진단 정보 dict여야 합니다. 현재 타입: {type(detail).__name__!r}, 값: {detail!r}"
        )

    def test_slot_capacity_error_detail_has_slot_capacity(self, client):
        """detail에 slot_capacity 필드가 있어야 한다 (왜 실패했는지 알 수 있음)."""
        state = _enter_mayor_phase(client)
        distribution = _make_invalid_legacy_distribution(state)
        res = client.post("/api/action/mayor-distribute", json={
            "player": "P0",
            "distribution": distribution,
        })
        assert res.status_code == 400
        detail = res.json()["detail"]
        assert isinstance(detail, dict), f"detail이 dict가 아님: {detail!r}"
        assert "slot_capacity" in detail, (
            f"detail에 slot_capacity 없음. 현재 키: {list(detail.keys()) if isinstance(detail, dict) else 'N/A'}"
        )

    def test_slot_capacity_error_detail_has_slot_info(self, client):
        """detail에 slot_info 필드가 있어야 한다 (슬롯에 뭐가 있는지 알 수 있음)."""
        state = _enter_mayor_phase(client)
        distribution = _make_invalid_legacy_distribution(state)
        res = client.post("/api/action/mayor-distribute", json={
            "player": "P0",
            "distribution": distribution,
        })
        assert res.status_code == 400
        detail = res.json()["detail"]
        assert isinstance(detail, dict), f"detail이 dict가 아님: {detail!r}"
        assert "slot_info" in detail, "detail에 slot_info 없음"

    def test_slot_capacity_error_detail_has_distribution_received(self, client):
        """detail에 distribution_received가 있어야 한다 (무엇을 보냈는지 알 수 있음)."""
        state = _enter_mayor_phase(client)
        distribution = _make_invalid_legacy_distribution(state)
        res = client.post("/api/action/mayor-distribute", json={
            "player": "P0",
            "distribution": distribution,
        })
        assert res.status_code == 400
        detail = res.json()["detail"]
        assert isinstance(detail, dict), f"detail이 dict가 아님: {detail!r}"
        assert "distribution_received" in detail, "detail에 distribution_received 없음"
        assert detail["distribution_received"] == distribution

    def test_slot_capacity_error_detail_has_unplaced_colonists(self, client):
        """detail에 unplaced_colonists가 있어야 한다 (이주민 수 확인 가능)."""
        state = _enter_mayor_phase(client)
        distribution = _make_invalid_legacy_distribution(state)
        res = client.post("/api/action/mayor-distribute", json={
            "player": "P0",
            "distribution": distribution,
        })
        assert res.status_code == 400
        detail = res.json()["detail"]
        assert isinstance(detail, dict), f"detail이 dict가 아님: {detail!r}"
        assert "unplaced_colonists" in detail, "detail에 unplaced_colonists 없음"

    def test_valid_all_zero_distribution_completes_mayor(self, client):
        """이주민이 없는 경우 전부 0인 distribution은 200 반환 (또는 이주민 배치 강제되면 skip)."""
        state = _enter_mayor_phase(client)
        active_player = state["meta"]["active_player"]
        player_data = state["players"][active_player]
        unplaced = player_data["city"]["colonists_unplaced"]

        if unplaced > 0:
            # 이주민이 있으면 최소 1개는 배치해야 할 수 있으므로 skip
            import pytest as _pytest
            _pytest.skip(f"Player has {unplaced} colonists — all-zero dist may be invalid")

        distribution = [0] * 24
        res = client.post("/api/action/mayor-distribute", json={
            "player": "P0",
            "distribution": distribution,
        })
        assert res.status_code == 200
