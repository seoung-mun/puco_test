import pytest

from app.core.env_secrets import (
    render_env_with_generated_secrets,
    validate_runtime_secrets,
)


def _to_mapping(content: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        pairs[key] = value
    return pairs


def test_render_env_with_generated_secrets_replaces_placeholders_and_syncs_frontend_key():
    content = """
SECRET_KEY=change-me-generate-a-random-64-char-hex-string
INTERNAL_API_KEY=change-me-generate-a-random-64-char-hex-string
VITE_INTERNAL_API_KEY=change-me-same-value-as-INTERNAL_API_KEY
POSTGRES_PASSWORD=change-me-strong-db-password
REDIS_PASSWORD=change-me-strong-redis-password
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
""".strip()

    updated, replaced = render_env_with_generated_secrets(content)
    mapping = _to_mapping(updated)

    assert mapping["SECRET_KEY"] != "change-me-generate-a-random-64-char-hex-string"
    assert mapping["INTERNAL_API_KEY"] == mapping["VITE_INTERNAL_API_KEY"]
    assert mapping["POSTGRES_PASSWORD"] != "change-me-strong-db-password"
    assert mapping["REDIS_PASSWORD"] != "change-me-strong-redis-password"
    assert mapping["GOOGLE_CLIENT_ID"] == "your-google-client-id.apps.googleusercontent.com"
    assert replaced == [
        "SECRET_KEY",
        "INTERNAL_API_KEY",
        "VITE_INTERNAL_API_KEY",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
    ]


def test_render_env_with_generated_secrets_preserves_existing_values():
    content = """
SECRET_KEY=already-secure
INTERNAL_API_KEY=existing-internal
VITE_INTERNAL_API_KEY=existing-internal
POSTGRES_PASSWORD=custom-db-password
REDIS_PASSWORD=custom-redis-password
""".strip()

    updated, replaced = render_env_with_generated_secrets(content)
    mapping = _to_mapping(updated)

    assert mapping["SECRET_KEY"] == "already-secure"
    assert mapping["INTERNAL_API_KEY"] == "existing-internal"
    assert mapping["VITE_INTERNAL_API_KEY"] == "existing-internal"
    assert mapping["POSTGRES_PASSWORD"] == "custom-db-password"
    assert mapping["REDIS_PASSWORD"] == "custom-redis-password"
    assert replaced == []


def test_validate_runtime_secrets_rejects_placeholder_values():
    with pytest.raises(RuntimeError, match="placeholder"):
        validate_runtime_secrets(
            {
                "DEBUG": "false",
                "SECRET_KEY": "change-me-generate-a-random-64-char-hex-string",
                "INTERNAL_API_KEY": "change-me-generate-a-random-64-char-hex-string",
            }
        )


def test_validate_runtime_secrets_allows_debug_mode():
    validate_runtime_secrets(
        {
            "DEBUG": "true",
            "SECRET_KEY": "change-me-generate-a-random-64-char-hex-string",
            "INTERNAL_API_KEY": "change-me-generate-a-random-64-char-hex-string",
        }
    )
