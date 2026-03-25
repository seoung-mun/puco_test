"""
Legacy API 패키지 — main.py가 기존과 동일하게 import할 수 있도록 router를 노출한다.

    from app.api.legacy import router as legacy_router  ← 변경 없음
"""
from fastapi import APIRouter

from .game import router as _game_router
from .lobby import router as _lobby_router
from .actions import router as _actions_router

router = APIRouter()
router.include_router(_game_router)
router.include_router(_lobby_router)
router.include_router(_actions_router)
