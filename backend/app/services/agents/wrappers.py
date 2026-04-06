import os
import sys
import torch
import numpy as np
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any

logger = logging.getLogger(__name__)

# Phase constants
MAYOR_PHASE_ID = 1
MAYOR_SKIP_ACTION = 69
PASS_ACTION = 15

# PuCo_RL의 인터페이스 임포트 (PYTHONPATH=/PuCo_RL 설정 활용)
PUCO_RL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../PuCo_RL"))
if PUCO_RL_PATH not in sys.path:
    sys.path.append(PUCO_RL_PATH)

try:
    from agents.base import AgentWrapper
except ImportError:
    class AgentWrapper(ABC):
        @abstractmethod
        def act(self, obs: torch.Tensor, mask: torch.Tensor, phase_id: int = 9) -> int:
            pass

class BasePPOWrapper(AgentWrapper):
    """
    모든 PPO 계열 에이전트의 공통 전처리 레이어.
    Schema Drift(211 vs 210), Phase IndexError, Empty Mask 등을 방어함.
    """
    def __init__(self, model: torch.nn.Module, device: torch.device):
        self.model = model
        self.device = device
        self.model.eval()
        
        # 모델이 기대하는 obs_dim 추출
        if hasattr(model, "actor") and isinstance(model.actor, torch.nn.Sequential):
            # LegacyPPOAgent 구조
            self._expected_dim = model.actor[0].in_features
        elif hasattr(model, "embed") and isinstance(model.embed, torch.nn.Sequential):
            # ResidualAgent / PhasePPOAgent 구조
            self._expected_dim = model.embed[0].in_features
            # PhasePPOAgent의 경우 obs_dim + phase_embed_dim 형태임
            if hasattr(model, "phase_embed"):
                self._expected_dim -= model.phase_embed.embedding_dim
        else:
            # 기본값 (fallback)
            self._expected_dim = 210

    def _sanitize_input(self, obs: torch.Tensor, mask: torch.Tensor, phase_id: int):
        """런타임 엣지 케이스를 정제하고 안전한 입력을 반환"""
        # 1. 배치 차원 보장 (1, dim)
        if obs.dim() == 1:
            obs = obs.unsqueeze(0)
        if mask.dim() == 1:
            mask = mask.unsqueeze(0)

        current_dim = obs.shape[-1]

        # 2. Universal Dimensionality Adapter (Schema Drift 해결)
        # 현재 엔진은 211차원(vp_chips 추가), 모델이 210차원이면 idx 42 제거
        if current_dim == 211 and self._expected_dim == 210:
            obs = torch.cat([obs[..., :42], obs[..., 43:]], dim=-1)
            # logger.debug("Schema Adapter: Removed vp_chips (idx 42) for 210-dim model.")
        elif current_dim != self._expected_dim:
            # 다른 종류의 불일치는 하드웨어 연산 에러를 막기 위해 예외 발생
            raise ValueError(f"Incompatible obs_dim: expected {self._expected_dim}, got {current_dim}")

        # 3. Phase ID Clamping (IndexError 방지)
        # PhasePPOAgent는 0~8만 가능. 9 이상의 값이 들어오면 8(END_ROUND)로 클램핑
        safe_phase = min(max(0, phase_id), 8)

        # 4. Mask Validation — phase-aware fallback
        if mask.sum() == 0:
            logger.warning("Empty action mask received. phase_id=%d", phase_id)
            mask = mask.clone()
            if safe_phase == MAYOR_PHASE_ID:
                mask[0, MAYOR_SKIP_ACTION] = 1.0  # Mayor: place 0 colonists (skip)
            else:
                mask[0, PASS_ACTION] = 1.0  # Other phases: Pass

        return obs.to(self.device), mask.to(self.device), safe_phase

    def _fallback_act(self, mask: torch.Tensor) -> int:
        """에러 발생 시 최후의 보루: Random 선택"""
        mask_np = mask.cpu().numpy().flatten()
        valid_indices = np.where(mask_np > 0.5)[0]
        if len(valid_indices) == 0:
            return 15
        return int(np.random.choice(valid_indices))

class LegacyPPOAgentWrapper(BasePPOWrapper):
    """구버전 PPO 모델(3-Linear)을 위한 래퍼"""
    def act(self, obs: torch.Tensor, mask: torch.Tensor, phase_id: int = 9) -> int:
        try:
            obs, mask, _ = self._sanitize_input(obs, mask, phase_id)
            with torch.no_grad():
                action, _, _, _ = self.model.get_action_and_value(obs, mask)
                return int(action.item())
        except Exception as e:
            logger.error(f"LegacyPPO inference failed: {e}", exc_info=True)
            return self._fallback_act(mask)

class PPOAgentWrapper(BasePPOWrapper):
    """신버전(Residual/Phase) PPO 모델을 위한 래퍼"""
    def act(self, obs: torch.Tensor, mask: torch.Tensor, phase_id: int = 9) -> int:
        try:
            obs, mask, safe_phase = self._sanitize_input(obs, mask, phase_id)
            phase_tensor = torch.tensor([safe_phase], device=self.device)
            
            with torch.no_grad():
                # 모델 아키텍처별 호출 분기
                if hasattr(self.model, "phase_heads"): # PhasePPOAgent
                    action, _, _, _ = self.model.get_action_and_value(obs, mask, phase_tensor)
                else: # Standard Residual Agent
                    action, _, _, _ = self.model.get_action_and_value(obs, mask)
                return int(action.item())
        except Exception as e:
            logger.error(f"PPO inference failed: {e}", exc_info=True)
            return self._fallback_act(mask)

class RandomAgentWrapper(AgentWrapper):
    """순수 무작위 에이전트"""
    def act(self, obs: torch.Tensor, mask: torch.Tensor, phase_id: int = 9) -> int:
        mask_np = mask.cpu().numpy().flatten()
        valid_indices = np.where(mask_np > 0.5)[0]
        if len(valid_indices) == 0:
            return 15
        return int(np.random.choice(valid_indices))
