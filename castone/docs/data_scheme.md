# PuCo 데이터 명세서 (Data Schema)

> 최종 업데이트: 2026-03-22
> 이 문서는 PostgreSQL과 Redis에 저장되는 모든 데이터의 구조, 타입, 제약 조건을 설명합니다.

---

## 1. PostgreSQL 스키마

### 1.1 `users` 테이블

유저 프로필 및 통계 데이터를 저장합니다. Google OAuth로 가입한 플레이어만 기록됩니다.

| 컬럼 | 타입 | 제약 | 기본값 | 설명 |
|------|------|------|--------|------|
| `id` | UUID | PK | uuid4() | 유저 고유 식별자 |
| `google_id` | VARCHAR | UNIQUE, NOT NULL | — | Google 계정 고유 ID |
| `nickname` | VARCHAR | — | — | 게임 내 표시 이름 |
| `total_games` | INTEGER | — | 0 | 참여한 총 게임 수 |
| `win_rate` | FLOAT | — | 0.0 | 승률 (0.0 ~ 1.0) |

**인덱스:**
- `ix_users_google_id` — UNIQUE (google_id)

**비고:**
- `win_rate`는 게임 종료 시 백엔드에서 계산하여 업데이트 (`total_games`, `winner_id` 기반)
- 봇(AI)은 users 테이블에 기록하지 않음

---

### 1.2 `games` 테이블

게임 세션의 메타데이터를 저장합니다. 한 게임의 생명주기(WAITING → PROGRESS → FINISHED) 전체를 추적합니다.

| 컬럼 | 타입 | 제약 | 기본값 | 설명 |
|------|------|------|--------|------|
| `id` | UUID | PK | uuid4() | 게임 세션 고유 식별자 |
| `title` | VARCHAR | — | — | 방 제목 |
| `status` | VARCHAR | NOT NULL | — | 게임 상태: `WAITING` / `PROGRESS` / `FINISHED` |
| `num_players` | INTEGER | — | — | 총 플레이어 수 (인간 + 봇 포함, 2~5명) |
| `players` | JSONB | — | `[]` | 플레이어 순서 배열. 인간: User UUID, 봇: `"BOT_{TYPE}"` |
| `model_versions` | JSONB | — | `{}` | 봇 모델 버전 맵. `{"player_idx": "PPO_v2"}` |
| `winner_id` | VARCHAR | nullable | NULL | 승리자 (User UUID 또는 봇 식별자) |
| `created_at` | TIMESTAMPTZ | — | now() | 방 생성 시각 |
| `updated_at` | TIMESTAMPTZ | — | now() | 마지막 업데이트 시각 (ORM onupdate) |

**인덱스:**
- `ix_games_status` — status 컬럼 (활성 게임 목록 조회용)

**players 배열 구조:**
```json
["550e8400-e29b-41d4-a716-446655440000", "BOT_PPO_1", "BOT_RANDOM_2"]
```
- 인덱스 순서 = 게임 내 플레이어 순서
- 인간 플레이어: `users.id` (UUID 문자열)
- 봇 플레이어: `"BOT_{MODEL_TYPE}_{숫자}"` 형식

---

### 1.3 `game_logs` 테이블

RL 학습을 위한 게임 전환 데이터를 저장합니다. 매 유효한 액션마다 1개의 레코드가 생성됩니다.

| 컬럼 | 타입 | 제약 | 기본값 | 설명 |
|------|------|------|--------|------|
| `id` | INTEGER | PK, autoincrement | — | 레코드 고유 ID |
| `game_id` | UUID | FK → games.id, NOT NULL | — | 해당 게임 세션 |
| `round` | INTEGER | — | — | 게임 내 라운드 번호 (1부터 시작) |
| `step` | INTEGER | — | — | 라운드 내 스텝 번호 |
| `actor_id` | VARCHAR | — | — | 액션을 수행한 플레이어 식별자 |
| `action_data` | JSONB | — | — | 수행된 액션 상세 정보 |
| `available_options` | JSONB | — | — | 액션 수행 당시의 액션 마스크 (0/1 배열) |
| `state_before` | JSONB | — | — | 액션 수행 전 게임 전체 상태 스냅샷 |
| `state_after` | JSONB | — | — | 액션 수행 후 게임 전체 상태 스냅샷 |
| `timestamp` | TIMESTAMPTZ | — | now() | 레코드 생성 시각 |

