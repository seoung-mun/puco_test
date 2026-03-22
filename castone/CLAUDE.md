# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Puerto Rico AI Battle Platform — a multiplayer web platform for the board game "Puerto Rico" where human players and AI agents compete. The primary goal is generating high-quality RL training datasets by logging every game action (state_before, action, action_mask, state_after) to PostgreSQL.

## Development Commands

### Full Stack (Docker Compose — recommended)

```bash
docker-compose up --build   # Start all services (DB, Redis, backend, frontend)
docker-compose down         # Stop all services
```

Services:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- PostgreSQL: localhost:5432 (user: `puco_user`, pass: `puco_password`, db: `puco_rl`)
- Redis: localhost:6379

### Frontend (Next.js 16.2)

```bash
cd frontend
npm run dev     # Dev server
npm run build   # Production build
npm run lint    # ESLint
```

> **Important:** This project uses **Next.js 16.2** with **React 19.2** — APIs and conventions may differ from your training data. Before writing Next.js code, consult `node_modules/next/dist/docs/` for the correct API. Always use the App Router.

### Backend (FastAPI)

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The `PYTHONPATH` must include both `/app` (backend) and `/PuCo_RL` (game engine). Docker handles this automatically; for local dev, set it manually.

### Game Engine Tests (PuCo_RL)

```bash
cd PuCo_RL
pytest tests/                          # All tests
pytest tests/test_engine.py           # Single test file
pytest tests/test_pr_env.py -v        # Verbose
```

The engine has its own `.venv` at `PuCo_RL/.venv/`.

## Architecture

### Three-Layer Structure

```
castone/
├── frontend/       # Next.js (App Router) — viewer only, no game logic
├── backend/        # FastAPI — authoritative game server
│   └── app/
│       ├── api/v1/ # auth.py, room.py, game.py, ws.py
│       ├── db/     # SQLAlchemy models (User, GameSession, GameLog)
│       ├── engine_wrapper/wrapper.py  # PuCo_RL integration
│       ├── services/ws_manager.py     # Redis Pub/Sub + WebSocket broadcast
│       └── dependencies.py           # DB session, engine injection
└── PuCo_RL/        # Pure Python game engine (Gymnasium/PettingZoo AEC)
    ├── env/engine.py     # PuertoRicoGame state machine
    ├── env/pr_env.py     # PuertoRicoEnv (Gymnasium wrapper)
    ├── agents/           # random, heuristic, MCTS, PPO agents
    └── configs/constants.py  # Phase, Role, Good, BuildingType enums
```

### Key Architectural Decisions

**Authoritative Server:** All game logic runs in the backend's `EngineWrapper`. The frontend is a pure viewer — it never validates or applies game actions locally.

**PettingZoo AEC Interface:** `PuertoRicoEnv` uses PettingZoo's Agent-Environment-Cycle API. After `env.step(action)`, state is retrieved via `env.observe(env.agent_selection)`, not from step's return value (which is None). The `EngineWrapper` in `backend/app/engine_wrapper/wrapper.py` abstracts this.

**RL Logging:** Every valid action triggers atomic logging to `game_logs` (JSONB). The log entry includes `state_before`, `action`, `action_mask`, `state_after`. Logging failure rolls back game state to prevent data corruption.

**Real-time Sync:** Redis Pub/Sub broadcasts game state changes to all WebSocket clients in a room via `ws_manager.py`. WebSocket endpoint: `ws://server/api/v1/ws/game/{game_id}`.

**Agent Runner:** When the next turn belongs to an AI agent, the backend automatically calls the agent's `act(state, mask)` and applies the result through the same action pipeline as human moves (including RL logging).

### Game Action Flow

1. Client → `POST /api/v1/game/action` with JWT
2. Backend validates JWT + verifies it's the player's turn
3. `EngineWrapper.step(action)` → validates + applies via PuCo_RL
4. Result logged atomically to `game_logs` (JSONB)
5. Redis Pub/Sub → WebSocket broadcast to all room clients

### Database Models (`backend/app/db/models.py`)

- `User`: Google OAuth profile, stats
- `GameSession`: Active game metadata, player slots, status
- `GameLog`: RL snapshots with JSONB fields; partitioned by `round` in production

### Environment Variables (`.env` — create manually)

```
DATABASE_URL=postgresql://puco_user:puco_password@db:5432/puco_rl
REDIS_URL=redis://redis:6379/0
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_WS_URL=ws://localhost:8000/api/v1/ws
```

Google OAuth credentials are also required (see `docs/PRD.md`).
