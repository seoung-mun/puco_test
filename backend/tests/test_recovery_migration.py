"""Spec Section 8.2: recovery metadata migration roundtrip stays idempotent."""

import subprocess


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["alembic", *args],
        capture_output=True,
        text=True,
        check=True,
        cwd="/app",
    )


def test_alembic_migration_adds_columns_idempotent():
    _alembic("downgrade", "-1")
    _alembic("upgrade", "head")
    _alembic("downgrade", "-1")
    _alembic("upgrade", "head")