**인덱스:**
- `ix_game_logs_game_id` — game_id (단일)
- `ix_game_logs_round` — round (단일)
- `ix_game_logs_timestamp` — timestamp
- `ix_game_logs_game_round` — (game_id, round) **복합 인덱스** (RL 데이터 추출 최적화)

**action_data 구조:**
```json
{ "action": 3 }
```
- `action`: 게임 엔진에 전달된 이산 액션 인덱스 (0~99+)

**available_options (액션 마스크) 구조:**
```json
[0, 0, 1, 0, 1, 0, 0, 1, ...]
```
- 길이: 게임 엔진의 action space 크기 (100+)
- `1`: 해당 인덱스의 액션이 현재 유효함
- `0`: 해당 인덱스의 액션이 현재 불가

**state 스냅샷 구조 (state_before / state_after):**

```json
{
  "meta": {
    "round": 1,
    "num_players": 3,
    "governor": "player_0",
    "phase": "role_selection",
    "active_player": "player_0",
    "active_role": null,
    "vp_supply_remaining": 75,
    "end_game_triggered": false
  },
  "common_board": {
    "roles": { "settler": {"doubloons_on_role": 0, "taken_by": null}, ... },
    "colonists": {"ship": 3, "supply": 45},
    "trading_house": {"goods": [], "d_spaces_used": 0, "d_is_full": false},
    "cargo_ships": [{"capacity": 4, "good": null, "d_is_full": false}, ...],
    "available_plantations": {"face_up": ["corn", "indigo", ...], "draw_pile": {...}},
    "available_buildings": { "small_indigo_plant": {"cost": 1, "vp": 1, ...}, ... },
    "goods_supply": {"corn": 10, "indigo": 11, "sugar": 11, "tobacco": 9, "coffee": 9}
  },
  "players": {
    "player_0": {
      "display_name": "Alice",
      "doubloons": 3,
      "vp_chips": 0,
      "goods": {"corn": 0, "indigo": 0, ...},
      "island": {"plantations": [{"type": "indigo", "colonized": false}, ...], ...},
      "city": {"buildings": [], "colonists_unplaced": 0, ...},
      "production": {"corn": {"can_produce": false, "amount": 0}, ...}
    }
  },
  "history": [],
  "bot_players": {"player_1": "ppo", "player_2": "ppo"}
}
```

**데이터 보존 정책:**
- `game_logs`는 영구 보관 (RL 학습 데이터셋 축적 목적)
- 삭제 없음, 아카이빙 없음

---

## 2. Redis 데이터 구조

### 2.1 게임 상태 캐시

| Key | Type | TTL | 설명 |
|-----|------|-----|------|
| `game:{game_id}:state` | STRING (JSON) | 900초 (15분) / 종료 후 300초 (5분) | 현재 게임 상태 스냅샷 (WebSocket 재접속용) |
| `game:{game_id}:events` | PUB/SUB Channel | — | 실시간 게임 이벤트 브로드캐스트 채널 |

**`game:{game_id}:state` 값 구조:**
`state_before` / `state_after`와 동일한 전체 게임 상태 JSON

**TTL 갱신 규칙:**
- 모든 액션 처리 시 TTL 자동 갱신 (`SET ... EX 900`)
- 게임 종료 시 5분으로 단축 (`SET ... EX 300`)

---

### 2.2 플레이어 접속 상태

| Key | Type | TTL | 설명 |
|-----|------|-----|------|
| `game:{game_id}:players` | HASH | 900초 | 플레이어별 접속 상태 추적 |

