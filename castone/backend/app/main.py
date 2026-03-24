import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
import uvicorn

from app.api.v1 import room, game, ws, auth
from app.api.legacy import router as legacy_router
from app.dependencies import SessionLocal
from app.core.redis import async_redis_client

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Puerto Rico AI Battle Platform API",
    description="Backend for Puerto Rico AI Battle Platform with RL Logging",
    version="0.1.0",
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
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.on_event("startup")
async def startup_checks():
    # Verify PostgreSQL connection
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection verified")
    except Exception as e:
        logger.error("PostgreSQL connection failed: %s", e)

    # Verify Redis connection
    try:
        await async_redis_client.ping()
        logger.info("Redis connection verified")
    except Exception as e:
        logger.error("Redis connection failed: %s", e)


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
        checks["postgresql"] = f"error: {e}"

    try:
        await async_redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        content={"status": "ok" if all_ok else "degraded", "checks": checks},
        status_code=200 if all_ok else 503,
    )


# Frontend-compatible API (no version prefix)
app.include_router(legacy_router, prefix="/api", tags=["legacy"])

# API Routes Inclusion
app.include_router(room.router, prefix="/api/v1/rooms", tags=["rooms"])
app.include_router(game.router, prefix="/api/v1/game", tags=["game"])
app.include_router(ws.router, prefix="/api/v1/ws", tags=["websocket"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
