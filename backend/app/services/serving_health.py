from __future__ import annotations

import os
from dataclasses import dataclass

from app.services.agent_registry import (
    AGENT_REGISTRY,
    describe_model_artifact_resolution,
    get_adapter_runtime,
    require_valid_bot_type,
)


@dataclass(frozen=True)
class ServingHealth:
    ok: bool
    bot_type: str
    source: str | None
    artifact_name: str | None
    detail: str | None = None


def _join_details(*parts: str | None) -> str | None:
    values = [part for part in parts if part]
    if not values:
        return None
    return " ".join(values)


def validate_serving_health(bot_type: str = "ppo") -> ServingHealth:
    normalized = require_valid_bot_type(bot_type)
    cfg = AGENT_REGISTRY[normalized]
    resolution = describe_model_artifact_resolution(normalized)
    artifact = resolution.artifact
    ok = (
        artifact is not None
        and resolution.failure_detail is None
        and resolution.warning is None
        and not resolution.used_legacy_override
    )
    detail = resolution.failure_detail

    if normalized == "ppo":
        expected_bundle = cfg.get("bundle_dir")
        model_type = os.getenv("MODEL_TYPE")
        if (model_type or "").strip().lower() != "ppo":
            ok = False
            detail = _join_details(
                detail,
                f"MODEL_TYPE must be 'ppo' for PPO serving, got {model_type!r}.",
            )

        bundle_override = os.getenv(cfg.get("bundle_dir_env_key", ""))
        if bundle_override is None or bundle_override.strip() != expected_bundle:
            ok = False
            detail = _join_details(
                detail,
                f"PPO_BUNDLE_DIR must be {expected_bundle!r} in production, got {bundle_override!r}.",
            )

        model_override = os.getenv(cfg.get("model_env_key", ""))
        if model_override:
            ok = False
            detail = _join_details(
                detail,
                f"{cfg['model_env_key']} should be empty in production.",
            )

    if (
        cfg.get("use_adapter")
        and artifact is not None
        and artifact.metadata_source == "bundle_v2"
    ):
        try:
            runtime = get_adapter_runtime(normalized)
        except Exception as exc:
            ok = False
            detail = _join_details(detail, f"Adapter runtime failed: {exc}")
        else:
            if runtime is None:
                ok = False
                detail = _join_details(
                    detail,
                    "Adapter runtime unavailable for bundle-based PPO serving.",
                )

    if artifact is None and detail is None:
        detail = "No serving artifact could be resolved."

    detail = _join_details(detail, resolution.warning)
    return ServingHealth(
        ok=ok,
        bot_type=normalized,
        source=artifact.metadata_source if artifact is not None else None,
        artifact_name=artifact.artifact_name if artifact is not None else None,
        detail=detail,
    )
