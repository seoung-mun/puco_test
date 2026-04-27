"""
PolicyAdapter ABC - 모든 모델 adapter의 기본 인터페이스.

이 클래스를 상속하여 각 모델 번들의 encode/decode 로직을 구현한다.
backend는 이 인터페이스만 의존하고, concrete adapter는 동적으로 import한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

import numpy as np


class DecodeResult:
    """decode_action의 반환 타입."""

    __slots__ = ("engine_action", "canonical_id", "fallback_used",
                 "fallback_reason", "confidence")

    def __init__(
        self,
        engine_action: int,
        canonical_id: str = "",
        fallback_used: bool = False,
        fallback_reason: str = "",
        confidence: float = 1.0,
    ):
        self.engine_action = int(engine_action)
        self.canonical_id = canonical_id
        self.fallback_used = bool(fallback_used)
        self.fallback_reason = fallback_reason
        self.confidence = float(confidence)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_action": self.engine_action,
            "canonical_id": self.canonical_id,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "confidence": self.confidence,
        }


class PolicyAdapter(ABC):
    """모델 번들의 obs/action 변환을 담당하는 기본 인터페이스."""

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """adapter 고유 식별자. 예: 'puco.semantic293.type_mayor.v1'."""

    @property
    @abstractmethod
    def canonical_state_version(self) -> str:
        """지원하는 canonical state 버전."""

    @property
    @abstractmethod
    def canonical_action_version(self) -> str:
        """지원하는 canonical action 버전."""

    @property
    @abstractmethod
    def obs_dim(self) -> int:
        """모델이 기대하는 observation 벡터 차원."""

    @property
    @abstractmethod
    def action_dim(self) -> int:
        """모델의 action space 크기."""

    def validate_compatibility(
        self,
        manifest: Dict[str, Any],
        runtime_versions: Dict[str, Any],
    ) -> None:
        """manifest와 runtime canonical version의 호환성을 사전 검증한다."""
        rt_state = runtime_versions.get("canonical_state_version", "")
        rt_action = runtime_versions.get("canonical_action_version", "")
        compat = manifest.get("compatibility") or {}
        supported_states = compat.get("supported_canonical_state_versions", [])
        supported_actions = compat.get("supported_canonical_action_versions", [])
        if supported_states and rt_state not in supported_states:
            raise ValueError(
                f"Adapter {self.adapter_id} does not support "
                f"canonical state version '{rt_state}'. "
                f"Supported: {supported_states}"
            )
        if supported_actions and rt_action not in supported_actions:
            raise ValueError(
                f"Adapter {self.adapter_id} does not support "
                f"canonical action version '{rt_action}'. "
                f"Supported: {supported_actions}"
            )

    @abstractmethod
    def encode_obs(
        self,
        state: Dict[str, Any],
        player_idx: int,
    ) -> np.ndarray:
        """canonical state를 모델 입력 벡터로 변환한다."""

    @abstractmethod
    def encode_action_mask(
        self,
        state: Dict[str, Any],
        legal_actions: List[Dict[str, Any]],
    ) -> np.ndarray:
        """canonical legal actions를 모델 action space mask로 변환한다."""

    @abstractmethod
    def decode_action(
        self,
        model_action_idx: int,
        state: Dict[str, Any],
        legal_actions: List[Dict[str, Any]],
    ) -> DecodeResult:
        """모델 output action index를 engine action int로 변환한다."""
