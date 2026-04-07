"""
구체 AgentWrapper 구현체.

PPOWrapper  — 표준 PPO (ppo_agent.Agent)
HPPOWrapper — 계층형 PPO (ppo_agent.HierarchicalAgent), phase_id 활용
RandomWrapper — 유효 행동 중 무작위 선택 (가중치 불필요)

새 알고리즘 추가 예시:
    class A2CWrapper(AgentWrapper):
        def __init__(self, model_path, obs_dim): ...
        def act(self, obs, mask, phase_id=9) -> int: ...
"""
import logging
import os

import torch

from agents.base import AgentWrapper
from agents.ppo_agent import Agent, PhasePPOAgent

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../models")
)


def _ensure_batched(obs: torch.Tensor, mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    if obs.dim() == 1:
        obs = obs.unsqueeze(0)
    if mask.dim() == 1:
        mask = mask.unsqueeze(0)
    return obs, mask


def _load_weights(agent: torch.nn.Module, model_path: str) -> None:
    """state_dict 또는 {'model_state_dict': ...} 형식 모두 처리."""
    if not os.path.exists(model_path):
        logger.warning("가중치 파일 없음: %s — 무작위 초기화로 동작", model_path)
        return
    try:
        checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
        state = checkpoint.get("model_state_dict", checkpoint)
        agent.load_state_dict(state, strict=False)
        logger.info("가중치 로드 완료 (strict=False): %s", model_path)
    except Exception as exc:
        logger.error("가중치 로드 실패: %s — %s", model_path, exc)


class PPOWrapper(AgentWrapper):
    """표준 PPO Agent 래퍼. phase_id는 사용하지 않는다."""

    def __init__(self, model_path: str | None, obs_dim: int):
        self._agent = Agent(obs_dim=obs_dim, action_dim=200)
        self._agent.eval()
        if model_path:
            _load_weights(self._agent, model_path)

    def act(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        phase_id: int = 9,
        obs_dict: dict | None = None,
        player_idx: int | None = None,
    ) -> int:
        obs, mask = _ensure_batched(obs, mask)
        with torch.no_grad():
            action, *_ = self._agent.get_action_and_value(obs, mask)
        return int(action.item())


class HPPOWrapper(AgentWrapper):
    """계층형 PPO Agent 래퍼. phase_id로 위상별 Actor Head를 선택한다."""

    def __init__(self, model_path: str | None, obs_dim: int):
        self._agent = PhasePPOAgent(obs_dim=obs_dim, action_dim=200)
        self._agent.eval()
        if model_path:
            _load_weights(self._agent, model_path)

    def act(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        phase_id: int = 9,
        obs_dict: dict | None = None,
        player_idx: int | None = None,
    ) -> int:
        obs, mask = _ensure_batched(obs, mask)
        phase_tensor = torch.tensor([phase_id], dtype=torch.long)
        with torch.no_grad():
            action, *_ = self._agent.get_action_and_value(obs, mask, phase_tensor)
        return int(action.item())


class RuleBasedWrapper(AgentWrapper):
    """Rule-Based Agent 래퍼. 10가지 휴리스틱 전략 중 무작위 선택."""

    def __init__(self, model_path: str | None = None, obs_dim: int = 0):
        from agents.rule_based_agent import RuleBasedAgent
        self._agent = RuleBasedAgent(action_dim=200)
        self._agent.eval()

    def act(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        phase_id: int = 9,
        obs_dict: dict | None = None,
        player_idx: int | None = None,
    ) -> int:
        obs, mask = _ensure_batched(obs, mask)
        with torch.no_grad():
            action, *_ = self._agent.get_action_and_value(
                obs,
                mask,
                obs_dict=obs_dict,
                player_idx=player_idx,
            )
        return int(action.item())


class AdvancedRuleBasedWrapper(AgentWrapper):
    """Advanced Rule-Based Agent 래퍼."""

    def __init__(self, model_path: str | None = None, obs_dim: int = 0):
        from agents.advanced_rule_based_agent import AdvancedRuleBasedAgent
        self._agent = AdvancedRuleBasedAgent(action_dim=200)
        self._agent.eval()

    def act(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        phase_id: int = 9,
        obs_dict: dict | None = None,
        player_idx: int | None = None,
    ) -> int:
        obs, mask = _ensure_batched(obs, mask)
        with torch.no_grad():
            action, *_ = self._agent.get_action_and_value(
                obs,
                mask,
                obs_dict=obs_dict,
                player_idx=player_idx,
            )
        return int(action.item())


class FactoryRuleBasedWrapper(AgentWrapper):
    """Factory Rule-Based Agent 래퍼."""

    def __init__(self, model_path: str | None = None, obs_dim: int = 0):
        from agents.factory_rule_based_agent import FactoryRuleBasedAgent
        self._agent = FactoryRuleBasedAgent(action_dim=200)
        self._agent.eval()

    def act(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        phase_id: int = 9,
        obs_dict: dict | None = None,
        player_idx: int | None = None,
    ) -> int:
        obs, mask = _ensure_batched(obs, mask)
        with torch.no_grad():
            action, *_ = self._agent.get_action_and_value(
                obs,
                mask,
                obs_dict=obs_dict,
                player_idx=player_idx,
            )
        return int(action.item())


class RandomWrapper(AgentWrapper):
    """유효 행동 중 무작위 선택. 가중치 파일 불필요."""

    def __init__(self, model_path: str | None = None, obs_dim: int = 0):
        pass  # 모델 없음

    def act(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        phase_id: int = 9,
        obs_dict: dict | None = None,
        player_idx: int | None = None,
    ) -> int:
        obs, mask = _ensure_batched(obs, mask)
        valid = (mask.squeeze(0) > 0.5).nonzero(as_tuple=True)[0]
        if len(valid) == 0:
            return 15  # 폴백: pass 액션
        idx = torch.randint(len(valid), (1,)).item()
        return int(valid[idx].item())
