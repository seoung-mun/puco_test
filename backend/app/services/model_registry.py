from __future__ import annotations

import functools
import inspect
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from app.services.engine_gateway.agents import ResidualAgent
from app.services.engine_gateway.env import (
    PuertoRicoEnv,
    SHAPING_GAMMA,
    get_flattened_obs_dim,
)


MODELS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../PuCo_RL/models")
)
MODEL_METADATA_SCHEMA_V1 = "model-metadata.v1"
_PPO_PR_SERVER_PATTERN = re.compile(r"^PPO_PR_Server_.*\.pth$")
ARTIFACT_FINGERPRINT_SCHEMA_V1 = "artifact-fingerprint.v1"
REPLAY_PARITY_SCHEMA_V1 = "replay-parity.v1"
ACTION_SPACE_FINGERPRINT_V1 = "castone.action-space.slot-mayor.v1"
MAYOR_SEMANTICS_FINGERPRINT_V1 = "castone.mayor.slot-direct.v1"
UPSTREAM_REMOTE = "puco-upstream"
UPSTREAM_BRANCH = "main"
UPSTREAM_COMMIT = "4949773"
UPSTREAM_SOURCE_URL = "https://github.com/dae-hany/PuertoRico-BoardGame-RL-Balancing.git"
DEFAULT_POTENTIAL_MODE = "option3"


