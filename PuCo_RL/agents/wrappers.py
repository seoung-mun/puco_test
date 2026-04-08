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
from types import SimpleNamespace

import torch

from agents.base import AgentWrapper
from agents.ppo_agent import Agent, PhasePPOAgent, PHASE_EMBED_DIM

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


def _load_checkpoint_state_dict(model_path: str | None) -> dict | None:
    if not model_path or not os.path.exists(model_path):
        if model_path:
            logger.warning("가중치 파일 없음: %s — 무작위 초기화로 동작", model_path)
        return None

    checkpoint = torch.load(model_path, map_location="cpu", weights_only=True)
    if isinstance(checkpoint, dict):
        return checkpoint.get("model_state_dict", checkpoint)
    return None


def _infer_residual_obs_dim(state_dict: dict | None) -> int | None:
    if not state_dict:
        return None

    embed_weight = state_dict.get("embed.0.weight")
    if isinstance(embed_weight, torch.Tensor) and embed_weight.ndim == 2:
        return int(embed_weight.shape[1])

    actor_weight = state_dict.get("actor.0.weight")
    if isinstance(actor_weight, torch.Tensor) and actor_weight.ndim == 2:
        return int(actor_weight.shape[1])

    return None


def _infer_phase_obs_dim(state_dict: dict | None) -> int | None:
    raw_dim = _infer_residual_obs_dim(state_dict)
    if raw_dim is None:
        return None
    return max(0, raw_dim - PHASE_EMBED_DIM)


def _adapt_obs_dim(obs: torch.Tensor, expected_dim: int) -> torch.Tensor:
    current_dim = int(obs.shape[-1])
    if current_dim == expected_dim:
        return obs

    # Backend/runtime env added vp_chips at flattened index 42 (210 -> 211).
    if current_dim == 211 and expected_dim == 210:
        return torch.cat([obs[..., :42], obs[..., 43:]], dim=-1)

    # Allow reverse compatibility when a newer checkpoint expects vp_chips
    # but an older serialized observation is still 210-dim.
    if current_dim == 210 and expected_dim == 211:
        pad = torch.zeros(*obs.shape[:-1], 1, device=obs.device, dtype=obs.dtype)
        return torch.cat([obs[..., :42], pad, obs[..., 42:]], dim=-1)

    raise ValueError(f"Incompatible obs_dim: expected {expected_dim}, got {current_dim}")


def _normalize_env_context(env: object | None) -> object | None:
    if env is None:
        return None
    if hasattr(env, "game"):
        return env
    return SimpleNamespace(game=env)


class PPOWrapper(AgentWrapper):
    """표준 PPO Agent 래퍼. phase_id는 사용하지 않는다."""

    def __init__(self, model_path: str | None, obs_dim: int):
        state_dict = _load_checkpoint_state_dict(model_path)
        self._expected_obs_dim = _infer_residual_obs_dim(state_dict) or obs_dim
        self._agent = Agent(obs_dim=self._expected_obs_dim, action_dim=200)
        self._agent.eval()
        if state_dict is not None:
            missing, unexpected = self._agent.load_state_dict(state_dict, strict=False)
            if missing or unexpected:
                logger.warning(
                    "PPOWrapper partial load: missing=%s unexpected=%s model=%s",
                    missing,
                    unexpected,
                    model_path,
                )

    def act(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        phase_id: int = 9,
        obs_dict: dict | None = None,
        player_idx: int | None = None,
        env: object | None = None,
    ) -> int:
        obs, mask = _ensure_batched(obs, mask)
        obs = _adapt_obs_dim(obs, self._expected_obs_dim)
        with torch.no_grad():
            action, *_ = self._agent.get_action_and_value(obs, mask)
        return int(action.item())


class HPPOWrapper(AgentWrapper):
    """계층형 PPO Agent 래퍼. phase_id로 위상별 Actor Head를 선택한다."""

    def __init__(self, model_path: str | None, obs_dim: int):
        state_dict = _load_checkpoint_state_dict(model_path)
        self._expected_obs_dim = _infer_phase_obs_dim(state_dict) or obs_dim
        self._agent = PhasePPOAgent(obs_dim=self._expected_obs_dim, action_dim=200)
        self._agent.eval()
        if state_dict is not None:
            missing, unexpected = self._agent.load_state_dict(state_dict, strict=False)
            if missing or unexpected:
                logger.warning(
                    "HPPOWrapper partial load: missing=%s unexpected=%s model=%s",
                    missing,
                    unexpected,
                    model_path,
                )

    def act(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        phase_id: int = 9,
        obs_dict: dict | None = None,
        player_idx: int | None = None,
        env: object | None = None,
    ) -> int:
        obs, mask = _ensure_batched(obs, mask)
        obs = _adapt_obs_dim(obs, self._expected_obs_dim)
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
        env: object | None = None,
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
        env: object | None = None,
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


class ShippingRushWrapper(AgentWrapper):
    """Shipping Rush Agent 래퍼."""

    def __init__(self, model_path: str | None = None, obs_dim: int = 0):
        from agents.shipping_rush_agent import ShippingRushAgent

        self._agent = ShippingRushAgent(action_dim=200)
        self._agent.eval()

    def act(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        phase_id: int = 9,
        obs_dict: dict | None = None,
        player_idx: int | None = None,
        env: object | None = None,
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
        env: object | None = None,
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


class ActionValueWrapper(AgentWrapper):
    """Action Value Agent 래퍼."""

    def __init__(self, model_path: str | None = None, obs_dim: int = 0):
        from agents.action_value_agent import ActionValueAgent

        self._agent = ActionValueAgent(action_dim=200)
        self._agent.eval()

    def act(
        self,
        obs: torch.Tensor,
        mask: torch.Tensor,
        phase_id: int = 9,
        obs_dict: dict | None = None,
        player_idx: int | None = None,
        env: object | None = None,
    ) -> int:
        obs, mask = _ensure_batched(obs, mask)
        env_context = _normalize_env_context(env)
        if env_context is None:
            logger.warning("ActionValueWrapper requires env/game context. Falling back to random valid action.")
            valid = (mask.squeeze(0) > 0.5).nonzero(as_tuple=True)[0]
            if len(valid) == 0:
                return 15
            idx = torch.randint(len(valid), (1,)).item()
            return int(valid[idx].item())

        self._agent.set_env(env_context)
        with torch.no_grad():
            action, *_ = self._agent.get_action_and_value(obs, mask)
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
        env: object | None = None,
    ) -> int:
        obs, mask = _ensure_batched(obs, mask)
        valid = (mask.squeeze(0) > 0.5).nonzero(as_tuple=True)[0]
        if len(valid) == 0:
            return 15  # 폴백: pass 액션
        idx = torch.randint(len(valid), (1,)).item()
        return int(valid[idx].item())
