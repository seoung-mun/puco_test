from __future__ import annotations

from enum import IntEnum

from app.services.engine_gateway.bootstrap import ensure_puco_rl_path

ensure_puco_rl_path()

from configs.constants import (  # noqa: E402
    BUILDING_DATA,
    GOOD_PRICES,
    BuildingType,
    Good,
    MayorStrategy,
    Phase,
    Role,
    TileType,
)

try:  # noqa: E402
    from configs.constants import ControlMode  # type: ignore
except ImportError:  # pragma: no cover - upstream canonical constants no longer define this
    class ControlMode(IntEnum):
        HUMAN = 0
        BOT = 1

__all__ = [
    "BUILDING_DATA",
    "GOOD_PRICES",
    "BuildingType",
    "ControlMode",
    "Good",
    "MayorStrategy",
    "Phase",
    "Role",
    "TileType",
]
