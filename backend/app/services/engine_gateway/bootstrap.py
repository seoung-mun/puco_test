from __future__ import annotations

import os
import sys


PUCO_RL_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../PuCo_RL")
)


def ensure_puco_rl_path() -> str:
    if PUCO_RL_PATH not in sys.path:
        sys.path.append(PUCO_RL_PATH)
    return PUCO_RL_PATH


__all__ = ["PUCO_RL_PATH", "ensure_puco_rl_path"]
