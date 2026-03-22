# Puerto Rico AI Battle Platform

**[한국어](#한국어) | [English](#english)**

---

## 한국어

Puerto Rico 보드게임을 웹 환경에서 멀티플레이어 + AI 에이전트가 함께 플레이하는 플랫폼입니다.
모든 게임 액션은 서버에서 처리되며, 강화학습(RL) 재학습용 고품질 데이터셋 자동 생성이 핵심 목표입니다.

### 목차

- [프로젝트 구조](#프로젝트-구조)
- [기술 스택](#기술-스택)
- [빠른 시작 (Docker)](#빠른-시작-docker)
- [로컬 개발 환경 설정](#로컬-개발-환경-설정)
- [게임플레이 로그 저장 방식](#게임플레이-로그-저장-방식)
- [저장 데이터 확인 방법](#저장-데이터-확인-방법)
- [아키텍처 상세](#아키텍처-상세)
- [환경 변수](#환경-변수)
- [트러블슈팅](#트러블슈팅)

---

### 프로젝트 구조

```
castone/
├── frontend/               # Vite + React (TypeScript) — 뷰어 전용
│   ├── src/
│   │   ├── App.tsx         # 메인 앱 (로비, 게임 화면)
│   │   ├── components/     # LobbyScreen, HomeScreen 등
│   │   └── types/          # TypeScript 타입 정의
│   └── vite.config.ts
├── backend/                # FastAPI (Python 3.12+) — 모든 게임 로직
│   ├── app/
│   │   ├── api/
│   │   │   ├── legacy.py          # 프론트엔드 호환 API (/api/*)
│   │   │   └── v1/                # REST API (auth, room, game, ws)
│   │   ├── db/
│   │   │   └── models.py          # SQLAlchemy ORM 모델
│   │   ├── services/
│   │   │   ├── game_service.py    # 게임 라이프사이클 + 액션 처리
│   │   │   ├── ml_logger.py       # 비동기 JSONL 파일 로깅
│   │   │   ├── bot_service.py     # PPO/랜덤 봇 추론
│   │   │   ├── state_serializer.py # 게임 상태 → JSON 직렬화
│   │   │   ├── action_translator.py # 시맨틱 액션 → 정수 인덱스
│   │   │   ├── session_manager.py  # 인메모리 로비/세션 관리
│   │   │   └── ws_manager.py      # WebSocket + Redis Pub/Sub
│   │   ├── engine_wrapper/
│   │   │   └── wrapper.py         # FastAPI ↔ PuCo_RL 브릿지
│   │   └── main.py
│   └── requirements.txt
├── PuCo_RL/                # 순수 Python 게임 엔진 (Gymnasium/PettingZoo)
│   ├── env/
│   │   ├── engine.py       # PuertoRicoGame 상태 머신
│   │   ├── pr_env.py       # AECEnv 래퍼 (PettingZoo)
│   │   └── components.py   # CargoShip, Plantation 등
│   ├── agents/
│   │   ├── ppo_agent.py    # PyTorch PPO 모델
│   │   └── random_agent.py
│   ├── models/             # 훈련된 모델 가중치 (.pth)
│   ├── configs/
│   │   └── constants.py    # Phase, Role, Good, BuildingType Enum
│   └── tests/
├── data/
│   └── logs/               # JSONL 형식 RL 트랜지션 로그
├── docs/                   # PRD, 아키텍처, API 설계 문서
├── docker-compose.yml
└── .env                    # 환경 변수 (직접 생성 필요)
```

---

### 기술 스택

| 레이어 | 기술 |
|--------|------|
| **Frontend** | Vite 5, React 18, TypeScript, react-i18next |
| **Backend** | FastAPI 0.111, Python 3.12, Uvicorn |
| **게임 엔진** | 순수 Python, Gymnasium 0.29, PettingZoo 1.24 |
| **데이터베이스** | PostgreSQL 16 (JSONB 로그 저장) |
| **캐시/Pub-Sub** | Redis 7 (WebSocket 실시간 동기화) |
| **AI 에이전트** | PyTorch 2.3 (PPO), 랜덤 봇 |
| **ORM** | SQLAlchemy 2.0, Alembic |
| **컨테이너** | Docker, Docker Compose |

---

### 빠른 시작 (Docker)

> Docker와 Docker Compose가 설치되어 있어야 합니다.

```bash
# 1. 저장소 클론
git clone <repo-url>
cd castone

# 2. 환경 변수 파일 생성
cp .env.example .env      # .env.example이 없으면 아래 내용으로 직접 생성

# 3. 컨테이너 빌드 및 실행
docker-compose up --build
```

**접속 정보:**

| 서비스 | URL |
|--------|-----|
| 프론트엔드 | http://localhost:3000 |
| 백엔드 API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

---

### 로컬 개발 환경 설정

Docker 없이 직접 실행하는 경우입니다.

#### 사전 요구사항

- Python 3.12+
- Node.js 18+
- PostgreSQL 16
- Redis 7

#### 1. PuCo_RL 가상환경 설정

```bash
cd PuCo_RL
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. 백엔드 설정

```bash
cd backend
pip install -r requirements.txt

# 환경 변수 설정
export DATABASE_URL="postgresql://puco_user:puco_password@localhost:5432/puco_rl"
export REDIS_URL="redis://localhost:6379/0"
export PYTHONPATH="/path/to/castone/PuCo_RL:/path/to/castone/backend"

# DB 마이그레이션
alembic upgrade head

# 개발 서버 실행
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 3. 프론트엔드 설정

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
```

> **참고:** 프론트엔드는 Vite 프록시를 통해 `/api/*` 요청을 `http://localhost:8000`으로 전달합니다.

#### 4. 게임 엔진 테스트 실행

```bash
cd PuCo_RL
source .venv/bin/activate
pytest tests/ -v

# 백엔드 단위 테스트 (SQLite, PostgreSQL 불필요)
cd backend
DATABASE_URL="sqlite:///./test.db" \
PYTHONPATH="../PuCo_RL:." \
python3 -m pytest tests/test_legacy_features.py --noconftest -v
```

---

### 게임플레이 로그 저장 방식

게임의 모든 액션은 **두 가지 경로**로 동시에 기록됩니다.

#### 경로 1: PostgreSQL `game_logs` 테이블

각 액션마다 아래 레코드가 JSONB 컬럼으로 삽입됩니다.

```
game_logs
├── id          (integer, PK)
├── game_id     (UUID, FK → games.id)
├── round       (integer)  — 라운드 번호
├── step        (integer)  — 스텝 번호
├── actor_id    (string)   — 플레이어 ID
├── action_data (JSON)     — {"action": 5}
├── available_options (JSON) — 액션 마스크 (불리언 배열, 200개)
├── state_before (JSON)    — 액션 전 전체 게임 상태
├── state_after  (JSON)    — 액션 후 전체 게임 상태
└── timestamp   (datetime)
```

**코드 위치:** `backend/app/services/game_service.py`

```python
game_log = GameLog(
    game_id=game_id,
    round=result["info"].get("round", 0),
    step=result["info"].get("step", 0),
    actor_id=actor_id,
    action_data={"action": action},
    available_options=result["action_mask"],
    state_before=result["state_before"],
    state_after=result["state_after"]
)
db.add(game_log)
db.commit()
```

#### 경로 2: JSONL 파일 로그 (`/data/logs/`)

강화학습 훈련에 바로 사용할 수 있는 형식으로 파일에 저장됩니다.

**파일 위치:** `/data/logs/transitions_YYYY-MM-DD.jsonl`

**파일 형식 (한 줄 = 한 트랜지션):**

```json
{
  "timestamp": "2025-01-15T14:23:01.123Z",
  "game_id": "uuid-...",
  "actor_id": "player_0",
  "state_before": { "players": {...}, "roles": {...}, "ships": [...] },
  "action": 3,
  "reward": 0.0,
  "done": false,
  "state_after": { "players": {...}, "roles": {...}, "ships": [...] },
  "info": { "round": 2, "step": 15, "phase": "select_role" }
}
```

**코드 위치:** `backend/app/services/ml_logger.py`

#### 경로 3: Redis (실시간 동기화, 영구 저장 아님)

```
채널: game:{game_id}:events
메시지 타입: STATE_UPDATE
내용: 직렬화된 현재 게임 상태 (JSON)
용도: WebSocket 클라이언트 실시간 브로드캐스트
```

Redis는 영구 저장소가 아닙니다. 재시작 시 데이터가 사라집니다.

---

### 저장 데이터 확인 방법

#### PostgreSQL 확인

```bash
# Docker 환경에서 psql 접속
docker exec -it puco_db psql -U puco_user -d puco_rl

# 직접 접속
psql postgresql://puco_user:puco_password@localhost:5432/puco_rl
```

**유용한 쿼리:**

```sql
-- 전체 게임 목록
SELECT id, title, status, num_players, created_at
FROM games
ORDER BY created_at DESC
LIMIT 10;

-- 특정 게임의 모든 로그
SELECT id, round, step, actor_id, action_data, timestamp
FROM game_logs
WHERE game_id = '<game-uuid>'
ORDER BY step ASC;

-- 게임당 총 액션 수
SELECT game_id, COUNT(*) AS total_steps
FROM game_logs
GROUP BY game_id
ORDER BY total_steps DESC;

-- 특정 스텝의 state_before 확인 (JSONB 필드 조회)
SELECT
  step,
  actor_id,
  state_before->'players'->'player_0'->>'victory_points' AS p0_vp,
  action_data
FROM game_logs
WHERE game_id = '<game-uuid>'
ORDER BY step ASC;

-- 액션 분포 (어떤 액션이 가장 많이 쓰였는지)
SELECT
  (action_data->>'action')::int AS action_idx,
  COUNT(*) AS count
FROM game_logs
GROUP BY action_idx
ORDER BY count DESC;
```

#### Redis 확인

```bash
# Docker 환경에서 redis-cli 접속
docker exec -it puco_redis redis-cli

# 직접 접속
redis-cli -h localhost -p 6379
```

**유용한 명령어:**

```bash
# 현재 활성 채널 목록
PUBSUB CHANNELS game:*

# 특정 채널 구독 (실시간 모니터링)
SUBSCRIBE game:<game-id>:events

# 모든 키 목록
KEYS *

# 메모리 사용량 확인
INFO memory

# 초당 명령어 수 모니터링
MONITOR
```

#### JSONL 파일 확인

```bash
# Docker 환경에서 파일 확인
docker exec -it puco_backend ls /data/logs/
docker exec -it puco_backend cat /data/logs/transitions_2025-01-15.jsonl | head -5

# jq로 파싱 (가독성 있게 출력)
docker exec -it puco_backend sh -c \
  "cat /data/logs/transitions_2025-01-15.jsonl | head -1 | python3 -m json.tool"

# 로컬 환경
ls ./data/logs/
cat ./data/logs/transitions_$(date +%Y-%m-%d).jsonl | python3 -m json.tool | head -50
```

**Python으로 JSONL 파일 읽기:**

```python
import json

with open("data/logs/transitions_2025-01-15.jsonl") as f:
    records = [json.loads(line) for line in f if line.strip()]

print(f"총 트랜지션 수: {len(records)}")
print(f"게임 목록: {set(r['game_id'] for r in records)}")
print(f"평균 리워드: {sum(r['reward'] for r in records) / len(records):.3f}")
```

#### GUI 툴 (권장)

| 툴 | 대상 | 설명 |
|----|------|------|
| [pgAdmin 4](https://www.pgadmin.org/) | PostgreSQL | 웹 기반 DB 관리 UI |
| [TablePlus](https://tableplus.com/) | PostgreSQL, Redis | macOS/Windows GUI 클라이언트 |
| [DBeaver](https://dbeaver.io/) | PostgreSQL | 무료 범용 DB 클라이언트 |
| [RedisInsight](https://redis.io/insight/) | Redis | Redis 공식 GUI 툴 |
| [Swagger UI](http://localhost:8000/docs) | REST API | 내장 API 탐색기 |

---

### 아키텍처 상세

#### 게임 액션 흐름

```
클라이언트 (React)
    │  POST /api/action/<type>  {player, ...}
    ▼
FastAPI (legacy.py)
    │  action_translator.py → 정수 인덱스 변환
    │  session.game.step(action)
    ▼
EngineWrapper (wrapper.py)
    │  PuCo_RL PuertoRicoEnv.step(action)
    ▼
PuertoRicoGame (engine.py)
    │  상태 업데이트
    ▼
serialize_game_state() → JSON 응답
    │
    ├─→ PostgreSQL: game_logs INSERT (JSONB)
    ├─→ /data/logs/: JSONL 파일 append (비동기)
    └─→ Redis Pub/Sub → WebSocket 브로드캐스트
```

#### 봇 실행 흐름

```
액션 처리 완료
    │
    └─→ _run_pending_bots() 호출
          │  다음 플레이어가 봇인지 확인
          │  봇이면: get_action_mask() → 유효한 액션 중 선택
          │  (random 봇: random.choice, ppo 봇: 모델 추론)
          └─→ 동일한 game.step(action) 파이프라인으로 실행
```

#### 주요 액션 인덱스 매핑

```
0 – 7   : 역할 선택 (Role.SETTLER=0 … Role.PROSPECTOR=7)
8 – 13  : 정착 — 공개 농장 선택 (인덱스 0–5)
14      : 정착 — 채석장 선택
15      : 패스
16 – 38 : 건설 (23종 건물)
39 – 43 : 상인 — 상품 판매 (5종)
44 – 58 : 선장 — 선박 적재 (선박 인덱스 × 5 + 상품)
59 – 63 : 선장 — 부두(Wharf) 적재
69 – 92 : 시장 — 식민지 배치/회수 토글
93 – 97 : 장인 — 특권 상품 선택
105     : 아시엔다 추가 농장 뽑기
```

#### 데이터베이스 스키마

```
users
├── id (UUID, PK)
├── google_id (string, unique)
├── nickname (string)
├── total_games (int, default 0)
└── win_rate (int, default 0)

games
├── id (UUID, PK)
├── title (string)
├── status (string: WAITING | PROGRESS | FINISHED)
├── num_players (int)
├── players (JSON)          -- 플레이어 ID 배열
├── model_versions (JSON)   -- {"0": "PPO_v2"} 형식
├── winner_id (string, nullable)
└── created_at (datetime)

game_logs
├── id (int, PK, auto-increment)
├── game_id (UUID, FK → games.id, indexed)
├── round (int, indexed)
├── step (int)
├── actor_id (string)
├── action_data (JSON)
├── available_options (JSON) -- 액션 마스크 (200차원 불리언)
├── state_before (JSON)
├── state_after (JSON)
└── timestamp (datetime, indexed)
```

---

### 환경 변수

`.env` 파일을 프로젝트 루트에 생성하세요.

```bash
# 데이터베이스
DATABASE_URL=postgresql://puco_user:puco_password@db:5432/puco_rl

# Redis
REDIS_URL=redis://redis:6379/0

# 프론트엔드 → 백엔드 연결
VITE_API_TARGET=http://backend:8000

# (선택) Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

**로컬 개발 시:**

```bash
DATABASE_URL=postgresql://puco_user:puco_password@localhost:5432/puco_rl
REDIS_URL=redis://localhost:6379/0
VITE_API_TARGET=http://localhost:8000
```

---

### 트러블슈팅

#### PostgreSQL 연결 실패

```
Error: could not connect to server: Connection refused
```

```bash
# Docker 컨테이너 상태 확인
docker-compose ps

# PostgreSQL 헬스체크
docker exec puco_db pg_isready -U puco_user -d puco_rl

# 로그 확인
docker-compose logs db
```

#### Redis 연결 실패

```bash
docker exec puco_redis redis-cli ping   # PONG 응답 확인
docker-compose logs redis
```

#### 백엔드 PYTHONPATH 오류

```
ModuleNotFoundError: No module named 'configs'
```

`PYTHONPATH`에 `PuCo_RL` 경로가 포함되어야 합니다.

```bash
export PYTHONPATH="/path/to/castone/PuCo_RL:/path/to/castone/backend"
```

Docker 환경에서는 `docker-compose.yml`의 `PYTHONPATH` 환경 변수가 자동으로 설정됩니다.

#### 프론트엔드 API 연결 안 됨

`frontend/vite.config.ts`의 프록시 설정을 확인하세요.

```typescript
proxy: {
  '/api': { target: 'http://localhost:8000' }
}
```

#### 게임 로그 파일이 생성되지 않음

```bash
# Docker에서 /data/logs 마운트 확인
docker exec puco_backend ls /data/logs/

# 쓰기 권한 확인
docker exec puco_backend touch /data/logs/test.txt
```

---

---

## English

Puerto Rico is a web-based multiplayer platform where human players and AI agents compete in the Puerto Rico board game. All game logic runs authoritatively on the server. The primary purpose is generating high-quality reinforcement learning training datasets by logging every game action.

### Table of Contents

- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Development Setup](#local-development-setup)
- [How Gameplay Logs Are Stored](#how-gameplay-logs-are-stored)
- [Inspecting Stored Data](#inspecting-stored-data)
- [Architecture Details](#architecture-details)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

---

### Project Structure

```
castone/
├── frontend/               # Vite + React (TypeScript) — viewer only
│   ├── src/
│   │   ├── App.tsx         # Main app (lobby, game screen)
│   │   ├── components/     # LobbyScreen, HomeScreen, etc.
│   │   └── types/          # TypeScript type definitions
│   └── vite.config.ts
├── backend/                # FastAPI (Python 3.12+) — all game logic
│   ├── app/
│   │   ├── api/
│   │   │   ├── legacy.py          # Frontend-compatible API (/api/*)
│   │   │   └── v1/                # REST API (auth, room, game, ws)
│   │   ├── db/
│   │   │   └── models.py          # SQLAlchemy ORM models
│   │   ├── services/
│   │   │   ├── game_service.py    # Game lifecycle + action processing
│   │   │   ├── ml_logger.py       # Async JSONL file logging
│   │   │   ├── bot_service.py     # PPO/random bot inference
│   │   │   ├── state_serializer.py # Game state → JSON serialization
│   │   │   ├── action_translator.py # Semantic action → integer index
│   │   │   ├── session_manager.py  # In-memory lobby/session tracking
│   │   │   └── ws_manager.py      # WebSocket + Redis Pub/Sub
│   │   ├── engine_wrapper/
│   │   │   └── wrapper.py         # FastAPI ↔ PuCo_RL bridge
│   │   └── main.py
│   └── requirements.txt
├── PuCo_RL/                # Pure Python game engine (Gymnasium/PettingZoo)
│   ├── env/
│   │   ├── engine.py       # PuertoRicoGame state machine
│   │   ├── pr_env.py       # AECEnv wrapper (PettingZoo AEC interface)
│   │   └── components.py   # CargoShip, Plantation, etc.
│   ├── agents/
│   │   ├── ppo_agent.py    # PyTorch PPO model
│   │   └── random_agent.py
│   ├── models/             # Trained model weights (.pth files)
│   ├── configs/
│   │   └── constants.py    # Phase, Role, Good, BuildingType enums
│   └── tests/
├── data/
│   └── logs/               # JSONL format RL transition logs
├── docs/                   # PRD, architecture, API design docs
├── docker-compose.yml
└── .env                    # Environment variables (create manually)
```

---

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Vite 5, React 18, TypeScript, react-i18next |
| **Backend** | FastAPI 0.111, Python 3.12, Uvicorn |
| **Game Engine** | Pure Python, Gymnasium 0.29, PettingZoo 1.24 |
| **Database** | PostgreSQL 16 (JSONB log storage) |
| **Cache / Pub-Sub** | Redis 7 (real-time WebSocket sync) |
| **AI Agents** | PyTorch 2.3 (PPO), random bot |
| **ORM** | SQLAlchemy 2.0, Alembic |
| **Containerization** | Docker, Docker Compose |

---

### Quick Start (Docker)

> Requires Docker and Docker Compose.

```bash
# 1. Clone the repository
git clone <repo-url>
cd castone

# 2. Create environment file
cat > .env << 'EOF'
DATABASE_URL=postgresql://puco_user:puco_password@db:5432/puco_rl
REDIS_URL=redis://redis:6379/0
VITE_API_TARGET=http://backend:8000
EOF

# 3. Build and start all services
docker-compose up --build
```

**Access points:**

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

---

### Local Development Setup

For running services without Docker.

#### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 16
- Redis 7

#### 1. Set up PuCo_RL virtual environment

```bash
cd PuCo_RL
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. Set up backend

```bash
cd backend
pip install -r requirements.txt

# Environment variables
export DATABASE_URL="postgresql://puco_user:puco_password@localhost:5432/puco_rl"
export REDIS_URL="redis://localhost:6379/0"
export PYTHONPATH="/absolute/path/to/castone/PuCo_RL:/absolute/path/to/castone/backend"

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 3. Set up frontend

```bash
cd frontend
npm install
npm run dev     # Starts at http://localhost:5173
```

> The Vite dev proxy forwards all `/api/*` requests to `http://localhost:8000`.

#### 4. Run tests

```bash
# Game engine tests
cd PuCo_RL
source .venv/bin/activate
pytest tests/ -v

# Backend unit tests (uses SQLite, no PostgreSQL required)
cd backend
DATABASE_URL="sqlite:///./test.db" \
PYTHONPATH="../PuCo_RL:." \
python3 -m pytest tests/test_legacy_features.py --noconftest -v
```

---

### How Gameplay Logs Are Stored

Every game action is recorded through **two parallel pipelines**.

#### Pipeline 1: PostgreSQL `game_logs` Table

A row is inserted for each action. The `state_before` and `state_after` columns use PostgreSQL's native JSONB type, allowing efficient querying of nested fields.

**Schema:**

```
game_logs
├── id                (integer, PK, auto-increment)
├── game_id           (UUID, FK → games.id, indexed)
├── round             (integer, indexed)
├── step              (integer)
├── actor_id          (string)              — e.g. "player_0"
├── action_data       (JSON)               — {"action": 5}
├── available_options (JSON)               — action mask, 200-element bool array
├── state_before      (JSON)               — full game state snapshot before action
├── state_after       (JSON)               — full game state snapshot after action
└── timestamp         (datetime, indexed)
```

**Source:** `backend/app/services/game_service.py`

#### Pipeline 2: JSONL Files in `/data/logs/`

Each transition is appended as a newline-delimited JSON record. Files are rotated daily. This format can be consumed directly by PyTorch `Dataset` classes for offline RL training.

**File path:** `/data/logs/transitions_YYYY-MM-DD.jsonl`

**Record format (one line per transition):**

```json
{
  "timestamp": "2025-01-15T14:23:01.123Z",
  "game_id": "550e8400-e29b-41d4-a716-446655440000",
  "actor_id": "player_0",
  "state_before": {
    "players": { "player_0": { "victory_points": 3, "doubloons": 2, ... } },
    "roles": { "settler": { "taken_by": null }, ... },
    "ships": [ { "capacity": 4, "good": "corn", "load": 2 }, ... ]
  },
  "action": 3,
  "reward": 0.0,
  "done": false,
  "state_after": { ... },
  "info": { "round": 2, "step": 15, "phase": "select_role" }
}
```

**Source:** `backend/app/services/ml_logger.py`

#### Pipeline 3: Redis Pub/Sub (real-time only, not persisted)

```
Channel:  game:{game_id}:events
Type:     STATE_UPDATE
Content:  Serialized current game state (JSON)
Purpose:  Broadcast to all WebSocket clients in the same game room
```

Redis data is **not persisted** across restarts. It serves only for live synchronization.

---

### Inspecting Stored Data

#### PostgreSQL

```bash
# Connect via Docker
docker exec -it puco_db psql -U puco_user -d puco_rl

# Connect directly
psql postgresql://puco_user:puco_password@localhost:5432/puco_rl
```

**Useful queries:**

```sql
-- List all games
SELECT id, title, status, num_players, created_at
FROM games
ORDER BY created_at DESC
LIMIT 10;

-- All logs for a specific game
SELECT id, round, step, actor_id, action_data, timestamp
FROM game_logs
WHERE game_id = '<game-uuid>'
ORDER BY step ASC;

-- Total action count per game
SELECT game_id, COUNT(*) AS total_steps
FROM game_logs
GROUP BY game_id
ORDER BY total_steps DESC;

-- Query nested JSONB fields (e.g., player victory points at each step)
SELECT
  step,
  actor_id,
  state_before->'players'->'player_0'->>'victory_points' AS p0_vp,
  action_data
FROM game_logs
WHERE game_id = '<game-uuid>'
ORDER BY step ASC;

-- Action distribution
SELECT
  (action_data->>'action')::int AS action_idx,
  COUNT(*) AS count
FROM game_logs
GROUP BY action_idx
ORDER BY count DESC;
```

#### Redis

```bash
# Connect via Docker
docker exec -it puco_redis redis-cli

# Connect directly
redis-cli -h localhost -p 6379
```

**Useful commands:**

```bash
# List active game channels
PUBSUB CHANNELS game:*

# Subscribe to a game channel (live monitoring)
SUBSCRIBE game:<game-id>:events

# List all keys
KEYS *

# Memory usage
INFO memory

# Real-time command monitor
MONITOR
```

#### JSONL Log Files

```bash
# List log files (Docker)
docker exec -it puco_backend ls /data/logs/

# Pretty-print first record
docker exec -it puco_backend sh -c \
  "head -1 /data/logs/transitions_$(date +%Y-%m-%d).jsonl | python3 -m json.tool"

# Count transitions per game
docker exec -it puco_backend python3 -c "
import json
from collections import Counter
with open('/data/logs/transitions_$(date +%Y-%m-%d).jsonl') as f:
    records = [json.loads(l) for l in f if l.strip()]
counts = Counter(r['game_id'] for r in records)
for gid, n in counts.most_common(): print(f'{gid[:8]}...  {n} steps')
"
```

**Read JSONL in Python:**

```python
import json

with open("data/logs/transitions_2025-01-15.jsonl") as f:
    records = [json.loads(line) for line in f if line.strip()]

print(f"Total transitions: {len(records)}")
print(f"Unique games: {len(set(r['game_id'] for r in records))}")

# Extract state fields for RL training
for rec in records[:3]:
    print(f"Step {rec['info']['step']}: action={rec['action']}, done={rec['done']}")
```

#### Recommended GUI Tools

| Tool | Target | Notes |
|------|--------|-------|
| [pgAdmin 4](https://www.pgadmin.org/) | PostgreSQL | Web-based DB management UI |
| [TablePlus](https://tableplus.com/) | PostgreSQL + Redis | macOS/Windows GUI client |
| [DBeaver](https://dbeaver.io/) | PostgreSQL | Free, cross-platform |
| [RedisInsight](https://redis.io/insight/) | Redis | Official Redis GUI |
| [Swagger UI](http://localhost:8000/docs) | REST API | Built-in API explorer |

---

### Architecture Details

#### Game Action Flow

```
Client (React)
    │  POST /api/action/<type>  { player, ... }
    ▼
FastAPI (legacy.py)
    │  action_translator.py → integer index
    │  session.game.step(action)
    ▼
EngineWrapper (wrapper.py)
    │  PuCo_RL PuertoRicoEnv.step(action)
    ▼
PuertoRicoGame (engine.py)
    │  State mutation
    ▼
serialize_game_state() → JSON response
    │
    ├─→ PostgreSQL: INSERT INTO game_logs (JSONB)
    ├─→ /data/logs/: JSONL append (async)
    └─→ Redis Pub/Sub → WebSocket broadcast
```

#### Bot Execution Flow

```
After each human action
    └─→ _run_pending_bots()
          │  Check if next player is a bot
          │  If yes: get_action_mask() → pick valid action
          │    random bot: random.choice(valid_actions)
          │    ppo bot:    model inference
          └─→ Same game.step(action) pipeline
```

#### Action Index Mapping

```
0 – 7   : Select role (Role.SETTLER=0 … Role.PROSPECTOR=7)
8 – 13  : Settler — choose face-up plantation (index 0–5)
14      : Settler — take quarry
15      : Pass
16 – 38 : Builder — build building (23 types)
39 – 43 : Trader — sell good (5 goods)
44 – 58 : Captain — load ship (ship_idx × 5 + good)
59 – 63 : Captain — load via Wharf
69 – 92 : Mayor — colony placement toggle
93 – 97 : Craftsman — privilege good selection
105     : Use Hacienda to draw extra plantation
```

#### Database Schema

```
users
├── id (UUID, PK)
├── google_id (string, unique, indexed)
├── nickname (string)
├── total_games (int, default 0)
└── win_rate (int, default 0)

games
├── id (UUID, PK)
├── title (string)
├── status (string: WAITING | PROGRESS | FINISHED)
├── num_players (int)
├── players (JSON)           — array of player IDs
├── model_versions (JSON)    — e.g. {"0": "PPO_v2"}
├── winner_id (string, nullable)
└── created_at (datetime)

game_logs
├── id (int, PK, auto-increment)
├── game_id (UUID, FK → games.id, indexed)
├── round (int, indexed)     — partition key in production
├── step (int)
├── actor_id (string)
├── action_data (JSON)
├── available_options (JSON) — 200-element boolean action mask
├── state_before (JSON)
├── state_after (JSON)
└── timestamp (datetime, indexed)
```

---

### Environment Variables

Create a `.env` file in the project root:

```bash
# Database
DATABASE_URL=postgresql://puco_user:puco_password@db:5432/puco_rl

# Redis
REDIS_URL=redis://redis:6379/0

# Frontend → Backend proxy target (Docker)
VITE_API_TARGET=http://backend:8000

# (Optional) Google OAuth
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

**For local development (no Docker):**

```bash
DATABASE_URL=postgresql://puco_user:puco_password@localhost:5432/puco_rl
REDIS_URL=redis://localhost:6379/0
VITE_API_TARGET=http://localhost:8000
```

**Full variable reference:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | — | Redis connection string |
| `VITE_API_TARGET` | Yes | — | Backend URL for Vite proxy |
| `GOOGLE_CLIENT_ID` | No | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | No | — | Google OAuth client secret |

---

### Troubleshooting

#### PostgreSQL connection refused

```bash
# Check container status
docker-compose ps

# Check PostgreSQL health
docker exec puco_db pg_isready -U puco_user -d puco_rl

# View logs
docker-compose logs db
```

#### Redis connection refused

```bash
docker exec puco_redis redis-cli ping    # Should return: PONG
docker-compose logs redis
```

#### Backend ModuleNotFoundError

```
ModuleNotFoundError: No module named 'configs'
```

`PYTHONPATH` must include the `PuCo_RL` directory:

```bash
export PYTHONPATH="/absolute/path/to/castone/PuCo_RL:/absolute/path/to/castone/backend"
```

In Docker this is set automatically via `docker-compose.yml`.

#### Frontend cannot reach API

Check the proxy config in `frontend/vite.config.ts`:

```typescript
proxy: {
  '/api': { target: process.env.VITE_API_TARGET ?? 'http://localhost:8000' }
}
```

#### Log files not being created

```bash
# Verify /data/logs mount in Docker
docker exec puco_backend ls /data/logs/

# Check write permissions
docker exec puco_backend touch /data/logs/test.txt
```
