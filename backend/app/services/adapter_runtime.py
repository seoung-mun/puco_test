"""
AdapterRuntime - Model bundle의 adapter를 동적 로딩하고 추론을 실행한다.

핵심 흐름:
1. manifest에서 adapter_module 경로를 읽는다.
2. importlib로 adapter class를 동적 로딩한다.
3. validate_compatibility로 호환성을 검증한다.
4. encode_obs -> model forward (masked argmax) -> decode_action을 수행한다.

Serving semantics는 학습 시점의 stochastic 정책과 다르게
masked logits에 대한 deterministic argmax를 사용한다.
replay parity와 promotion gate는 모두 이 serving semantics 기준이다.
"""
from __future__ import annotations

import importlib
import logging
from typing import Any, Dict

import numpy as np
import torch

from app.services.canonical_action import (
    CANONICAL_ACTION_VERSION,
    build_canonical_action_catalog,
)
from app.services.canonical_state import (
    CANONICAL_STATE_VERSION,
    build_canonical_state,
)
from app.services.engine_gateway.bootstrap import ensure_puco_rl_path

logger = logging.getLogger(__name__)

RUNTIME_VERSIONS = {
    "canonical_state_version": CANONICAL_STATE_VERSION,
    "canonical_action_version": CANONICAL_ACTION_VERSION,
}


def load_adapter_class(adapter_module_path: str):
    """'common.semantic293_adapter:Semantic293TypeMayorAdapter' 형태에서 class 로딩."""
    if ":" not in adapter_module_path:
        raise ValueError(
            f"adapter_module must be 'module.path:ClassName', got {adapter_module_path!r}"
        )
    module_path, class_name = adapter_module_path.rsplit(":", 1)
    ensure_puco_rl_path()
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls


class InferenceResult:
    """추론 결과와 audit/replay용 메타데이터."""

    __slots__ = (
        "engine_action", "canonical_id", "fallback_used", "fallback_reason",
        "bundle_id", "adapter_id",
        "canonical_state_version", "canonical_action_version", "phase_id",
    )

    def __init__(
        self,
        *,
        engine_action: int,
        canonical_id: str = "",
        fallback_used: bool = False,
        fallback_reason: str = "",
        bundle_id: str = "",
        adapter_id: str = "",
        canonical_state_version: str = CANONICAL_STATE_VERSION,
        canonical_action_version: str = CANONICAL_ACTION_VERSION,
        phase_id: int = 9,
    ):
        self.engine_action = int(engine_action)
        self.canonical_id = canonical_id
        self.fallback_used = bool(fallback_used)
        self.fallback_reason = fallback_reason
        self.bundle_id = bundle_id
        self.adapter_id = adapter_id
        self.canonical_state_version = canonical_state_version
        self.canonical_action_version = canonical_action_version
        self.phase_id = int(phase_id)

    def to_dict(self) -> Dict[str, Any]:
        return {slot: getattr(self, slot) for slot in self.__slots__}


class AdapterRuntime:
    """Bundle의 adapter를 관리하고 추론을 실행한다."""

    def __init__(self, manifest: Dict[str, Any], checkpoint_path: str):
        self._manifest = dict(manifest)
        self._checkpoint_path = checkpoint_path

        adapter_module = manifest["adapter_module"]
        adapter_cls = load_adapter_class(adapter_module)
        self._adapter = adapter_cls()

        self._adapter.validate_compatibility(manifest, RUNTIME_VERSIONS)

        self._model = self._load_model(manifest, checkpoint_path)

        logger.info(
            "AdapterRuntime initialized: bundle=%s adapter=%s obs_dim=%d action_dim=%d",
            manifest.get("bundle_id"),
            self._adapter.adapter_id,
            self._adapter.obs_dim,
            self._adapter.action_dim,
        )

    @staticmethod
    def _load_model(manifest: Dict[str, Any], checkpoint_path: str):
        """checkpoint를 로딩하고 모델을 초기화한다."""
        ensure_puco_rl_path()
        from agents.ppo_agent import Agent

        obs_dim = int(manifest["obs_dim"])
        action_dim = int(manifest["action_dim"])
        network = manifest.get("network") or {}

        agent_kwargs: Dict[str, Any] = {"obs_dim": obs_dim, "action_dim": action_dim}
        hidden_dim = network.get("hidden_dim")
        if hidden_dim is not None:
            agent_kwargs["hidden_dim"] = int(hidden_dim)
        num_res_blocks = network.get("num_res_blocks")
        if num_res_blocks is not None:
            agent_kwargs["num_res_blocks"] = int(num_res_blocks)

        model = Agent(**agent_kwargs)
        model.eval()

        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        if not isinstance(checkpoint, dict):
            raise ValueError(
                "Checkpoint must be a dict containing 'model_state_dict' or a raw state_dict."
            )

        state_dict = checkpoint.get("model_state_dict", checkpoint)
        if not isinstance(state_dict, dict) or not state_dict:
            raise ValueError("Checkpoint payload does not contain a valid state_dict.")

        if not any(torch.is_tensor(v) for v in state_dict.values()):
            raise ValueError("Checkpoint state_dict does not contain tensor weights.")

        load_result = model.load_state_dict(state_dict, strict=False)
        if load_result.missing_keys:
            logger.warning(
                "Model load missing keys (%d): %s",
                len(load_result.missing_keys),
                load_result.missing_keys[:10],
            )
        if load_result.unexpected_keys:
            logger.warning(
                "Model load unexpected keys (%d): %s",
                len(load_result.unexpected_keys),
                load_result.unexpected_keys[:10],
            )
        return model

    @property
    def adapter(self):
        return self._adapter

    @property
    def manifest(self) -> Dict[str, Any]:
        return self._manifest

    def infer(self, engine) -> InferenceResult:
        """전체 추론 파이프라인을 실행한다."""
        canonical_state = build_canonical_state(engine)
        action_mask_raw = engine.get_action_mask()
        catalog = build_canonical_action_catalog(action_mask_raw, canonical_state)

        player_idx = canonical_state["meta"]["current_player_idx"]
        legal_actions = catalog["legal_actions"]

        obs = self._adapter.encode_obs(canonical_state, player_idx)
        mask = self._adapter.encode_action_mask(canonical_state, legal_actions)

        obs_tensor = torch.as_tensor(np.asarray(obs), dtype=torch.float32).unsqueeze(0)
        mask_tensor = torch.as_tensor(np.asarray(mask), dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            features = self._model._shared_features(obs_tensor)
            logits = self._model.actor_head(features)
            masked_logits = torch.where(
                mask_tensor > 0.5,
                logits,
                torch.tensor(-1e8, dtype=logits.dtype),
            )
            model_action_idx = int(masked_logits.argmax(dim=-1).item())

        decode_result = self._adapter.decode_action(
            model_action_idx, canonical_state, legal_actions
        )

        return InferenceResult(
            engine_action=decode_result.engine_action,
            canonical_id=decode_result.canonical_id,
            fallback_used=decode_result.fallback_used,
            fallback_reason=decode_result.fallback_reason,
            bundle_id=str(self._manifest.get("bundle_id", "unknown")),
            adapter_id=str(self._adapter.adapter_id),
            canonical_state_version=CANONICAL_STATE_VERSION,
            canonical_action_version=CANONICAL_ACTION_VERSION,
            phase_id=int(canonical_state["meta"]["phase_id"]),
        )
