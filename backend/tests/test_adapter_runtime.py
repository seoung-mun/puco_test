"""Tests for adapter_runtime + PolicyAdapter ABC."""
import json
import os

import numpy as np
import pytest
import torch

from app.services.adapter_runtime import (
    AdapterRuntime,
    InferenceResult,
    RUNTIME_VERSIONS,
    load_adapter_class,
)
from app.services.engine_gateway.bootstrap import ensure_puco_rl_path

ensure_puco_rl_path()
from common.base_adapter import DecodeResult, PolicyAdapter  # noqa: E402


# ── PolicyAdapter ABC tests ────────────────────────────────────────────────


def test_adapter_abc_cannot_be_instantiated():
    with pytest.raises(TypeError):
        PolicyAdapter()  # type: ignore[abstract]


def test_decode_result_to_dict():
    result = DecodeResult(engine_action=42, canonical_id="role:settler")
    d = result.to_dict()
    assert d["engine_action"] == 42
    assert d["canonical_id"] == "role:settler"
    assert d["fallback_used"] is False
    assert d["fallback_reason"] == ""
    assert d["confidence"] == 1.0


def test_validate_compatibility_passes_when_supported():
    class _A(PolicyAdapter):
        @property
        def adapter_id(self): return "test.v1"
        @property
        def canonical_state_version(self): return "castone.canonical-state.v1"
        @property
        def canonical_action_version(self): return "castone.canonical-action.v1"
        @property
        def obs_dim(self): return 1
        @property
        def action_dim(self): return 1
        def encode_obs(self, state, player_idx): return np.zeros(1, dtype=np.float32)
        def encode_action_mask(self, state, legal_actions): return np.zeros(1, dtype=np.float32)
        def decode_action(self, model_action_idx, state, legal_actions):
            return DecodeResult(0)

    manifest = {
        "compatibility": {
            "supported_canonical_state_versions": ["castone.canonical-state.v1"],
            "supported_canonical_action_versions": ["castone.canonical-action.v1"],
        }
    }
    _A().validate_compatibility(manifest, RUNTIME_VERSIONS)  # no raise


def test_validate_compatibility_raises_for_unsupported():
    class _A(PolicyAdapter):
        @property
        def adapter_id(self): return "test.v1"
        @property
        def canonical_state_version(self): return "x"
        @property
        def canonical_action_version(self): return "y"
        @property
        def obs_dim(self): return 1
        @property
        def action_dim(self): return 1
        def encode_obs(self, state, player_idx): return np.zeros(1, dtype=np.float32)
        def encode_action_mask(self, state, legal_actions): return np.zeros(1, dtype=np.float32)
        def decode_action(self, model_action_idx, state, legal_actions):
            return DecodeResult(0)

    bad_manifest = {
        "compatibility": {
            "supported_canonical_state_versions": ["other.v9"],
            "supported_canonical_action_versions": ["castone.canonical-action.v1"],
        }
    }
    with pytest.raises(ValueError, match="canonical state version"):
        _A().validate_compatibility(bad_manifest, RUNTIME_VERSIONS)


# ── load_adapter_class tests ───────────────────────────────────────────────


def test_load_adapter_class_valid_path():
    cls = load_adapter_class("common.base_adapter:PolicyAdapter")
    assert cls is PolicyAdapter


def test_load_adapter_class_missing_colon_raises():
    with pytest.raises(ValueError):
        load_adapter_class("common.base_adapter.PolicyAdapter")


def test_load_adapter_class_invalid_path():
    with pytest.raises((ImportError, AttributeError)):
        load_adapter_class("nonexistent.module:FakeAdapter")


# ── AdapterRuntime tests ───────────────────────────────────────────────────


@pytest.fixture
def manifest_dict():
    return {
        "schema_version": "model-bundle.v2",
        "bundle_id": "test-bundle",
        "family": "ppo",
        "policy_tag": "candidate",
        "architecture": "ppo_residual",
        "checkpoint_file": "checkpoint.pth",
        "adapter_module": "common.semantic293_adapter:Semantic293TypeMayorAdapter",
        "adapter_version": "1.0.0",
        "canonical_state_version": "castone.canonical-state.v1",
        "canonical_action_version": "castone.canonical-action.v1",
        "obs_dim": 293,
        "action_dim": 200,
        "num_players": 3,
        "network": {"hidden_dim": 512, "num_res_blocks": 3},
        "compatibility": {
            "supported_canonical_state_versions": ["castone.canonical-state.v1"],
            "supported_canonical_action_versions": ["castone.canonical-action.v1"],
        },
    }


@pytest.fixture
def good_checkpoint(tmp_path, manifest_dict):
    """ppo_agent.Agent state_dict를 disk에 저장한다."""
    ensure_puco_rl_path()
    from agents.ppo_agent import Agent
    agent = Agent(obs_dim=manifest_dict["obs_dim"], action_dim=manifest_dict["action_dim"])
    path = tmp_path / "checkpoint.pth"
    torch.save({"model_state_dict": agent.state_dict()}, path)
    return str(path)


def test_adapter_runtime_loads_with_valid_manifest(manifest_dict, good_checkpoint):
    runtime = AdapterRuntime(manifest_dict, good_checkpoint)
    assert runtime.adapter is not None
    assert runtime.adapter.obs_dim == 293


def test_adapter_runtime_rejects_non_state_dict_checkpoint(manifest_dict, tmp_path):
    bad_checkpoint = tmp_path / "bad_checkpoint.pt"
    torch.save({"epoch": 3, "metrics": {"loss": 1.23}}, bad_checkpoint)
    with pytest.raises(ValueError, match="state_dict"):
        AdapterRuntime(manifest_dict, str(bad_checkpoint))


def test_adapter_runtime_rejects_unsupported_canonical_state(manifest_dict, good_checkpoint):
    bad = dict(manifest_dict)
    bad["compatibility"] = {
        "supported_canonical_state_versions": ["other.v9"],
        "supported_canonical_action_versions": ["castone.canonical-action.v1"],
    }
    with pytest.raises(ValueError, match="canonical state version"):
        AdapterRuntime(bad, good_checkpoint)


def test_inference_result_to_dict_round_trip():
    res = InferenceResult(
        engine_action=7,
        canonical_id="role:prospector_2",
        bundle_id="b1",
        adapter_id="a1",
        phase_id=8,
    )
    d = res.to_dict()
    # Must be JSON-serializable for replay logging.
    json.dumps(d)
    assert d["engine_action"] == 7
    assert d["bundle_id"] == "b1"
