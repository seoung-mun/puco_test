from __future__ import annotations

import os
import secrets
from collections.abc import Mapping


_GENERATED_SECRET_KEYS = (
    "SECRET_KEY",
    "INTERNAL_API_KEY",
    "VITE_INTERNAL_API_KEY",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
)
_REQUIRED_RUNTIME_SECRETS = (
    "SECRET_KEY",
    "INTERNAL_API_KEY",
)
_PLACEHOLDER_MARKERS = (
    "change-me",
    "your-google-client-id",
    "placeholder",
)


def _is_debug_enabled(env: Mapping[str, str | None]) -> bool:
    return str(env.get("DEBUG", "false")).strip().lower() == "true"


def is_placeholder_secret(value: str | None) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return True
    return any(marker in normalized for marker in _PLACEHOLDER_MARKERS)


def _generate_secret_for_key(key: str) -> str:
    if key in {"SECRET_KEY", "INTERNAL_API_KEY", "VITE_INTERNAL_API_KEY"}:
        return secrets.token_hex(32)
    return secrets.token_urlsafe(24)


def render_env_with_generated_secrets(content: str) -> tuple[str, list[str]]:
    replacements: dict[str, str] = {}
    lines = content.splitlines()

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        if key not in _GENERATED_SECRET_KEYS:
            continue
        if key == "VITE_INTERNAL_API_KEY":
            continue
        if is_placeholder_secret(value):
            replacements[key] = _generate_secret_for_key(key)

    internal_api_value = replacements.get("INTERNAL_API_KEY")
    if internal_api_value is not None:
        replacements["VITE_INTERNAL_API_KEY"] = internal_api_value

    updated_lines: list[str] = []
    touched: list[str] = []
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            updated_lines.append(raw_line)
            continue

        key, value = raw_line.split("=", 1)
        normalized_key = key.strip()
        replacement = replacements.get(normalized_key)
        if replacement is None:
            updated_lines.append(raw_line)
            continue

        updated_lines.append(f"{key}={replacement}")
        if normalized_key not in touched:
            touched.append(normalized_key)

    return "\n".join(updated_lines), touched


def validate_runtime_secrets(env: Mapping[str, str | None] | None = None) -> None:
    active_env = env or os.environ
    if _is_debug_enabled(active_env):
        return

    invalid_keys = [
        key for key in _REQUIRED_RUNTIME_SECRETS
        if is_placeholder_secret(active_env.get(key))
    ]
    if invalid_keys:
        joined = ", ".join(invalid_keys)
        raise RuntimeError(
            "Production secret placeholder detected for "
            f"{joined}. Replace placeholder values before starting the server."
        )
