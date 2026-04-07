"""
AgentWrapper — 모든 에이전트 알고리즘의 공통 ABC.

새 알고리즘을 추가할 때:
1. 이 클래스를 상속한 Wrapper를 wrappers.py에 구현
2. agent_registry.py의 AGENT_REGISTRY에 한 줄 추가
"""
from abc import ABC, abstractmethod
import torch


class AgentWrapper(ABC):
    """모든 에이전트 알고리즘이 구현해야 하는 단일 인터페이스."""

    @abstractmethod
    def act(
        self,
        obs: torch.Tensor,   # shape: (1, obs_dim)
        mask: torch.Tensor,  # shape: (1, action_dim)
        phase_id: int = 9,   # PuCo_RL Phase IntEnum 값 (0–8), 9는 폴백
        obs_dict: dict | None = None,
        player_idx: int | None = None,
    ) -> int:
        """유효한 행동 인덱스를 정수로 반환한다."""
        ...
