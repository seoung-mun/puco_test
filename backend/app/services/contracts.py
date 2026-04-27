from __future__ import annotations

from typing import Any


ACTION_REQUEST_SCHEMA_VERSION = "action-request.v1"

MODEL_OBSERVATION_SCHEMA_VERSION = "model-observation.v1"
MODEL_OBSERVATION_STATE_KIND = "model-observation"

RICH_GAME_STATE_SCHEMA_VERSION = "rich-game-state.v1"
RICH_GAME_STATE_STATE_KIND = "rich-game-state"

REPLAY_SUMMARY_SCHEMA_VERSION = "replay-summary.v1"
REPLAY_SUMMARY_STATE_KIND = "replay-summary"

TRANSITION_ENVELOPE_SCHEMA_VERSION = "transition-envelope.v1"


def with_state_contract(
    state: dict[str, Any],
    *,
    schema_version: str,
    state_kind: str,
    producer: str,
    trace_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    labeled = dict(state)
    labeled["schema_version"] = schema_version
    labeled["state_kind"] = state_kind
    labeled["producer"] = producer
    if trace_id is not None:
        labeled["trace_id"] = trace_id
    for key, value in extra.items():
        if value is not None:
            labeled[key] = value
    return labeled


def extract_state_kind(state: Any, default: str = "unknown") -> str:
    if isinstance(state, dict):
        value = state.get("state_kind")
        if isinstance(value, str) and value:
            return value
    return default


def extract_schema_version(state: Any, default: str = "unknown") -> str:
    if isinstance(state, dict):
        value = state.get("schema_version")
        if isinstance(value, str) and value:
            return value
    return default
