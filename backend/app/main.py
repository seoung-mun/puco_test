import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
import uvicorn

from app.api.channel import room, game, ws, auth, lobby_ws, replay, playback
from app.api.legacy import router as legacy_router
from app.dependencies import SessionLocal
from app.core.redis import async_redis_client
from app.services.serving_health import validate_serving_health
from app.services.startup_cleanup import cleanup_stale_rooms

logger = logging.getLogger(__name__)

_DEBUG = os.getenv("DEBUG", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # === STARTUP ===
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection verified")
    except Exception as e:
        logger.error("PostgreSQL connection failed: %s", e)

    try:
        await async_redis_client.ping()
        logger.info("Redis connection verified")
    except Exception as e:
        logger.error("Redis connection failed: %s", e)

    try:
        with SessionLocal() as db:
            cleanup_stale_rooms(db)
    except Exception as e:
        logger.error("Startup room cleanup failed: %s", e)

    serving_health = validate_serving_health()
    if serving_health.ok:
        logger.info(
            "Serving health verified for %s artifact=%s source=%s",
            serving_health.bot_type,
            serving_health.artifact_name,
            serving_health.source,
        )
    else:
        logger.warning(
            "Serving health degraded for %s artifact=%s source=%s detail=%s",
            serving_health.bot_type,
            serving_health.artifact_name,
            serving_health.source,
            serving_health.detail,
        )

    yield

    # === SHUTDOWN ===
    logger.info("Shutdown initiated, cleaning up...")

    from app.services.ws_manager import manager as ws_mgr
    from app.services.game_service import GameService

    for task in list(ws_mgr._disconnect_timers.values()):
        try:
            if not task.done():
                task.cancel()
        except RuntimeError:
            logger.warning("Disconnect timer cleanup skipped because event loop is closed")
    ws_mgr._disconnect_timers.clear()

    for task in list(GameService._bot_tasks.values()):
        try:
            if not task.done():
                task.cancel()
        except RuntimeError:
            logger.warning("Bot task cleanup skipped because event loop is closed")
    GameService._bot_tasks.clear()

    for task in list(GameService._bot_stall_watchdogs.values()):
        try:
            if not task.done():
                task.cancel()
        except RuntimeError:
            logger.warning("Bot watchdog cleanup skipped because event loop is closed")
    GameService._bot_stall_watchdogs.clear()

    if hasattr(GameService, "_background_log_tasks"):
        for task in list(GameService._background_log_tasks):
            try:
                if not task.done():
                    task.cancel()
            except RuntimeError:
                logger.warning("Background log task cleanup skipped because event loop is closed")
        GameService._background_log_tasks.clear()

    try:
        await async_redis_client.aclose()
    except Exception as e:
        logger.warning("Error closing async Redis: %s", e)

    try:
        from app.core.redis import sync_redis_client
        sync_redis_client.close()
    except Exception as e:
        logger.warning("Error closing sync Redis: %s", e)

    await asyncio.sleep(0.5)
    logger.info("Shutdown cleanup complete")


# H-3: Swagger/OpenAPI 비프로덕션에서만 노출
app = FastAPI(
    title="Puerto Rico AI Battle Platform API",
    description="Backend for Puerto Rico AI Battle Platform with RL Logging",
    version="0.1.0",
    docs_url="/docs" if _DEBUG else None,
    redoc_url="/redoc" if _DEBUG else None,
    openapi_url="/openapi.json" if _DEBUG else None,
    lifespan=lifespan,
)

# CORS Setting
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
_allowed_origins: list[str] = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins
    else ["http://localhost:3000", "http://localhost:5173"]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# M-2: 보안 응답 헤더 미들웨어
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if not _DEBUG:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response



@app.get("/")
async def root():
    return {"message": "Puerto Rico AI Battle Platform API is running"}


@app.get("/health")
async def health():
    checks = {}

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["postgresql"] = "ok"
    except Exception as e:
        checks["postgresql"] = "error"
        logger.error("PostgreSQL health check failed: %s", e)

    try:
        await async_redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = "error"
        logger.error("Redis health check failed: %s", e)

    serving_health = validate_serving_health()
    checks["serving"] = {
        "status": "ok" if serving_health.ok else "degraded",
        "artifact_name": serving_health.artifact_name,
        "metadata_source": serving_health.source,
    }
    if serving_health.detail:
        checks["serving"]["detail"] = serving_health.detail

    all_ok = (
        checks["postgresql"] == "ok"
        and checks["redis"] == "ok"
        and serving_health.ok
    )
    # Always return 200 for Render liveness probe;
    # body contains degraded status for monitoring.
    return JSONResponse(
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
        status_code=200,
    )


# Frontend-compatible API (no version prefix)
app.include_router(legacy_router, prefix="/api", tags=["legacy"])

# API Routes
app.include_router(room.router, prefix="/api/puco/rooms", tags=["rooms"])
app.include_router(game.router, prefix="/api/puco/game", tags=["game"])
app.include_router(lobby_ws.router, prefix="/api/puco/ws/lobby", tags=["lobby-ws"])
app.include_router(ws.router, prefix="/api/puco/ws", tags=["websocket"])
app.include_router(auth.router, prefix="/api/puco/auth", tags=["auth"])
app.include_router(replay.router, prefix="/api/puco/replays", tags=["replays"])
app.include_router(playback.router, prefix="/api/puco/games", tags=["playback"])

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
