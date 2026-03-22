from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from fastapi import FastAPI

from app.api.v1 import room, game, ws, auth
from app.db.models import Base
from app.dependencies import engine

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Puerto Rico AI Battle Platform API",
    description="Backend for Puerto Rico AI Battle Platform with RL Logging",
    version="0.1.0",
)

# CORS Setting
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Puerto Rico AI Battle Platform API is running"}

@app.get("/health")
async def health():
    return {"status": "ok"}

# API Routes Inclusion
app.include_router(room.router, prefix="/api/v1/rooms", tags=["rooms"])
app.include_router(game.router, prefix="/api/v1/game", tags=["game"])
app.include_router(ws.router, prefix="/api/v1/ws", tags=["websocket"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
