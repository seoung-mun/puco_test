import json

import pytest
import torch

from app.services import model_registry
from app.services.agent_registry import resolve_model_artifact
from agents.ppo_agent import Agent


def test_allowlisted_ppo_checkpoint_uses_bootstrap_metadata(tmp_path):
    checkpoint_path = tmp_path / "PPO_PR_Server_20260401_214532_step_99942400.pth"
    agent = Agent(obs_dim=210, action_dim=200)
    torch.save(agent.state_dict(), checkpoint_path)

    artifact = model_registry.resolve_model_artifact_from_path(
        str(checkpoint_path),
        family="ppo",
    )

    assert artifact.checkpoint_filename == "PPO_PR_Server_20260401_214532_step_99942400.pth"
    assert artifact.metadata_source == "bootstrap_derived"
    assert artifact.bootstrap_profile == "ppo_pr_server_v1"
    assert artifact.obs_dim == 210
    assert artifact.action_dim == 200
    assert artifact.potential_mode == "option3"
    assert artifact.fingerprint["action_space"] == "castone.action-space.strategy-first.v1"
    assert artifact.fingerprint["mayor_semantics"] == "castone.mayor.strategy-first.v1"
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
    assert artifact.fingerprint["mayor_semantics"] == "castone.mayor.strategy-first.v1"
    assert "4949773" in artifact.fingerprint["env"]


def test_bootstrap_metadata_infers_obs_dim_from_checkpoint_when_state_dict_is_210(tmp_path):
    checkpoint_path = tmp_path / "PPO_PR_Server_20260408_120000_step_100.pth"
    agent = Agent(obs_dim=210, action_dim=200)
    torch.save(agent.state_dict(), checkpoint_path)

    artifact = model_registry.resolve_model_artifact_from_path(
        str(checkpoint_path),
        family="ppo",
    )

    assert artifact.metadata_source == "bootstrap_derived"
    assert artifact.obs_dim == 210
