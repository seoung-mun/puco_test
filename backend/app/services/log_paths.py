from __future__ import annotations

import os


DEFAULT_LOG_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../data/logs")
)


def resolve_log_dir() -> str:
    configured = os.getenv("APP_LOG_DIR", "").strip()
    if configured:
        return os.path.abspath(configured)
    return DEFAULT_LOG_DIR


def ensure_log_dir(*parts: str) -> str:
    path = os.path.join(resolve_log_dir(), *parts)
    os.makedirs(path, exist_ok=True)
    return path
