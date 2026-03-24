# Puerto Rico AI Battle Platform — Architecture Design

> **설계 기준:** Kaizen (단계적 개선) · Backend Architect · Backend-Dev-Guidelines · CC-Skill-Backend-Patterns
> **목적:** RL 학습 데이터 수집을 위한 다인용 보드게임 플랫폼 (인간 vs AI)
> **작성일:** 2026-03-24

---

## 1. 프로젝트 개요

```
Puerto Rico AI Battle Platform
├── 목적: 고품질 RL 학습 데이터셋 생성 (state_before, action, mask, state_after)
├── 게임: Puerto Rico 보드게임 (3인 기준)
├── 플레이어: 인간 + AI 봇 (PPO / HPPO / Random)
└── 핵심: 모든 액션을 PostgreSQL에 원자적으로 저장
```

---

## 2. AS-IS 구조 (현재 — 문제 있음)

### 2-1. 시스템 흐름

```
Frontend (Next.js)
    │
    │  POST /api/action/... (매 액션마다 반복)
    ▼
Legacy API (/api/*)
    │
    ├─ _step(action)          ← EngineWrapper.step() 동기 호출
    │
    └─ _run_pending_bots()    ← 루프 5000회 (ML 추론 동기)
           │
           ├─ BotService.get_action()  ← PPO/HPPO 추론 (블로킹)
           └─ engine.step()
    │
    ▼
response 반환 (수초 소요)
    │
    ▼
Frontend → 다시 POST ... (무한 반복)
```

### 2-2. 핵심 문제점

| 문제 | 원인 | 영향 |
|------|------|------|
| POST 폭탄 | 프론트가 게임 루프를 HTTP로 직접 구동 | 로그 오염, 불필요한 트래픽 |
| HTTP 핸들러 블로킹 | ML 추론이 동기적으로 HTTP 요청 안에서 실행 | 응답 지연 (수초) |
| 프론트 종속 게임 루프 | 연결 끊기면 봇 게임 정지 | 데이터 수집 불안정 |
| Singleton session | SessionManager 단일 인스턴스 | 수평 스케일링 불가 |
| 레이어 혼재 | Legacy API가 라우팅·비즈니스·ML 추론 전부 처리 | 유지보수 불가 |
| DB 저장 없음 (Legacy) | Legacy API는 인메모리만 사용 | RL 데이터 유실 |

---

## 3. TO-BE 구조 (목표)

### 3-1. 전체 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                        │
│                                                                  │
│   ┌──────────────┐    ┌──────────────────────────────────────┐  │
│   │  Game UI     │    │  WebSocket Client                    │  │
│   │              │◄───│  ws://server/api/v1/ws/game/{id}     │  │
│   │  Human       │    │  - STATE_UPDATE 수신                 │  │
│   │  Action만    │    │  - 봇 턴 결과 수신                   │  │
│   │  POST 1회    │    │  - 게임 종료 수신                    │  │
│   └──────┬───────┘    └──────────────────────────────────────┘  │
└──────────┼──────────────────────────────────────────────────────┘
           │ POST /api/v1/game/action
           │ (JWT 포함, 인간 액션만)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway Layer (FastAPI)                    │
