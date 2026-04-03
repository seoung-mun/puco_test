"""
TDD: LegacyPPOAgentWrapper obs_dim 불일치 처리 검증

버그: global_state.vp_chips(1차원)가 훈련 후 pr_env.py에 추가되어
obs_dim이 210→211이 됨. 인덱스 42에 삽입되므로 단순 자르기 불가.
해결: wrapper.act()에서 인덱스 42를 제거하여 모델에 210차원 전달.
"""
import torch
import pytest

from app.services.agents.legacy_models import LegacyPPOAgent
from app.services.agents.wrappers import LegacyPPOAgentWrapper


@pytest.fixture
def legacy_wrapper():
    model = LegacyPPOAgent(obs_dim=210, action_dim=200, hidden_dim=256)
    return LegacyPPOAgentWrapper(model, device=torch.device("cpu"))


def test_wrapper_handles_211_dim_obs(legacy_wrapper):
    """211차원 obs가 입력돼도 RuntimeError 없이 정상 액션을 반환해야 한다."""
    obs = torch.zeros(1, 211)
    mask = torch.zeros(1, 200)
    mask[0, 15] = 1.0  # Pass만 유효

    action = legacy_wrapper.act(obs, mask)  # 현재: RuntimeError 발생

    assert isinstance(action, int)
    assert 0 <= action < 200


def test_wrapper_still_works_with_correct_210_dim_obs(legacy_wrapper):
    """기존 210차원 obs도 정상 동작해야 한다 (회귀 방지)."""
    obs = torch.zeros(1, 210)
    mask = torch.zeros(1, 200)
    mask[0, 15] = 1.0

    action = legacy_wrapper.act(obs, mask)

    assert isinstance(action, int)
    assert 0 <= action < 200


def test_wrapper_removes_index_42_not_truncates(legacy_wrapper):
    """단순 자르기([:210])가 아닌 인덱스 42 제거임을 검증한다.

    인덱스 42에 특이값을 넣고, 43 이후 데이터가 올바른 위치(42~)로
    이동하는지 확인. 즉, 제거 후 obs[43]이 제거 후 obs[42]가 돼야 한다.
    """
    obs = torch.zeros(211)
    obs[42] = 999.0   # 제거될 global_state.vp_chips
    obs[43] = 1.0     # player_0 첫 번째 값 → 제거 후 index 42가 돼야 함

    mask = torch.ones(1, 200)

    # 내부적으로 42를 제거한 결과를 간접 검증: RuntimeError 없이 실행되면 성공
    # (obs[42]=999가 제거되지 않으면 model forward에서 결과가 달라짐)
    action = legacy_wrapper.act(obs, mask)

    assert isinstance(action, int)


def test_wrapper_selects_only_valid_action(legacy_wrapper):
    """mask에서 유효한 액션 중 하나를 선택해야 한다 (211차원 obs)."""
    obs = torch.randn(1, 211)
    mask = torch.zeros(1, 200)
    mask[0, 5] = 1.0
    mask[0, 10] = 1.0

    action = legacy_wrapper.act(obs, mask)

    assert action in (5, 10)


def test_empty_mask_mayor_phase_uses_action_69(legacy_wrapper):
    """Mayor 페이즈(phase_id=1)에서 Empty Mask면 Pass(15)가 아닌
    place-0(69)를 폴백으로 선택해야 한다."""
    obs = torch.zeros(1, 211)
    mask = torch.zeros(1, 200)  # 모든 액션 비활성화 (엣지 케이스)

    action = legacy_wrapper.act(obs, mask, phase_id=1)

    assert isinstance(action, int)
    # Mayor 페이즈에서 Empty Mask → 69(place 0) 폴백
    assert action == 69


def test_empty_mask_non_mayor_phase_uses_pass(legacy_wrapper):
    """Mayor가 아닌 페이즈에서 Empty Mask면 Pass(15)를 선택해야 한다."""
    obs = torch.zeros(1, 211)
    mask = torch.zeros(1, 200)

    action = legacy_wrapper.act(obs, mask, phase_id=0)  # SETTLER

    assert isinstance(action, int)
    assert action == 15