**Hash 필드:**
```
player_uuid_1 → "connected" | "disconnected"
player_uuid_2 → "connected" | "disconnected"
```

**업데이트 시점:**
- WebSocket 연결 시: `connected` 설정
- WebSocket 연결 해제 시: `disconnected` 설정
- 재연결 시: 다시 `connected`로 갱신

---

### 2.3 게임 메타데이터

| Key | Type | TTL | 설명 |
|-----|------|-----|------|
| `game:{game_id}:meta` | HASH | 900초 / 종료 후 300초 | 이탈/타임아웃 로직에 필요한 게임 정보 |

**Hash 필드:**

| 필드 | 값 예시 | 설명 |
|------|---------|------|
| `status` | `"PROGRESS"` / `"FINISHED"` | 현재 게임 상태 |
| `human_count` | `"2"` | 인간 플레이어 수 |
| `num_players` | `"3"` | 전체 플레이어 수 |

---

### 2.4 이탈 타임아웃 관리

이탈 타임아웃은 Redis 키가 아닌 **asyncio Task**로 관리됩니다 (Python 메모리 내):

- 이탈 감지 → `asyncio.create_task(_disconnect_timeout())` 생성
- `_disconnect_timers: Dict["{game_id}:{player_id}", asyncio.Task]` 딕셔너리에 저장
- 재접속 시 → `task.cancel()` 호출하여 타이머 취소
- 타임아웃(10분) 경과 → 게임 자동 종료 + `GAME_ENDED` 브로드캐스트

---

## 3. PUB/SUB 이벤트 메시지 구조

WebSocket 클라이언트가 받는 실시간 메시지 형식입니다.

### STATE_UPDATE (서버 → 클라이언트)
```json
{
  "type": "STATE_UPDATE",
  "data": { /* 전체 게임 상태 스냅샷 */ },
  "action_mask": [0, 1, 0, 1, ...]
}
```

### PLAYER_DISCONNECTED (서버 → 클라이언트)
```json
{
  "type": "PLAYER_DISCONNECTED",
  "player_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Player 550e8400... has disconnected.",
  "options": ["end_game", "wait"],
  "timeout_seconds": 600
}
```

### GAME_ENDED (서버 → 클라이언트)
```json
{
  "type": "GAME_ENDED",
  "reason": "player_disconnect_timeout" | "player_request",
  "disconnected_player": "550e8400-...",
  "requested_by": "aa11bb22-..."
}
```

### END_GAME_REQUEST (클라이언트 → 서버)
```json
{
  "type": "END_GAME_REQUEST"
}
```

---

## 4. RL 학습 데이터 파이프라인

game_logs는 두 곳에 동시에 기록됩니다:

1. **PostgreSQL** `game_logs` 테이블 — 영구 저장 (쿼리/분석용)
2. **JSONL 파일** — `/data/logs/transitions_YYYY-MM-DD.jsonl` (배치 학습 입력용)

**JSONL 레코드 구조:**
```json
{
  "game_id": "uuid-string",
  "actor_id": "player_0",
  "state_before": { ... },
  "action": 3,
  "reward": 0.0,
  "done": false,
  "state_after": { ... },
  "info": { "round": 1, "step": 2 }
}
```

---

## 5. 데이터 흐름 요약

```
[클라이언트 HTTP POST /game/{id}/action]
        ↓
[FastAPI: JWT 검증 → GameService.process_action()]
        ↓
[EngineWrapper.step(action)] ← PuCo_RL 게임 엔진
        ↓
┌────────────────────────────────────────┐
│ 원자적 저장                             │
│  1. PostgreSQL game_logs (JSONB)       │
│  2. JSONL 파일 (비동기, MLLogger)       │
└────────────────────────────────────────┘
        ↓
[Redis SET game:{id}:state EX 900]
[Redis PUBLISH game:{id}:events]
        ↓
[WebSocket 브로드캐스트 → 모든 클라이언트]
```
