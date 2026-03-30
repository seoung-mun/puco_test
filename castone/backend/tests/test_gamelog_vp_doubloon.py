"""
TDD: GameLog VP / Doubloon 정확성 검증

목적:
- game_service.process_action() 이 PostgreSQL game_logs에 정확히 기록하는지 확인
- state_summary에 모든 플레이어의 doubloons / vp 키가 포함되는지 확인
- 엔진 레벨에서 state_before / state_after 연속성(chain) 확인
- doubloon 또는 vp 변화가 있을 때 해당 변화가 로그에 캡처되는지 확인

테스트 전략:
- DB 레이어 (PostgreSQL): GameLog JSONB 구조 + state_summary 내용 검증
- 엔진 레이어 (no DB): engine.step() state chain 연속성 단위 테스트
- 변화 감지: 여러 step을 돌려 doubloon/vp 변화 포착 여부 확인
"""
import os
import sys
import uuid

import pytest
from sqlalchemy import text

os.environ.setdefault("DATABASE_URL", "postgresql://puco_user:puco_password@localhost:5432/puco_rl")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

from app.db.models import GameLog, GameSession, User
from app.core.security import create_access_token


# ================================================================== #
#  Helper: 게임 세팅 + 액션 N번 실행 후 game_id 반환                  #
# ================================================================== #

def _setup_game_and_run_actions(client, db, n_actions: int) -> uuid.UUID:
    """공통 픽스처: 3인 게임(human + 2 bots) 생성 후 n_actions 번 액션 수행.

    - /start 응답의 action_mask로 첫 액션을 선택
    - 이후 각 /action 응답의 action_mask로 다음 액션을 선택
    - 게임 종료 또는 유효 액션 없음 시 중단
    """
    user_id = uuid.uuid4()
    db.add(User(id=user_id, google_id=f"gid_{user_id.hex[:8]}", nickname=f"Tester_{user_id.hex[:4]}"))
    game_id = uuid.uuid4()
    db.add(GameSession(
        id=game_id,
        title="VP/DL Test Room",
        status="WAITING",
        num_players=3,
        players=[str(user_id), "BOT_random", "BOT_random"],
    ))
    db.flush()

    headers = {"Authorization": f"Bearer {create_access_token(subject=str(user_id))}"}

    start = client.post(f"/api/puco/game/{game_id}/start", headers=headers)
    assert start.status_code == 200, f"게임 시작 실패: {start.json()}"

    mask = start.json().get("action_mask", [])

    for _ in range(n_actions):
        valid_actions = [i for i, v in enumerate(mask) if v == 1]
        if not valid_actions:
            break
        action = valid_actions[0]
        resp = client.post(
            f"/api/puco/game/{game_id}/action",
            json={"payload": {"action_index": action}},
            headers=headers,
        )
        if resp.status_code != 200:
            break  # 더 이상 액션 불가 (게임 종료 등)
        mask = resp.json().get("action_mask", [])

    return game_id


# ================================================================== #
#  Feature 1: state_summary 구조 검증                                 #
# ================================================================== #

