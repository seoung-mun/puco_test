"""Tests for bundle v2 manifest support in model_registry."""
import json

import pytest
import torch

from app.services.model_registry import (
    MODEL_BUNDLE_SCHEMA_V2,
    _parse_bundle_v2,
    load_bundle_artifact,
    load_bundle_manifest,
    resolve_bundle_checkpoint,
)


def _write_bundle(tmp_path, manifest_data: dict, *, write_checkpoint: bool = True):
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "manifest.json").write_text(
        json.dumps(manifest_data), encoding="utf-8"
    )
    if write_checkpoint:
        torch.save({"model_state_dict": {"x": torch.zeros(1)}}, bundle_dir / "checkpoint.pth")
    return bundle_dir


@pytest.fixture
def sample_v2_manifest():
    return {
        "schema_version": MODEL_BUNDLE_SCHEMA_V2,
        "bundle_id": "ppo-test-v1",
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


def test_load_bundle_manifest_returns_v2_data(tmp_path, sample_v2_manifest):
    bundle_dir = _write_bundle(tmp_path, sample_v2_manifest)
    manifest = load_bundle_manifest(str(bundle_dir))
    assert manifest is not None
    assert manifest["schema_version"] == MODEL_BUNDLE_SCHEMA_V2
    assert manifest["bundle_id"] == "ppo-test-v1"


def test_load_bundle_manifest_returns_none_when_missing(tmp_path):
    assert load_bundle_manifest(str(tmp_path / "nonexistent")) is None


def test_load_bundle_manifest_returns_none_for_wrong_schema(tmp_path):
    bundle_dir = _write_bundle(
        tmp_path, {"schema_version": "model-metadata.v1"}, write_checkpoint=False
    )
    assert load_bundle_manifest(str(bundle_dir)) is None


def test_resolve_bundle_checkpoint_returns_existing_path(tmp_path, sample_v2_manifest):
    bundle_dir = _write_bundle(tmp_path, sample_v2_manifest)
    path = resolve_bundle_checkpoint(str(bundle_dir), sample_v2_manifest)
    assert path.endswith("/checkpoint.pth")


def test_resolve_bundle_checkpoint_raises_when_missing(tmp_path, sample_v2_manifest):
    bundle_dir = _write_bundle(tmp_path, sample_v2_manifest, write_checkpoint=False)
    with pytest.raises(FileNotFoundError):
        resolve_bundle_checkpoint(str(bundle_dir), sample_v2_manifest)


def test_parse_bundle_v2_creates_artifact(tmp_path, sample_v2_manifest):
    bundle_dir = _write_bundle(tmp_path, sample_v2_manifest)
    artifact = _parse_bundle_v2(sample_v2_manifest, bundle_dir=str(bundle_dir))
    assert artifact.metadata_source == "bundle_v2"
    assert artifact.obs_dim == 293
    assert artifact.action_dim == 200
    assert artifact.num_players == 3
    assert artifact.hidden_dim == 512
    assert artifact.num_res_blocks == 3
    assert artifact.architecture == "ppo_residual"
    assert artifact.policy_tag == "candidate"
    assert artifact.artifact_name == "ppo-test-v1"


def test_load_bundle_artifact_returns_model_artifact(tmp_path, sample_v2_manifest):
    bundle_dir = _write_bundle(tmp_path, sample_v2_manifest)
    artifact = load_bundle_artifact(str(bundle_dir))
    assert artifact is not None
    assert artifact.metadata_source == "bundle_v2"
    assert artifact.checkpoint_filename == "checkpoint.pth"
