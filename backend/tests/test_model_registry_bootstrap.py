import json

import pytest

from app.services import model_registry
from app.services.agent_registry import (
    AGENT_REGISTRY,
    clear_wrapper_cache,
    resolve_model_artifact,
)
from app.services import serving_health
from app.services.serving_health import validate_serving_health


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_wrapper_cache()
    yield
    clear_wrapper_cache()


def test_default_ppo_artifact_uses_bundle_metadata(monkeypatch):
    monkeypatch.delenv("PPO_MODEL_FILENAME", raising=False)
    monkeypatch.delenv("PPO_BUNDLE_DIR", raising=False)

    artifact = resolve_model_artifact("ppo")

    assert artifact is not None
    assert artifact.artifact_name == AGENT_REGISTRY["ppo"]["bundle_dir"]
    assert artifact.checkpoint_filename == AGENT_REGISTRY["ppo"]["model_default"]
    assert artifact.metadata_source == "bundle_v2"
    assert artifact.obs_dim == 293
    assert artifact.action_dim == 200
    assert artifact.fingerprint["action_space"] == model_registry.ACTION_SPACE_FINGERPRINT_V1
    assert artifact.fingerprint["mayor_semantics"] == model_registry.MAYOR_SEMANTICS_FINGERPRINT_V1
    assert "obs=293" in artifact.fingerprint["env"]
    assert "4949773" in artifact.fingerprint["env"]


def test_non_allowlisted_ppo_checkpoint_requires_sidecar(tmp_path):
    checkpoint_path = tmp_path / "custom_candidate.pth"
    checkpoint_path.write_bytes(b"placeholder")

    with pytest.raises(ValueError, match="sidecar"):
        model_registry.resolve_model_artifact_from_path(
            str(checkpoint_path),
            family="ppo",
        )


def test_v1_sidecar_metadata_is_parsed(tmp_path):
    checkpoint_path = tmp_path / "PPO_PR_Server_20260405_120000_step_100.pth"
    checkpoint_path.write_bytes(b"placeholder")
    sidecar_path = checkpoint_path.with_suffix(".json")
    sidecar_path.write_text(
        json.dumps(
            {
                "schema_version": "model-metadata.v1",
                "artifact_name": "PPO_PR_Server_20260405_120000_step_100",
                "family": "ppo",
                "architecture": "ppo_residual",
                "training_script": "PuCo_RL/train/train_ppo_selfplay_server.py",
                "env_module": "PuCo_RL/env/pr_env.py",
                "obs_dim": 211,
                "action_dim": 200,
                "num_players": 3,
                "network": {
                    "hidden_dim": 512,
                    "num_res_blocks": 3,
                },
                "environment": {
                    "max_game_steps": 1200,
                },
                "reward": {
                    "potential_mode": "option3",
                    "shaping_gamma": 0.99,
                },
                "fingerprint": {
                    "action_space": "custom.action-space.v99",
                },
            }
        ),
        encoding="utf-8",
    )

    artifact = model_registry.resolve_model_artifact_from_path(
        str(checkpoint_path),
        family="ppo",
    )

    assert artifact.metadata_source == "sidecar"
    assert artifact.artifact_name == "PPO_PR_Server_20260405_120000_step_100"
    assert artifact.architecture == "ppo_residual"
    assert artifact.obs_dim == 211
    assert artifact.hidden_dim == 512
    assert artifact.num_res_blocks == 3
    assert artifact.fingerprint["action_space"] == "custom.action-space.v99"
    assert artifact.fingerprint["mayor_semantics"] == model_registry.MAYOR_SEMANTICS_FINGERPRINT_V1
    assert "4949773" in artifact.fingerprint["env"]


def test_allowlisted_ppo_checkpoint_without_sidecar_is_rejected(tmp_path):
    checkpoint_path = tmp_path / "PPO_PR_Server_20260408_120000_step_100.pth"
    checkpoint_path.write_bytes(b"placeholder")

    with pytest.raises(ValueError, match="sidecar"):
        model_registry.resolve_model_artifact_from_path(
            str(checkpoint_path),
            family="ppo",
        )


def test_serving_health_degrades_when_bundle_manifest_missing(tmp_path, monkeypatch):
    checkpoint_name = AGENT_REGISTRY["ppo"]["model_default"]
    (tmp_path / checkpoint_name).write_bytes(b"placeholder")

    monkeypatch.setattr("app.services.agent_registry._MODELS_DIR", str(tmp_path))
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "bundle_dir", "missing-bundle")
    monkeypatch.setenv("MODEL_TYPE", "ppo")
    monkeypatch.setenv("PPO_BUNDLE_DIR", "missing-bundle")
    monkeypatch.delenv("PPO_MODEL_FILENAME", raising=False)

    health = validate_serving_health()

    assert health.ok is False
    assert health.artifact_name == checkpoint_name.removesuffix(".pth")
    assert health.source == "static_config"
    assert health.detail == (
        f"Bundle manifest missing: {tmp_path / 'missing-bundle' / 'manifest.json'}"
    )


def test_serving_health_degrades_when_bundle_checkpoint_missing(tmp_path, monkeypatch):
    bundle_dir = tmp_path / "broken-bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": model_registry.MODEL_BUNDLE_SCHEMA_V2,
                "bundle_id": "ppo-broken-bundle",
                "family": "ppo",
                "policy_tag": "champion",
                "architecture": "ppo_residual",
                "checkpoint_file": "missing-checkpoint.pth",
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
        ),
        encoding="utf-8",
    )
    checkpoint_name = AGENT_REGISTRY["ppo"]["model_default"]
    (tmp_path / checkpoint_name).write_bytes(b"placeholder")

    monkeypatch.setattr("app.services.agent_registry._MODELS_DIR", str(tmp_path))
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "bundle_dir", "broken-bundle")
    monkeypatch.setenv("MODEL_TYPE", "ppo")
    monkeypatch.setenv("PPO_BUNDLE_DIR", "broken-bundle")
    monkeypatch.delenv("PPO_MODEL_FILENAME", raising=False)

    health = validate_serving_health()

    assert health.ok is False
    assert health.artifact_name == checkpoint_name.removesuffix(".pth")
    assert health.source == "static_config"
    assert health.detail == (
        f"Bundle checkpoint not found: {tmp_path / 'broken-bundle' / 'missing-checkpoint.pth'}"
    )


def test_serving_health_degrades_when_prod_contract_env_missing(monkeypatch):
    monkeypatch.delenv("MODEL_TYPE", raising=False)
    monkeypatch.delenv("PPO_BUNDLE_DIR", raising=False)
    monkeypatch.delenv("PPO_MODEL_FILENAME", raising=False)
    monkeypatch.setattr(serving_health, "get_adapter_runtime", lambda _bot_type: object())

    health = validate_serving_health()

    assert health.ok is False
    assert health.artifact_name == AGENT_REGISTRY["ppo"]["bundle_dir"]
    assert health.source == "bundle_v2"
    assert "MODEL_TYPE must be 'ppo'" in (health.detail or "")
    assert "PPO_BUNDLE_DIR must be" in (health.detail or "")