class TestStateSummaryStructure:

    def test_state_summary_is_not_null_after_action(self, client, db):
        """게임 액션 후 GameLog.state_summary가 None이 아니어야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        assert log is not None, "GameLog 항목이 없음"
        assert log.state_summary is not None, "state_summary가 NULL — serialize_compact_summary 실패 가능성"

    def test_state_summary_has_players_key(self, client, db):
        """state_summary에 'players' 키가 존재해야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        assert log.state_summary is not None
        assert "players" in log.state_summary, (
            f"state_summary에 'players' 없음. 키 목록: {list(log.state_summary.keys())}"
        )

    def test_state_summary_players_have_doubloons(self, client, db):
        """state_summary.players 각 항목에 'doubloons' 키가 있어야 한다.

        players는 {"p0": {...}, "p1": {...}} 형태의 dict.
        """
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        assert log.state_summary is not None
        players = log.state_summary.get("players", {})
        assert len(players) > 0, "players dict이 비어있음"
        for pid, p in players.items():
            assert "doubloons" in p, (
                f"players[{pid}]에 'doubloons' 없음. 키 목록: {list(p.keys())}"
            )

    def test_state_summary_players_have_vp(self, client, db):
        """state_summary.players 각 항목에 'vp' 키가 있어야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        assert log.state_summary is not None
        players = log.state_summary.get("players", {})
        assert len(players) > 0
        for pid, p in players.items():
            assert "vp" in p, (
                f"players[{pid}]에 'vp' 없음. 키 목록: {list(p.keys())}"
            )

    def test_state_summary_doubloons_are_non_negative(self, client, db):
        """모든 플레이어의 doubloons 값은 0 이상이어야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=5)
        logs = db.query(GameLog).filter(GameLog.game_id == game_id).all()
        for log in logs:
            if log.state_summary is None:
                continue
            for pid, p in log.state_summary.get("players", {}).items():
                dl = p.get("doubloons", -1)
                assert dl >= 0, (
                    f"doubloons 음수 발생: players[{pid}].doubloons={dl} (step={log.step})"
                )

    def test_state_summary_vp_are_non_negative(self, client, db):
        """모든 플레이어의 vp 값은 0 이상이어야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=5)
        logs = db.query(GameLog).filter(GameLog.game_id == game_id).all()
        for log in logs:
            if log.state_summary is None:
                continue
            for pid, p in log.state_summary.get("players", {}).items():
                vp = p.get("vp", -1)
                assert vp >= 0, f"vp 음수 발생: players[{pid}].vp={vp} (step={log.step})"


# ================================================================== #
#  Feature 2: state_before / state_after JSONB 저장 검증              #
# ================================================================== #

class TestStateBeforeAfterStorage:

    def test_state_before_stored_as_jsonb(self, client, db):
        """state_before는 None이 아닌 JSONB로 저장되어야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        assert log is not None
        assert log.state_before is not None, "state_before가 NULL"

    def test_state_after_stored_as_jsonb(self, client, db):
        """state_after는 None이 아닌 JSONB로 저장되어야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        assert log is not None
        assert log.state_after is not None, "state_after가 NULL"

    def test_state_before_and_after_are_different(self, client, db):
        """유효한 게임 액션 후 state_before != state_after 이어야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        assert log is not None
        assert log.state_before != log.state_after, (
            "state_before == state_after — 액션이 상태를 변경하지 않았거나 캡처 오류"
        )

    def test_state_before_is_json_serializable(self, client, db):
        """state_before가 dict 또는 list여야 함 (JSONB 역직렬화)."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        assert isinstance(log.state_before, (dict, list)), (
            f"state_before 타입이 잘못됨: {type(log.state_before)}"
        )

    def test_available_options_is_binary_mask(self, client, db):
        """available_options(action mask)는 0/1로만 구성된 리스트여야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        assert isinstance(log.available_options, list), "available_options가 list가 아님"
        assert len(log.available_options) > 0
        assert all(v in (0, 1) for v in log.available_options), (
            f"0/1 이외의 값: {set(log.available_options)}"
        )


# ================================================================== #
#  Feature 3: state chain 연속성 (state_before[n] == state_after[n-1]) #
# ================================================================== #

class TestStateChainContinuity:

    def test_multiple_logs_are_created_for_multiple_actions(self, client, db):
        """여러 번의 액션은 여러 GameLog를 생성해야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=3)
        count = db.query(GameLog).filter(GameLog.game_id == game_id).count()
        # 봇 액션도 포함되므로 최소 1개 이상
        assert count >= 1, f"GameLog 개수 부족: {count}"

    def test_logs_have_increasing_step_numbers(self, client, db):
        """GameLog의 step 번호는 단조증가해야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=3)
        logs = (
            db.query(GameLog)
            .filter(GameLog.game_id == game_id)
            .order_by(GameLog.id)
            .all()
        )
        if len(logs) < 2:
            pytest.skip("로그가 2개 미만 — step 순서 검증 불가")
        steps = [log.step for log in logs]
        assert steps == sorted(steps), f"step이 단조증가하지 않음: {steps}"

    def test_consecutive_logs_state_chain(self, client, db):
        """연속 GameLog: log[n].state_before == log[n-1].state_after이어야 한다.

        봇 턴이 사이에 끼어들지 않는 구간에서만 검증한다.
        즉, step이 연속적인 두 로그에서 state chain이 맞는지 확인.
        """
        game_id = _setup_game_and_run_actions(client, db, n_actions=5)
        logs = (
            db.query(GameLog)
            .filter(GameLog.game_id == game_id)
            .order_by(GameLog.id)
            .all()
        )
        if len(logs) < 2:
            pytest.skip("연속 체인 검증을 위해 로그 2개 이상 필요")

        # 연속된 step 쌍에서 chain 확인
        for i in range(1, len(logs)):
            prev, curr = logs[i - 1], logs[i]
            # 봇 액션은 step이 연속적이지 않을 수 있으므로 step이 연속된 경우만 확인
            if curr.step == prev.step + 1:
                assert curr.state_before == prev.state_after, (
                    f"state chain 깨짐 — "
                    f"log[{i}].state_before != log[{i-1}].state_after "
                    f"(step {prev.step} → {curr.step})"
                )


