"""Tests for agent_registry bundle/adapter routing."""
import json

import pytest
import torch

from app.services import agent_registry
from app.services.agent_registry import (
    AGENT_REGISTRY,
    clear_wrapper_cache,
    get_adapter_runtime,
    resolve_model_artifact,
)
from app.services.model_registry import MODEL_BUNDLE_SCHEMA_V2


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_wrapper_cache()
    yield
    clear_wrapper_cache()


def _write_bundle(bundle_dir):
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": MODEL_BUNDLE_SCHEMA_V2,
        "bundle_id": "ppo-test-bundle",
        "family": "ppo",
        "policy_tag": "candidate",
        "architecture": "ppo_residual",
        "checkpoint_file": "checkpoint.pth",
        "adapter_module": "common.semantic293_adapter:Semantic293TypeMayorAdapter",
        "adapter_version": "1.0.0",
        "obs_dim": 293,
        "action_dim": 200,
        "num_players": 3,
        "network": {"hidden_dim": 512, "num_res_blocks": 3},
        "compatibility": {
            "supported_canonical_state_versions": ["castone.canonical-state.v1"],
            "supported_canonical_action_versions": ["castone.canonical-action.v1"],
        },
    }
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    from app.services.engine_gateway.bootstrap import ensure_puco_rl_path
    ensure_puco_rl_path()
    from agents.ppo_agent import Agent
    agent = Agent(obs_dim=293, action_dim=200)
    torch.save(
        {"model_state_dict": agent.state_dict()},
        bundle_dir / "checkpoint.pth",
    )


def test_default_ppo_config_enables_adapter_bundle():
    assert AGENT_REGISTRY["ppo"]["use_adapter"] is True
    assert AGENT_REGISTRY["ppo"]["bundle_dir"] == "ppo-pr-server-semantic293-20260419"


def test_get_adapter_runtime_returns_none_when_use_adapter_false(monkeypatch):
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "use_adapter", False)
    clear_wrapper_cache()
    assert get_adapter_runtime("ppo") is None


def test_get_adapter_runtime_returns_none_for_no_bundle_config():
    assert get_adapter_runtime("random") is None


def test_get_adapter_runtime_returns_runtime_when_configured(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "bundle-test"
    _write_bundle(bundle_dir)

    monkeypatch.setattr(agent_registry, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "bundle_dir", "bundle-test")
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "use_adapter", True)
    monkeypatch.delenv("PPO_BUNDLE_DIR", raising=False)
    clear_wrapper_cache()

    runtime = get_adapter_runtime("ppo")
    assert runtime is not None
    assert runtime.adapter.obs_dim == 293
    assert runtime.adapter.action_dim == 200


def test_resolve_model_artifact_prefers_bundle_when_configured(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "bundle-test"
    _write_bundle(bundle_dir)

    monkeypatch.setattr(agent_registry, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "bundle_dir", "bundle-test")
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "use_adapter", True)
    monkeypatch.delenv("PPO_BUNDLE_DIR", raising=False)
    clear_wrapper_cache()

    artifact = resolve_model_artifact("ppo")
    assert artifact is not None
    assert artifact.metadata_source == "bundle_v2"
    assert artifact.artifact_name == "ppo-test-bundle"
    assert artifact.checkpoint_filename == "checkpoint.pth"


def test_resolve_model_artifact_falls_back_to_static_when_bundle_missing(tmp_path, monkeypatch):
    checkpoint_name = AGENT_REGISTRY["ppo"]["model_default"]
    (tmp_path / checkpoint_name).write_bytes(b"placeholder")

    monkeypatch.setattr(agent_registry, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "bundle_dir", "missing-bundle")
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "use_adapter", True)
    monkeypatch.delenv("PPO_BUNDLE_DIR", raising=False)
    monkeypatch.delenv("PPO_MODEL_FILENAME", raising=False)
    clear_wrapper_cache()

    artifact = resolve_model_artifact("ppo")
    assert artifact is not None
    assert artifact.metadata_source == "static_config"
    assert artifact.checkpoint_filename == checkpoint_name


def test_get_adapter_runtime_env_var_overrides_default(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "env-bundle"
    _write_bundle(bundle_dir)

    monkeypatch.setattr(agent_registry, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "bundle_dir", "default-bundle")
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "use_adapter", True)
    monkeypatch.setenv("PPO_BUNDLE_DIR", "env-bundle")
    clear_wrapper_cache()

    runtime = get_adapter_runtime("ppo")
    assert runtime is not None


def test_get_adapter_runtime_returns_none_when_manifest_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_registry, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "bundle_dir", "missing-bundle")
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "use_adapter", True)
    clear_wrapper_cache()

    assert get_adapter_runtime("ppo") is None


def test_get_adapter_runtime_skips_default_bundle_when_model_override_is_set(tmp_path, monkeypatch):
    nested_checkpoint = tmp_path / "ppo_checkpoints" / "smoke" / "PPO_test.pth"
    nested_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    nested_checkpoint.write_bytes(b"placeholder")

    bundle_dir = tmp_path / "default-bundle"
    _write_bundle(bundle_dir)

    monkeypatch.setattr(agent_registry, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "bundle_dir", "default-bundle")
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "use_adapter", True)
    monkeypatch.setenv("PPO_MODEL_FILENAME", "PPO_test.pth")
    monkeypatch.delenv("PPO_BUNDLE_DIR", raising=False)
    clear_wrapper_cache()

    assert get_adapter_runtime("ppo") is None


def test_resolve_model_artifact_uses_nested_model_override_when_bundle_env_missing(tmp_path, monkeypatch):
    nested_checkpoint = tmp_path / "ppo_checkpoints" / "smoke" / "PPO_test.pth"
    nested_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    nested_checkpoint.write_bytes(b"placeholder")

    bundle_dir = tmp_path / "default-bundle"
    _write_bundle(bundle_dir)

    monkeypatch.setattr(agent_registry, "_MODELS_DIR", str(tmp_path))
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "bundle_dir", "default-bundle")
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "use_adapter", True)
    monkeypatch.setenv("PPO_MODEL_FILENAME", "PPO_test.pth")
    monkeypatch.delenv("PPO_BUNDLE_DIR", raising=False)
    clear_wrapper_cache()

    artifact = resolve_model_artifact("ppo")

    assert artifact is not None
    assert artifact.metadata_source == "static_config"
    assert artifact.checkpoint_path == str(nested_checkpoint)
    assert artifact.checkpoint_filename == "PPO_test.pth"
