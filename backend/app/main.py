import logging
import os

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
import uvicorn

from app.api.channel import room, game, ws, auth, lobby_ws
from app.api.legacy import router as legacy_router
from app.dependencies import SessionLocal
from app.core.redis import async_redis_client
from app.services.startup_cleanup import cleanup_stale_rooms

logger = logging.getLogger(__name__)

_DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# H-3: Swagger/OpenAPI 비프로덕션에서만 노출
app = FastAPI(
    title="Puerto Rico AI Battle Platform API",
    description="Backend for Puerto Rico AI Battle Platform with RL Logging",
    version="0.1.0",
    docs_url="/docs" if _DEBUG else None,
    redoc_url="/redoc" if _DEBUG else None,
    openapi_url="/openapi.json" if _DEBUG else None,
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


@app.on_event("startup")
async def startup_checks():
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

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
        status_code=200 if all_ok else 503,
    )


# Frontend-compatible API (no version prefix)
app.include_router(legacy_router, prefix="/api", tags=["legacy"])

# API Routes
app.include_router(room.router, prefix="/api/puco/rooms", tags=["rooms"])
app.include_router(game.router, prefix="/api/puco/game", tags=["game"])
app.include_router(lobby_ws.router, prefix="/api/puco/ws/lobby", tags=["lobby-ws"])
app.include_router(ws.router, prefix="/api/puco/ws", tags=["websocket"])
app.include_router(auth.router, prefix="/api/puco/auth", tags=["auth"])

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