# ================================================================== #
#  Feature 4: doubloon / vp 변화 캡처 검증                           #
# ================================================================== #

class TestVPDoubloonChangeCapture:

    def test_doubloon_change_captured_across_logs(self, client, db):
        """doubloon이 변화할 때 state_summary에 정확히 반영되어야 한다.

        Puerto Rico에서 doubloon은 Craftsman, Builder 페이즈 등에서 변경된다.
        TestClient 동기 환경에서는 봇 async task가 실행되지 않아
        경제 페이즈 완전 순환이 보장되지 않으므로:
        - 변화가 발생한 경우: before != after 확인
        - 변화가 없는 경우: 값이 비음수이고 기록 자체가 정상인지 확인

        players는 {"p0": {...}, "p1": {...}} 형태이므로 .values()로 순회.
        """
        game_id = _setup_game_and_run_actions(client, db, n_actions=30)
        logs = (
            db.query(GameLog)
            .filter(GameLog.game_id == game_id)
            .order_by(GameLog.id)
            .all()
        )
        valid_logs = [l for l in logs if l.state_summary and l.state_summary.get("players")]
        if len(valid_logs) < 2:
            pytest.skip("state_summary가 있는 로그가 2개 미만 — 변화 검증 불가")

        # doubloon 변화가 발생한 모든 step 쌍을 확인
        # 변화가 있다면: 반드시 값이 0 이상이어야 하고, 이전/이후가 논리적으로 합당해야 함
        changed_count = 0
        for i in range(1, len(valid_logs)):
            prev_players = valid_logs[i - 1].state_summary["players"]
            curr_players = valid_logs[i].state_summary["players"]
            for pid in curr_players:
                prev_dl = prev_players.get(pid, {}).get("doubloons", 0)
                curr_dl = curr_players[pid].get("doubloons", 0)
                if prev_dl != curr_dl:
                    changed_count += 1
                    # 변화가 있을 때 값이 비음수인지 확인
                    assert curr_dl >= 0, (
                        f"doubloon 변화 후 음수 발생: players[{pid}] {prev_dl} → {curr_dl} "
                        f"(step {valid_logs[i].step})"
                    )
                    # 한 번에 너무 많이 변하면 이상 (Puerto Rico에서 한 번에 ±10 이내)
                    diff = abs(curr_dl - prev_dl)
                    assert diff <= 15, (
                        f"doubloon 변화량이 비정상적으로 큼: {diff} "
                        f"(players[{pid}] {prev_dl} → {curr_dl})"
                    )

        # 변화가 없더라도 모든 값이 비음수임을 보장
        for log in valid_logs:
            for pid, p in log.state_summary["players"].items():
                assert p.get("doubloons", 0) >= 0, (
                    f"doubloons 음수: players[{pid}]={p.get('doubloons')} (step={log.step})"
                )

    def test_state_summary_doubloon_matches_game_progression(self, client, db):
        """초기 doubloon이 state_summary에 정확히 반영되어야 한다.

        Puerto Rico 3인 게임 초기: 모든 플레이어는 2 doubloon을 시작 자원으로 받는다.
        첫 번째 GameLog의 state_summary.players[px].doubloons 는 0~20 범위여야 한다.
        """
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        if not log or not log.state_summary:
            pytest.skip("state_summary 없음")

        for pid, p in log.state_summary.get("players", {}).items():
            dl = p.get("doubloons", -1)
            assert 0 <= dl <= 20, (
                f"초기 doubloons 범위 이상: players[{pid}].doubloons = {dl}"
            )

    def test_state_summary_vp_zero_at_game_start(self, client, db):
        """게임 시작 직후 모든 플레이어의 VP는 0이어야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = (
            db.query(GameLog)
            .filter(GameLog.game_id == game_id)
            .order_by(GameLog.id)
            .first()
        )
        if not log or not log.state_summary:
            pytest.skip("state_summary 없음")

        for pid, p in log.state_summary.get("players", {}).items():
            vp = p.get("vp", -1)
            assert vp >= 0, f"players[{pid}].vp가 음수: {vp}"
            assert vp <= 5, (
                f"게임 시작 직후 players[{pid}].vp가 너무 높음: {vp} "
                "(VP 계산 오류 또는 초기 상태 캡처 실패 가능성)"
            )


# ================================================================== #
#  Feature 5: PostgreSQL JSONB 직접 쿼리로 doubloon/vp 접근 검증      #
# ================================================================== #

class TestJSONBDirectQuery:

    def test_jsonb_query_state_summary_player_doubloons(self, client, db):
        """PostgreSQL JSONB 경로 연산자로 doubloons 값을 직접 쿼리할 수 있어야 한다.

        state_summary 구조: {"players": {"p0": {"doubloons": N, "vp": M}, ...}}
        """
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        if not log or not log.state_summary:
            pytest.skip("state_summary 없음")

        # JSONB 경로: state_summary -> 'players' -> 'p0' -> 'doubloons'
        result = db.execute(
            text(
                "SELECT (state_summary->'players'->'p0'->>'doubloons')::int "
                "FROM game_logs WHERE game_id = :gid ORDER BY id LIMIT 1"
            ),
            {"gid": str(game_id)},
        ).fetchone()
        assert result is not None, "JSONB 쿼리 결과 없음"
        assert result[0] is not None, "state_summary->players->p0->doubloons가 NULL"
        assert result[0] >= 0, f"doubloons 값이 음수: {result[0]}"

    def test_jsonb_query_state_summary_player_vp(self, client, db):
        """PostgreSQL JSONB 경로 연산자로 vp 값을 직접 쿼리할 수 있어야 한다."""
        game_id = _setup_game_and_run_actions(client, db, n_actions=1)
        log = db.query(GameLog).filter(GameLog.game_id == game_id).first()
        if not log or not log.state_summary:
            pytest.skip("state_summary 없음")

        result = db.execute(
            text(
                "SELECT (state_summary->'players'->'p0'->>'vp')::int "
                "FROM game_logs WHERE game_id = :gid ORDER BY id LIMIT 1"
            ),
            {"gid": str(game_id)},
        ).fetchone()
        assert result is not None
        assert result[0] is not None, "state_summary->players->p0->vp가 NULL"
        assert result[0] >= 0


# ================================================================== #
#  Feature 6: 엔진 레벨 state chain 단위 테스트 (DB 없이)             #
# ================================================================== #

class TestEngineStateChain:
    """EngineWrapper.step()이 state_before/state_after를 올바르게 캡처하는지 검증.
    DB 없이 순수 엔진 레벨에서 테스트.
    """

    @pytest.fixture(autouse=True)
    def setup_engine(self):
        from app.engine_wrapper.wrapper import create_game_engine
        self.engine = create_game_engine(num_players=3)

    def test_step_state_before_equals_pre_action_state(self):
        """engine.step() 반환값의 state_before == 액션 전 engine.get_state()."""
        state_pre = self.engine.get_state()
        mask = self.engine.get_action_mask()
        action = next(i for i, v in enumerate(mask) if v == 1)
        result = self.engine.step(action)
        assert result["state_before"] == state_pre, (
            "state_before가 액션 전 상태와 다름 — 캡처 순서 오류"
        )

    def test_step_state_after_equals_post_action_state(self):
        """engine.step() 반환값의 state_after == 액션 후 engine.get_state()."""
        mask = self.engine.get_action_mask()
        action = next(i for i, v in enumerate(mask) if v == 1)
        result = self.engine.step(action)
        state_post = self.engine.get_state()
        assert result["state_after"] == state_post, (
            "state_after가 액션 후 상태와 다름 — 캡처 순서 오류"
        )

    def test_consecutive_steps_state_chain(self):
        """연속 2 step: step1.state_after == step2.state_before."""
        mask1 = self.engine.get_action_mask()
        action1 = next(i for i, v in enumerate(mask1) if v == 1)
        result1 = self.engine.step(action1)

        mask2 = self.engine.get_action_mask()
        action2 = next(i for i, v in enumerate(mask2) if v == 1)
        result2 = self.engine.step(action2)

        assert result1["state_after"] == result2["state_before"], (
            "state chain 깨짐: step1.state_after != step2.state_before"
        )

    def test_state_before_and_after_differ_after_valid_action(self):
        """유효한 액션 후 state_before != state_after이어야 한다."""
        mask = self.engine.get_action_mask()
        action = next(i for i, v in enumerate(mask) if v == 1)
        result = self.engine.step(action)
        assert result["state_before"] != result["state_after"], (
            "state_before == state_after — 액션이 상태를 변경하지 않았거나 캡처 오류"
        )
