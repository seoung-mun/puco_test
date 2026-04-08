from __future__ import annotations

import re
from pathlib import Path


FORBIDDEN_IMPORTS = re.compile(
    r"^\s*(?:from\s+(?:env|configs|agents)\.|import\s+(?:env|configs|agents)\.)",
    re.MULTILINE,
)

ALLOWED_PATH_FRAGMENTS = (
    "backend/app/services/engine_gateway/",
    "backend/app/engine_wrapper/wrapper.py",
    "backend/app/api/legacy/",
)


def test_backend_app_imports_puco_modules_only_through_gateway_or_legacy_boundaries():
    root = Path(__file__).resolve().parents[2]
    backend_app = root / "backend" / "app"
    offenders: list[str] = []

    for path in sorted(backend_app.rglob("*.py")):
        posix_path = path.as_posix()
        if any(fragment in posix_path for fragment in ALLOWED_PATH_FRAGMENTS):
            continue

        content = path.read_text(encoding="utf-8")
        if FORBIDDEN_IMPORTS.search(content):
            offenders.append(posix_path.removeprefix(f"{root.as_posix()}/"))

    assert offenders == [], (
        "Direct PuCo_RL imports must stay inside engine_gateway, engine_wrapper, or legacy API boundaries. "
        f"Found: {offenders}"
    )
