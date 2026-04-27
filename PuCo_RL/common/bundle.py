"""Bundle writer utility — 학습 산출물을 bundle directory로 패키징한다."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from typing import Any, Dict, Optional


def compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def write_bundle(
    *,
    output_dir: str,
    checkpoint_path: str,
    bundle_id: str,
    family: str = "ppo",
    policy_tag: str = "candidate",
    architecture: str = "ppo_residual",
    adapter_module: str = "common.semantic293_adapter:Semantic293TypeMayorAdapter",
    adapter_version: str = "1.0.0",
    obs_dim: int = 293,
    action_dim: int = 200,
    num_players: int = 3,
    network: Optional[Dict[str, Any]] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """bundle directory를 생성하고 manifest를 작성한다.

    output_dir에 checkpoint.pth와 manifest.json을 기록한다.
    """
    os.makedirs(output_dir, exist_ok=True)

    dest_checkpoint = os.path.join(output_dir, "checkpoint.pth")
    shutil.copy2(checkpoint_path, dest_checkpoint)

    manifest: Dict[str, Any] = {
        "schema_version": "model-bundle.v2",
        "bundle_id": bundle_id,
        "family": family,
        "policy_tag": policy_tag,
        "architecture": architecture,
        "checkpoint_file": "checkpoint.pth",
        "checkpoint_sha256": compute_sha256(dest_checkpoint),
        "adapter_module": adapter_module,
        "adapter_version": adapter_version,
        "canonical_state_version": "castone.canonical-state.v1",
        "canonical_action_version": "castone.canonical-action.v1",
        "obs_dim": obs_dim,
        "action_dim": action_dim,
        "num_players": num_players,
        "network": network or {"hidden_dim": 512, "num_res_blocks": 3},
        "compatibility": {
            "supported_canonical_state_versions": ["castone.canonical-state.v1"],
            "supported_canonical_action_versions": ["castone.canonical-action.v1"],
        },
    }
    if extra_metadata:
        manifest.update(extra_metadata)

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return output_dir