def _stringify_fingerprint_part(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_env_fingerprint(
    *,
    env_module: str | None = None,
    num_players: int | None = None,
    obs_dim: int | None = None,
    action_dim: int | None = None,
    max_game_steps: int | None = None,
    potential_mode: str | None = None,
) -> str:
    defaults = get_ppo_pr_server_bootstrap_profile()
    parts = [
        f"{UPSTREAM_REMOTE}/{UPSTREAM_BRANCH}@{UPSTREAM_COMMIT}",
        f"source={UPSTREAM_SOURCE_URL}",
        f"env={env_module or defaults['env_module']}",
        f"players={num_players if num_players is not None else defaults['num_players']}",
        f"obs={obs_dim if obs_dim is not None else defaults['obs_dim']}",
        f"actions={action_dim if action_dim is not None else defaults['action_dim']}",
        f"max_steps={max_game_steps if max_game_steps is not None else defaults['max_game_steps']}",
        f"potential={potential_mode or defaults['potential_mode']}",
    ]
    return "|".join(parts)


def build_artifact_fingerprint(
    existing: dict[str, Any] | None = None,
    *,
    env_module: str | None = None,
    num_players: int | None = None,
    obs_dim: int | None = None,
    action_dim: int | None = None,
    max_game_steps: int | None = None,
    potential_mode: str | None = None,
) -> dict[str, str]:
    fingerprint = {
        "schema_version": ARTIFACT_FINGERPRINT_SCHEMA_V1,
        "action_space": ACTION_SPACE_FINGERPRINT_V1,
        "mayor_semantics": MAYOR_SEMANTICS_FINGERPRINT_V1,
        "env": _build_env_fingerprint(
            env_module=env_module,
            num_players=num_players,
            obs_dim=obs_dim,
            action_dim=action_dim,
            max_game_steps=max_game_steps,
            potential_mode=potential_mode,
        ),
    }
    if isinstance(existing, dict):
        for key in ("schema_version", "action_space", "mayor_semantics", "env"):
            value = _stringify_fingerprint_part(existing.get(key))
            if value:
                fingerprint[key] = value
    return fingerprint


def enrich_actor_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None

    enriched = dict(snapshot)
    enriched["fingerprint"] = build_artifact_fingerprint(
        enriched.get("fingerprint"),
        env_module=enriched.get("env_module"),
        num_players=enriched.get("num_players"),
        obs_dim=enriched.get("obs_dim"),
        action_dim=enriched.get("action_dim"),
        max_game_steps=enriched.get("max_game_steps"),
        potential_mode=enriched.get("potential_mode"),
    )
    return enriched


def build_replay_parity_snapshot(model_versions: dict[str, Any] | None) -> dict[str, Any]:
    expected = build_artifact_fingerprint()
    player_fingerprints: dict[str, dict[str, str]] = {}
    matching_players: list[str] = []
    mismatched_players: list[str] = []

    for player_key, snapshot in sorted((model_versions or {}).items()):
        enriched_snapshot = enrich_actor_snapshot(snapshot) or {"fingerprint": build_artifact_fingerprint()}
        fingerprint = enriched_snapshot["fingerprint"]
        player_fingerprints[player_key] = fingerprint
        if any(
            fingerprint[field] != expected[field]
            for field in ("action_space", "mayor_semantics", "env")
        ):
            mismatched_players.append(player_key)
        else:
            matching_players.append(player_key)

    return {
        "schema_version": REPLAY_PARITY_SCHEMA_V1,
        "expected": expected,
        "player_fingerprints": player_fingerprints,
        "matching_players": matching_players,
        "mismatched_players": mismatched_players,
    }


@dataclass(frozen=True)
class ModelArtifact:
    family: str
    policy_tag: str
    artifact_name: str
    checkpoint_filename: str
    checkpoint_path: str
    architecture: str | None = None
    obs_dim: int | None = None
    action_dim: int | None = None
    num_players: int | None = None
    hidden_dim: int | None = None
    num_res_blocks: int | None = None
    max_game_steps: int | None = None
    potential_mode: str | None = None
    shaping_gamma: float | None = None
    metadata_source: str = "sidecar"
    bootstrap_profile: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    fingerprint: dict[str, Any] = field(default_factory=dict)

    @property
    def cache_key(self) -> str:
        return ":".join(
            [
                self.family,
                self.policy_tag,
                self.checkpoint_filename,
                self.metadata_source,
                self.architecture or "unknown",
            ]
        )

    def to_snapshot(self, *, bot_type: str | None = None) -> dict[str, Any]:
        snapshot = {
            "actor_type": "bot",
            "bot_type": bot_type or self.family,
            "family": self.family,
            "policy_tag": self.policy_tag,
            "artifact_name": self.artifact_name,
            "checkpoint_filename": self.checkpoint_filename,
            "architecture": self.architecture,
            "metadata_source": self.metadata_source,
        }
        if self.bootstrap_profile:
            snapshot["bootstrap_profile"] = self.bootstrap_profile
        if self.obs_dim is not None:
            snapshot["obs_dim"] = self.obs_dim
        if self.action_dim is not None:
            snapshot["action_dim"] = self.action_dim
        if self.num_players is not None:
            snapshot["num_players"] = self.num_players
        if self.potential_mode is not None:
            snapshot["potential_mode"] = self.potential_mode
        if self.fingerprint:
            snapshot["fingerprint"] = dict(self.fingerprint)
        return snapshot


@functools.lru_cache(maxsize=1)
def get_ppo_pr_server_bootstrap_profile() -> dict[str, Any]:
    env = PuertoRicoEnv(num_players=3, max_game_steps=1200)
    agent = env.possible_agents[0]
    obs_space = env.observation_space(agent)["observation"]
    action_space = env.action_space(agent)
    signature = inspect.signature(ResidualAgent.__init__)

    return {
        "family": "ppo",
        "architecture": "ppo_residual",
        "training_script": "PuCo_RL/train/train_ppo_selfplay_server.py",
        "env_module": "PuCo_RL/env/pr_env.py",
        "num_players": 3,
        "obs_dim": int(get_flattened_obs_dim(obs_space)),
        "action_dim": int(action_space.n),
        "hidden_dim": int(signature.parameters["hidden_dim"].default),
        "num_res_blocks": int(signature.parameters["num_res_blocks"].default),
        "max_game_steps": 1200,
        "potential_mode": str(getattr(env, "potential_mode", DEFAULT_POTENTIAL_MODE)),
        "shaping_gamma": float(SHAPING_GAMMA),
        "reward_weights": {
            "ship": float(env.w_ship),
            "building": float(env.w_bldg),
            "doubloon": float(env.w_doub),
        },
        "training": {
            "self_play": True,
        },
        "bootstrap_profile": "ppo_pr_server_v1",
    }


def _sidecar_path(checkpoint_path: str) -> str:
    stem, _ = os.path.splitext(checkpoint_path)
    return f"{stem}.json"


def _build_checkpoint_path(filename: str, *, models_dir: str = MODELS_DIR) -> str:
    return os.path.join(models_dir, filename)


def _build_artifact_name(data: dict[str, Any], checkpoint_path: str) -> str:
    return str(
        data.get("artifact_name")
        or data.get("name")
        or os.path.splitext(os.path.basename(checkpoint_path))[0]
    )


def _load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _infer_checkpoint_obs_dim(checkpoint_path: str, *, architecture: str | None = None) -> int | None:
    try:
        import torch

        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        state_dict = checkpoint.get("model_state_dict", checkpoint) if isinstance(checkpoint, dict) else None
        if not isinstance(state_dict, dict):
            return None

        embed_weight = state_dict.get("embed.0.weight")
        if not hasattr(embed_weight, "shape") or len(embed_weight.shape) != 2:
            return None

        obs_dim = int(embed_weight.shape[1])
        if architecture in {"phase_ppo", "hppo"}:
            return max(0, obs_dim - 16)
        return obs_dim
    except Exception:
        return None


def _parse_legacy_metadata(
    data: dict[str, Any],
    *,
    checkpoint_path: str,
    family: str,
    policy_tag: str,
) -> ModelArtifact:
    return ModelArtifact(
        family=family,
        policy_tag=policy_tag,
        artifact_name=_build_artifact_name(data, checkpoint_path),
        checkpoint_filename=os.path.basename(checkpoint_path),
        checkpoint_path=checkpoint_path,
        architecture=data.get("architecture"),
        obs_dim=int(data["obs_dim"]) if data.get("obs_dim") is not None else None,
        action_dim=int(data["action_dim"]) if data.get("action_dim") is not None else None,
        hidden_dim=int(data["hidden_dim"]) if data.get("hidden_dim") is not None else None,
        metadata_source="legacy_flat_json",
        metadata=dict(data),
        fingerprint=build_artifact_fingerprint(
            data.get("fingerprint"),
            env_module=data.get("env_module"),
            num_players=int(data["num_players"]) if data.get("num_players") is not None else None,
            obs_dim=int(data["obs_dim"]) if data.get("obs_dim") is not None else None,
            action_dim=int(data["action_dim"]) if data.get("action_dim") is not None else None,
            max_game_steps=int(data["max_game_steps"]) if data.get("max_game_steps") is not None else None,
            potential_mode=data.get("potential_mode"),
        ),
    )


def _parse_v1_metadata(
    data: dict[str, Any],
    *,
    checkpoint_path: str,
    family: str,
    policy_tag: str,
) -> ModelArtifact:
    network = data.get("network") or {}
    environment = data.get("environment") or {}
    reward = data.get("reward") or {}
    return ModelArtifact(
        family=str(data.get("family") or family),
        policy_tag=policy_tag,
        artifact_name=_build_artifact_name(data, checkpoint_path),
        checkpoint_filename=os.path.basename(checkpoint_path),
        checkpoint_path=checkpoint_path,
        architecture=data.get("architecture"),
        obs_dim=int(data["obs_dim"]) if data.get("obs_dim") is not None else None,
        action_dim=int(data["action_dim"]) if data.get("action_dim") is not None else None,
        num_players=int(data["num_players"]) if data.get("num_players") is not None else None,
        hidden_dim=int(network["hidden_dim"]) if network.get("hidden_dim") is not None else None,
        num_res_blocks=int(network["num_res_blocks"]) if network.get("num_res_blocks") is not None else None,
        max_game_steps=int(environment["max_game_steps"]) if environment.get("max_game_steps") is not None else None,
        potential_mode=reward.get("potential_mode"),
        shaping_gamma=float(reward["shaping_gamma"]) if reward.get("shaping_gamma") is not None else None,
        metadata_source="sidecar",
        metadata=dict(data),
        fingerprint=build_artifact_fingerprint(
            data.get("fingerprint"),
            env_module=data.get("env_module"),
            num_players=int(data["num_players"]) if data.get("num_players") is not None else None,
            obs_dim=int(data["obs_dim"]) if data.get("obs_dim") is not None else None,
            action_dim=int(data["action_dim"]) if data.get("action_dim") is not None else None,
            max_game_steps=int(environment["max_game_steps"]) if environment.get("max_game_steps") is not None else None,
            potential_mode=reward.get("potential_mode"),
        ),
    )


def load_sidecar_artifact(
    checkpoint_path: str,
    *,
    family: str,
    policy_tag: str = "champion",
) -> ModelArtifact | None:
    metadata_path = _sidecar_path(checkpoint_path)
    if not os.path.exists(metadata_path):
        return None

    data = _load_json(metadata_path)
    if data.get("schema_version") == MODEL_METADATA_SCHEMA_V1:
        return _parse_v1_metadata(
            data,
            checkpoint_path=checkpoint_path,
            family=family,
            policy_tag=policy_tag,
        )
    return _parse_legacy_metadata(
        data,
        checkpoint_path=checkpoint_path,
        family=family,
        policy_tag=policy_tag,
    )


def derive_bootstrap_artifact(
    checkpoint_path: str,
    *,
    family: str,
    policy_tag: str = "champion",
) -> ModelArtifact | None:
    filename = os.path.basename(checkpoint_path)
    if family != "ppo" or not _PPO_PR_SERVER_PATTERN.match(filename):
        return None

    profile = get_ppo_pr_server_bootstrap_profile()
    inferred_obs_dim = _infer_checkpoint_obs_dim(
        checkpoint_path,
        architecture=profile["architecture"],
    )
    obs_dim = inferred_obs_dim if inferred_obs_dim is not None else profile["obs_dim"]
    metadata = {
        "schema_version": MODEL_METADATA_SCHEMA_V1,
        "artifact_name": os.path.splitext(filename)[0],
        "family": family,
        "architecture": profile["architecture"],
        "training_script": profile["training_script"],
        "env_module": profile["env_module"],
        "obs_dim": obs_dim,
        "action_dim": profile["action_dim"],
        "num_players": profile["num_players"],
        "network": {
            "hidden_dim": profile["hidden_dim"],
            "num_res_blocks": profile["num_res_blocks"],
        },
        "environment": {
            "max_game_steps": profile["max_game_steps"],
        },
        "reward": {
            "potential_mode": profile["potential_mode"],
            "shaping_gamma": profile["shaping_gamma"],
            "weights": dict(profile["reward_weights"]),
        },
        "training": dict(profile["training"]),
    }

    return ModelArtifact(
        family=family,
        policy_tag=policy_tag,
        artifact_name=os.path.splitext(filename)[0],
        checkpoint_filename=filename,
        checkpoint_path=checkpoint_path,
        architecture=profile["architecture"],
        obs_dim=obs_dim,
        action_dim=profile["action_dim"],
        num_players=profile["num_players"],
        hidden_dim=profile["hidden_dim"],
        num_res_blocks=profile["num_res_blocks"],
        max_game_steps=profile["max_game_steps"],
        potential_mode=profile["potential_mode"],
        shaping_gamma=profile["shaping_gamma"],
        metadata_source="bootstrap_derived",
        bootstrap_profile=profile["bootstrap_profile"],
        metadata=metadata,
        fingerprint=build_artifact_fingerprint(
            metadata.get("fingerprint"),
            env_module=profile["env_module"],
            num_players=profile["num_players"],
            obs_dim=obs_dim,
            action_dim=profile["action_dim"],
            max_game_steps=profile["max_game_steps"],
            potential_mode=profile["potential_mode"],
        ),
    )


def make_static_artifact(
    checkpoint_path: str,
    *,
    family: str,
    policy_tag: str = "champion",
    architecture: str | None = None,
    metadata_source: str = "static_config",
) -> ModelArtifact:
    return ModelArtifact(
        family=family,
        policy_tag=policy_tag,
        artifact_name=os.path.splitext(os.path.basename(checkpoint_path))[0],
        checkpoint_filename=os.path.basename(checkpoint_path),
        checkpoint_path=checkpoint_path,
        architecture=architecture,
        metadata_source=metadata_source,
        fingerprint=build_artifact_fingerprint(),
    )


def resolve_model_artifact_from_path(
    checkpoint_path: str,
    *,
    family: str,
    policy_tag: str = "champion",
) -> ModelArtifact:
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Model checkpoint not found: {checkpoint_path}")

    sidecar = load_sidecar_artifact(
        checkpoint_path,
        family=family,
        policy_tag=policy_tag,
    )
    if sidecar is not None:
        return sidecar

    bootstrap = derive_bootstrap_artifact(
        checkpoint_path,
        family=family,
        policy_tag=policy_tag,
    )
    if bootstrap is not None:
        return bootstrap

    raise ValueError(
        "Model metadata sidecar is required for this checkpoint. "
        f"Unsupported bootstrap checkpoint: {os.path.basename(checkpoint_path)}"
    )


def resolve_model_artifact_from_filename(
    filename: str,
    *,
    family: str,
    policy_tag: str = "champion",
    models_dir: str = MODELS_DIR,
) -> ModelArtifact:
    checkpoint_path = _build_checkpoint_path(filename, models_dir=models_dir)
    return resolve_model_artifact_from_path(
        checkpoint_path,
        family=family,
        policy_tag=policy_tag,
    )


def build_human_snapshot(player_id: str) -> dict[str, Any]:
    return enrich_actor_snapshot({
        "actor_type": "human",
        "player_id": str(player_id),
    })