│                                                                  │
│  /api/v1/game/action   ──► GameRouter (얇음, 라우팅만)          │
│  /api/v1/ws/game/{id}  ──► WebSocket Endpoint                   │
│  /api/v1/auth/*        ──► Auth Router (Google OAuth)            │
│  /api/* (Legacy)       ──► [Deprecated — 봇 전용 테스트만]       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Service Layer                              │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  GameService (authoritative)                             │   │
│  │  - process_action(game_id, actor_id, action)             │   │
│  │  - start_game(game_id)                                   │   │
│  │  - _schedule_next_bot_turn_if_needed()                   │   │
│  │  - _sync_to_redis()                                      │   │
│  │  - _store_game_meta()                                    │   │
│  └───────────────────┬─────────────────────────────────────┘   │
│                      │                                          │
│         ┌────────────┼────────────┐                            │
│         ▼            ▼            ▼                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐                   │
│  │BotService│ │MLLogger  │ │WebSocketMgr  │                   │
│  │(async)   │ │(async)   │ │broadcast()   │                   │
│  │PPO/HPPO  │ │RL 로그   │ │Redis Pub/Sub │                   │
│  │Random    │ │비동기 저장│ │              │                   │
│  └──────────┘ └──────────┘ └──────────────┘                   │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Engine Layer                               │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  EngineWrapper                                            │  │
│  │  - step(action) → {state_before, state_after, reward...} │  │
│  │  - get_state() → Dict                                    │  │
│  │  - get_action_mask() → List[int]                         │  │
│  │  - _round_count, _step_count 추적                        │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                   │
│                             ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  PuCo_RL (변경 금지)                                     │  │
│  │  PuertoRicoEnv (PettingZoo AEC)                          │  │
│  │  PuertoRicoGame (state machine)                          │  │
│  │  agents/ (PPO, HPPO, Random, MCTS)                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Storage Layer                              │
│                                                                  │
│  ┌───────────────────────┐   ┌───────────────────────────────┐ │
│  │  Redis                │   │  PostgreSQL                    │ │
│  │  game:{id}:state      │   │  games 테이블                  │ │
│  │  → 현재 상태 캐시     │   │  - id, status, players        │ │
│  │  (TTL: 15분/5분)      │   │                               │ │
│  │                       │   │  game_logs 테이블             │ │
│  │  game:{id}:events     │   │  - state_before (raw obs)     │ │
│  │  → Pub/Sub 채널       │   │  - state_after  (raw obs)     │ │
│  │                       │   │  - state_summary (가독 JSON)  │ │
│  │  game:{id}:meta       │   │  - action_data, action_mask   │ │
│  │  → human_count,       │   │  - round, step, actor_id      │ │
│  │    status             │   │  → RL 학습 데이터셋           │ │
│  └───────────────────────┘   └───────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

### 3-2. 게임 액션 플로우 — 인간 턴

```
Frontend
  │
  │  POST /api/v1/game/action
  │  Body: { game_id, action: 3 }
  │  Header: Authorization: Bearer <JWT>
  │
  ▼
GameRouter
  │  JWT 검증, game_id 파싱
  ▼
GameService.process_action(game_id, actor_id="user_xxx", action=3)
  │
  ├─[1] 액션 마스크 검증
  │     mask = engine.get_action_mask()
  │     if not mask[action]: raise ValueError
  │
  ├─[2] 엔진 실행
  │     result = engine.step(action)
  │     → state_before, state_after, reward, terminated, info
  │
  ├─[3] DB 저장 (동기)
  │     GameLog(state_before, state_after, state_summary, ...)
  │     db.commit()
  │
  ├─[4] Redis Pub/Sub (동기)
  │     redis.publish(game:{id}:events, STATE_UPDATE)
  │     → WebSocketManager → 모든 클라이언트 브로드캐스트
  │
  ├─[5] MLLogger (비동기 - fire & forget)
  │     asyncio.create_task(MLLogger.log_transition(...))
  │
  └─[6] 다음 턴이 봇이면 봇 태스크 스케줄
        asyncio.create_task(BotService.run_bot_turn(...))
  │
  ▼
response: { state, action_mask }  ← 즉시 반환 (봇 완료 안 기다림)
  │
  ▼
Frontend ← 200 OK 수신
  │
  └─ (이후 상태 업데이트는 WebSocket으로 수신)
```

---

### 3-3. 게임 액션 플로우 — 봇 턴 (백그라운드)

```
asyncio.create_task 로 백그라운드 실행
  │
BotService.run_bot_turn(game_id, engine, actor_id="BOT_ppo_0")
  │
  ├─[1] await asyncio.sleep(1.0~2.0s)  ← 자연스러운 봇 "생각" 딜레이
  │
  ├─[2] 현재 상태 & 마스크 수집
  │     mask = engine.get_action_mask()
  │     obs = engine.last_obs
  │
  ├─[3] ML 추론 (동기, but 백그라운드 태스크 안에서)
  │     action = BotService.get_action(bot_type, game_context)
  │     → agent_registry.get_wrapper("ppo", obs_dim)
  │     → wrapper.act(obs_tensor, mask_tensor, phase_id)
  │
  ├─[4] 액션 콜백 실행
  │     process_action_callback(game_id, actor_id, action)
  │     → GameService.process_action() 재귀 호출
  │        (DB 저장 + Redis Pub/Sub + 다음 봇 스케줄)
  │
  └─[5] 에러 시 폴백
        action = 15 (pass)
        에러 로그만 기록, 게임 계속

※ Frontend는 POST 없음 — WebSocket STATE_UPDATE만 수신
```

---

### 3-4. WebSocket 실시간 브로드캐스트

```
GameService._sync_to_redis()
  │
  ├─[1] Redis SET  game:{id}:state  (상태 캐시, TTL 900s)
  │
  └─[2] Redis PUBLISH  game:{id}:events
              │
              ▼
        WebSocketManager (ws_manager.py)
        subscribe 루프 (Redis Pub/Sub)
              │
              └─ broadcast_to_game(game_id, data)
                      │
                      └─ 해당 game_id에 연결된
                         모든 WebSocket 클라이언트로 전송
                              │
                              ▼
                        Frontend WebSocket Client
                        → UI 상태 업데이트
```

---

### 3-5. RL 데이터 파이프라인

```
engine.step(action)
  │
  ├── state_before  ──────────────────────────────────┐
  │   (raw numpy obs → list, RL 학습용)               │
  │                                                    │
  ├── state_after   ──────────────────────────────────┤
  │   (raw numpy obs → list, RL 학습용)               │
  │                                                    ▼
  ├── action_mask   ──────────► game_logs 테이블 (PostgreSQL)
  │   (가능한 액션 리스트)       │
  │                              ├── state_before  (JSONB)
  ├── action_data   ─────────────┤── state_after   (JSONB)
  │   {"action": int}            ├── state_summary (JSONB) ◄── 가독성
  │                              ├── available_options (JSONB)
  └── state_summary ─────────────┤── action_data   (JSONB)
      (human-readable)           ├── actor_id, round, step
      {                          └── game_id (FK → games)
        "phase": "captain_action",
        "role": "captain",            ▼
        "vp_supply": 68,        Adminer SQL 조회
        "players": {            SELECT state_summary->>'phase',
          "p0": {                      state_summary->'players'
            "vp": 5,            FROM game_logs
            "doubloons": 3,     ORDER BY id;
            "goods": {"corn":2}
          }
        }
      }
```

---

## 4. 레이어 구조 상세 (Backend-Dev-Guidelines 기준)

```
castone/backend/app/
│
├── main.py                     ← FastAPI app, 라우터 등록
│
├── api/
│   ├── v1/
│   │   ├── auth.py             ← [Routes] Google OAuth, JWT 발급
│   │   ├── game.py             ← [Routes] 게임 액션, 방 생성/조회
│   │   └── ws.py               ← [Routes] WebSocket 연결
│   └── legacy.py               ← [Deprecated] 봇 테스트용 Legacy
│
├── services/                   ← [Business Logic Layer]
│   ├── game_service.py         ← 게임 액션 처리 (핵심)
│   ├── bot_service.py          ← ML 봇 추론 (async)
│   ├── ws_manager.py           ← WebSocket + Redis Pub/Sub
│   ├── ml_logger.py            ← RL 전환 로깅 (async)
│   ├── state_serializer.py     ← 게임 상태 → JSON 변환
│   │                              + serialize_compact_summary()
│   ├── session_manager.py      ← Legacy용 인메모리 세션
│   └── agent_registry.py       ← 봇 에이전트 팩토리
│
├── engine_wrapper/
│   └── wrapper.py              ← [Engine Abstraction Layer]
│                                  PuCo_RL ↔ Backend 중간층
│                                  step(), get_state(), get_action_mask()
│
├── db/
│   └── models.py               ← SQLAlchemy ORM (User, GameSession, GameLog)
│
├── schemas/                    ← Pydantic 입력 검증
│   ├── auth.py
│   └── game.py
│
├── core/
│   └── redis.py                ← Redis 클라이언트 (sync/async)
│
└── dependencies.py             ← DB 세션, 엔진 주입

```

**레이어 규칙:**

```
Routes (api/)
  └─► Services (services/)       ← 비즈니스 로직 여기만
        └─► Engine (engine_wrapper/)
        └─► Storage (db/ + Redis)
        └─► Services (다른 서비스 호출 가능)

금지:
  Routes → DB 직접 접근    ❌
  Routes → Engine 직접 접근 ❌
  Engine → DB 직접 접근    ❌
```

---

## 5. 데이터 모델

### GameSession (games 테이블)

```python
class GameSession(Base):
    id          : UUID       # PK
    title       : String     # 게임 제목
    status      : String     # WAITING | PROGRESS | FINISHED
    num_players : Integer    # 3 (현재 3인 고정)
    players     : JSONB      # ["user_xxx", "BOT_ppo_0", "BOT_random_1"]
    model_versions: JSONB    # {"BOT_ppo_0": "v1.2", ...}
    winner_id   : String     # nullable
    created_at  : DateTime
    updated_at  : DateTime
```

### GameLog (game_logs 테이블) — RL 학습 데이터

```python
class GameLog(Base):
    id               : Integer  # PK, autoincrement
    game_id          : UUID     # FK → games.id
    round            : Integer  # 라운드 번호 (governor 변경 기준)
    step             : Integer  # 전체 스텝 번호
    actor_id         : String   # "user_xxx" | "BOT_ppo_0"
    action_data      : JSONB    # {"action": 42}
    available_options: JSONB    # [0,1,0,1,...] (action mask)
    state_before     : JSONB    # raw observation (RL 학습용)
    state_after      : JSONB    # raw observation (RL 학습용)
    state_summary    : JSONB    # 가독 요약 (Adminer 조회용)
    timestamp        : DateTime
```

### state_summary 예시 (Adminer에서 보이는 형태)

```json
{
  "phase": "captain_action",
  "role": "captain",
  "current_player": 1,
  "governor": 0,
  "vp_supply": 68,
  "colonist_supply": 50,
  "colonist_ship": 3,
  "players": {
    "p0": {
      "doubloons": 3,
      "vp": 2,
      "goods": { "corn": 2, "indigo": 1 },
      "buildings": ["small_indigo_plant", "small_sugar_mill"],
      "plantations": { "corn": 2, "indigo": 1 },
      "colonists": 4,
      "empty_city": 8
    },
    "p1": { "doubloons": 5, "vp": 0, "goods": {}, ... },
    "p2": { "doubloons": 4, "vp": 1, "goods": { "sugar": 2 }, ... }
  }
}
```

---

## 6. Adminer SQL 조회 가이드

### 기본 상태 추적

```sql
SELECT
  id, round, step, actor_id,
  action_data->>'action'        AS action,
  state_summary->>'phase'       AS phase,
  state_summary->>'role'        AS role,
  (state_summary->>'vp_supply')::int AS vp_supply,
  (state_summary->>'colonist_supply')::int AS colonists
FROM game_logs
ORDER BY id DESC
LIMIT 50;
```

### 플레이어별 VP/골드 추적

```sql
SELECT
  id, round, step,
  state_summary->>'phase' AS phase,
  (state_summary->'players'->'p0'->>'vp')::int       AS p0_vp,
  (state_summary->'players'->'p1'->>'vp')::int       AS p1_vp,
  (state_summary->'players'->'p2'->>'vp')::int       AS p2_vp,
  (state_summary->'players'->'p0'->>'doubloons')::int AS p0_gold,
  (state_summary->'players'->'p1'->>'doubloons')::int AS p1_gold,
  (state_summary->'players'->'p2'->>'doubloons')::int AS p2_gold
FROM game_logs
WHERE game_id = '<UUID>'
ORDER BY id;
```

### state_before 연속성 검증 (체인 확인)

```sql
SELECT
  id,
  state_before->'global_state'->'vp_chips'           AS before_vp,
  state_after->'global_state'->'vp_chips'            AS after_vp,
  LAG(state_after->'global_state'->'vp_chips') OVER (ORDER BY id)
                                                      AS prev_after_vp
FROM game_logs
WHERE game_id = '<UUID>'
ORDER BY id
LIMIT 30;
-- before_vp == prev_after_vp 이면 체인 정상
```

---

## 7. Kaizen 로드맵 (단계별 개선)

```
Phase 1 ✅ 완료
  ├── Mayor 400 에러 수정 (_run_pending_bots Mayor 토글 제한)
  ├── terminated/truncated 분리 (자연 종료 vs 강제 종료)
  ├── max_game_steps: 2000 → 50000 (자연 종료 가능하도록)
  └── round/step 추적 (EngineWrapper에 추가)

Phase 2 ✅ 완료
  ├── state_summary JSONB 컬럼 추가 (GameLog)
  ├── serialize_compact_summary() 함수 (state_serializer.py)
  └── Alembic migration 003 (state_summary)

Phase 3 🔜 다음 (핵심 — POST 폭탄 제거)
  ├── Frontend: /api/legacy → /api/v1/game/action 전환
  ├── Frontend: WebSocket 연결로 상태 수신
  ├── GameService 검증: asyncio bot task 정상 작동 확인
  └── Legacy API: 봇 전용 테스트 플래그 추가 (점진적 제거)

Phase 4 🔮 중기
  ├── Legacy API 완전 제거
  ├── GameService 레이어 분리 (Repository 패턴 도입)
  └── 단위 테스트 추가 (GameService, BotService)

Phase 5 🔮 장기
  ├── MLLogger → Redis Queue 기반 비동기 파이프라인
  ├── 수평 스케일링 (SessionManager → Redis 기반)
  └── 모니터링 (Prometheus + Grafana)
```

---

## 8. BFRI 평가 (Backend Feasibility Risk Index)

### Phase 3 — Frontend v1 API 전환

| 항목 | 점수 | 이유 |
|------|------|------|
| Architectural Fit | +4 | 목표 아키텍처와 일치 |
| Testability | +4 | WebSocket + REST 분리로 테스트 용이 |
| Business Logic Complexity | -2 | WebSocket 상태 관리 필요 |
| Data Risk | -1 | 기존 DB 저장 로직 그대로 유지 |
| Operational Risk | -2 | Frontend 변경, WebSocket 연결 안정성 |

**BFRI = (4+4) - (2+1+2) = 3** → ⚠️ Moderate — 테스트 + 모니터링 필요

---

## 9. 환경 변수 설정

```env
# 데이터베이스
DATABASE_URL=postgresql://puco_user:puco_password@db:5432/puco_rl

# Redis
REDIS_URL=redis://redis:6379/0

# 프론트엔드 → 백엔드 연결
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_WS_URL=ws://localhost:8000/api/v1/ws

# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

---

## 10. Docker 서비스 구성

```
docker-compose.yml
├── db        → PostgreSQL 5432 (게임 데이터, 유저, RL 로그)
├── redis     → Redis 6379 (Pub/Sub, 상태 캐시)
├── backend   → FastAPI 8000 (게임 서버, RL 데이터 수집)
├── frontend  → Next.js 3000 (게임 UI, WebSocket 클라이언트)
└── adminer   → Adminer 8080 (DB 조회 UI)
```

**실행:**
```bash
cd castone
docker compose up --build
```

**서비스 URL:**
- 게임: http://localhost:3000
- API: http://localhost:8000/docs
- DB 조회: http://localhost:8080

---

*이 문서는 설계 기준 문서입니다. 구현 시 각 Phase의 BFRI를 재평가하고 테스트를 먼저 작성하세요.*
