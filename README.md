# Castone

Puerto Rico 보드게임을 웹 환경에서 멀티플레이어 + AI 에이전트와 함께 플레이하고, 그 과정에서 운영 로그와 RL 재학습용 데이터를 동시에 남기는 플랫폼입니다.

현재 코드베이스는 크게 네 축으로 움직입니다.

- `frontend/`: Vite + React UI
- `backend/`: FastAPI 서버, 인증, 로비, 게임 진행, 저장
- `PuCo_RL/`: 실제 Puerto Rico 엔진과 RL 학습/평가 코드
- `vis/`: DB/JSONL 로그를 사람이 읽기 좋은 Markdown 리포트로 바꾸는 도구

## Docker로 실행하기


### 1. 서비스 기동

개발용:

```bash
docker compose up -d --build
docker compose ps
```

프로덕션 compose:

```bash
docker compose down
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

기본 접속 주소:

| 서비스 | 주소 |
| --- | --- |
| Frontend | `http://localhost:3000` |
| Backend | `http://localhost:8000` |
| Adminer | `http://localhost:8080` |
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |

프로덕션 compose 접속 주소:

| 서비스 | 주소 |
| --- | --- |
| Frontend | `http://localhost` |
| Backend | 외부 미노출, frontend nginx가 `/api` 를 내부 프록시 |

주의:

- dev와 prod compose를 동시에 올리지 말고, 전환할 때는 먼저 `down` 하세요.
- `adminer`는 기본 dev 기동에서 제외됩니다. 필요할 때만 아래처럼 띄우세요.

```bash
docker compose --profile adminer up -d adminer
```

- prod frontend 포트를 바꾸고 싶으면 `.env`에 `FRONTEND_PORT=3000` 같은 값을 추가하세요.

### 2. 상태 확인

개발용:

```bash
curl http://localhost:8000/health
```

프로덕션 compose:

```bash
curl http://localhost/health
```

### 3. Google 로그인 400 점검

- prod compose의 frontend는 Vite 정적 빌드라서, `VITE_GOOGLE_CLIENT_ID`를 바꿨으면 반드시 `docker compose -f docker-compose.prod.yml up -d --build` 로 다시 빌드해야 합니다.
- Google Cloud Console의 OAuth Client에서 `Authorized JavaScript origins`에 실제 접속 origin을 정확히 추가해야 합니다.
- dev 기본 주소는 `http://localhost:3000` 입니다.
- prod 기본 주소는 `http://localhost` 입니다.
- prod를 `FRONTEND_PORT=3000`으로 띄우면 origin은 `http://localhost:3000` 이 됩니다.

## 전체 구조

```text
castone/
├── frontend/                  # React UI
├── backend/                   # FastAPI 서버
│   ├── app/
│   │   ├── api/               # modern API + legacy API + websocket
│   │   ├── db/                # SQLAlchemy 모델
│   │   ├── engine_wrapper/    # FastAPI ↔ PuCo_RL bridge
│   │   ├── services/          # 게임 처리, 로그 저장, bot orchestration
│   │   └── schemas/           # Pydantic request/response schema
│   ├── alembic/               # DB migration
│   ├── tests/                 # backend tests
│   └── readme.md              # backend 전용 운영 가이드
├── PuCo_RL/                   # 게임 엔진, 에이전트, 학습 코드
├── data/
│   └── logs/
│       ├── games/             # ML/계보용 raw JSONL
│       └── replay/            # 사람이 읽는 replay JSON
├── vis/                       # 로그 시각화/감사 리포트
├── docs/                      # 설계/운영 관련 문서
├── docker-compose.yml
└── .env.example
```

## Documentation Map

상향식 문서 구조는 아래를 기준으로 봅니다. 하위 폴더 README가 역할과 의존성을 먼저 설명하고, 상위 폴더 README가 이를 묶습니다.

- [backend/README.md](backend/README.md)
- [frontend/README.md](frontend/README.md)
- [PuCo_RL/README.md](PuCo_RL/README.md)
- [data/README.md](data/README.md)
- [vis/README.md](vis/README.md)
- [imgs/README.md](imgs/README.md)
- [models/README.md](models/README.md)

## 코드베이스가 동작하는 방식

큰 흐름은 아래와 같습니다.

1. 프론트엔드가 방 생성, 입장, 액션 요청을 보냅니다.
2. `backend/app/api/` 라우터가 인증과 입력 검증을 처리합니다.
3. [game_service.py](backend/app/services/game_service.py) 가 게임 시작, 액션 적용, DB 기록, Redis 동기화를 담당합니다.
4. 실제 규칙 처리와 상태 전이는 `PuCo_RL` 엔진이 수행합니다.
5. 결과는 동시에 여러 저장소로 기록됩니다.

- PostgreSQL
  - 정본 운영 기록
- Redis
  - 실시간 상태 전달
- `data/logs/games/<game_id>.jsonl`
  - 계보/ML 분석용 raw transition
- `data/logs/replay/<game_id>.json`
  - 사람이 읽는 replay 로그

## 어떤 데이터가 어디에 저장되나

### PostgreSQL

주요 테이블은 [models.py](backend/app/db/models.py) 기준으로 아래 세 개입니다.

- `users`
  - Google 로그인 사용자 정보
  - `nickname`, `email`, `total_games`, `win_rate`
- `games`
  - 방/게임 메타데이터
  - `status`, `players`, `model_versions`, `host_id`
- `game_logs`
  - 액션 단위 감사 로그
  - `action_data`, `available_options`, `state_before`, `state_after`, `state_summary`

### Redis

Redis는 실시간 브로드캐스트와 상태 캐시 용도입니다.

- `game:<game_id>:state`
- `game:<game_id>:meta`
- `game:<game_id>:players`
- websocket/pub-sub 이벤트

주의:

- Redis는 운영 편의용 캐시이며, 감사 정본 저장소로 보지 않는 편이 맞습니다.

### 로컬 로그 파일

#### 1. `data/logs/games/<game_id>.jsonl`

용도:

- ML 재학습
- lineage 추적
- `vis/` 리포트 입력

생성 코드:

- [ml_logger.py](backend/app/services/ml_logger.py)

주요 필드:

- `state_before`
- `action`
- `reward`
- `done`
- `state_after`
- `info`
- 선택적으로 `action_mask_before`, `phase_id_before`, `current_player_idx_before`, `model_info`

#### 2. `data/logs/replay/<game_id>.json`

용도:

- 사람이 게임 진행을 읽기 쉽게 확인
- 최근 수순 검토
- 최종 점수와 replay 흐름 확인

생성 코드:

- [replay_logger.py](backend/app/services/replay_logger.py)

주요 필드:

- top-level
  - `game_id`, `title`, `status`, `players`, `model_versions`, `initial_state_summary`
- `entries`
  - `step`, `round`, `player`, `phase`, `action`, `commentary`
  - `state_summary_before`, `state_summary_after`
- 종료 후
  - `final_scores`, `result_summary`

#### 3. `PuCo_RL/logs/replay/*.json`

이 경로는 backend 런타임 로그가 아니라, `PuCo_RL` 쪽 오프라인 평가/재생성 로그입니다.

- `data/logs/replay/*.json`
  - backend 실게임 런타임 replay
- `PuCo_RL/logs/replay/*.json`
  - RL 평가/분석 스크립트가 생성한 replay

## 저장된 DB를 확인하는 방법

### 1. Adminer로 확인

브라우저에서:

- `http://localhost:8080`

접속 값:

- System: `PostgreSQL`
- Server: `db` 또는 `host.docker.internal` 상황에 따라 선택
- Username: `.env` 의 `POSTGRES_USER`
- Password: `.env` 의 `POSTGRES_PASSWORD`
- Database: `puco_rl`

### 2. psql로 직접 확인

```bash
docker compose exec db psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl
```

자주 쓰는 SQL:

```sql
\dt

SELECT id, title, status, players, model_versions, created_at
FROM games
ORDER BY created_at DESC
LIMIT 20;

SELECT game_id, round, step, actor_id, action_data, state_summary, timestamp
FROM game_logs
ORDER BY id DESC
LIMIT 30;
```

특정 게임 하나만 보고 싶다면:

```sql
SELECT step, actor_id, action_data, state_summary
FROM game_logs
WHERE game_id = 'YOUR_GAME_ID'
ORDER BY step, id;
```

## Redis를 확인하는 방법

```bash
docker compose exec redis redis-cli -a "$REDIS_PASSWORD"
```

자주 쓰는 명령:

```redis
KEYS game:*
HGETALL game:<game_id>:meta
HGETALL game:<game_id>:players
GET game:<game_id>:state
```

## 게임 데이터 로그를 확인하는 방법

### JSONL raw 로그

```bash
python - <<'PY'
import json
path = 'data/logs/games/YOUR_GAME_ID.jsonl'
with open(path, 'r', encoding='utf-8') as f:
    for _ in range(3):
        print(json.dumps(json.loads(next(f)), ensure_ascii=False, indent=2))
PY
```

### 사람이 읽는 replay 로그

```bash
python - <<'PY'
import json
path = 'data/logs/replay/YOUR_GAME_ID.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
for entry in data['entries'][-10:]:
    print(
        f"[step {entry['step']}] "
        f"P{entry['player']} | {entry['phase']} | {entry['action']} | "
        f"{entry.get('commentary', '')}"
    )
PY
```

### `vis/` 보고서로 보기

```bash
python vis/render_lineage_report.py \
  --lang ko \
  --jsonl data/logs/games/YOUR_GAME_ID.jsonl \
  --output vis/output/lineage_ko.md
```

```bash
python vis/render_behavior_report.py \
  --lang ko \
  --jsonl data/logs/games/YOUR_GAME_ID.jsonl \
  --output vis/output/behavior_ko.md
```

```bash
python vis/render_storage_report.py \
  --lang ko \
  --game-id YOUR_GAME_ID \
  --jsonl data/logs/games/YOUR_GAME_ID.jsonl \
  --output vis/output/storage_ko.md
```

## API 명세 요약

OpenAPI/Swagger는 `DEBUG=true` 일 때만 열립니다.

- Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

현재 FastAPI 등록 라우터는 [main.py](backend/app/main.py) 기준으로 아래와 같습니다.

### Modern API

#### Auth

| Method | Path | 설명 |
| --- | --- | --- |
| `POST` | `/api/puco/auth/google` | Google id_token 검증 후 JWT 발급 |
| `PATCH` | `/api/puco/auth/me/nickname` | 닉네임 설정/수정 |
| `GET` | `/api/puco/auth/me` | 현재 사용자 조회 |

#### Room

| Method | Path | 설명 |
| --- | --- | --- |
| `POST` | `/api/puco/rooms/` | 방 생성 |
| `GET` | `/api/puco/rooms/` | 대기 중 방 목록 조회 |
| `POST` | `/api/puco/rooms/{room_id}/join` | 방 입장 |
| `POST` | `/api/puco/rooms/bot-game` | 봇전 즉시 생성/시작 |
| `POST` | `/api/puco/rooms/{room_id}/leave` | 방 나가기 |

#### Game

| Method | Path | 설명 |
| --- | --- | --- |
| `POST` | `/api/puco/game/{game_id}/start` | 게임 시작 |
| `POST` | `/api/puco/game/{game_id}/action` | 일반 액션 수행 |
| `POST` | `/api/puco/game/{game_id}/mayor-distribute` | Mayor 배치 처리 |
| `POST` | `/api/puco/game/{game_id}/add-bot` | 대기방에 봇 추가 |
| `GET` | `/api/puco/game/{game_id}/final-score` | 최종 점수 계산 |

#### WebSocket

| Path | 설명 |
| --- | --- |
| `/api/puco/ws/{game_id}` | 게임 상태 실시간 스트림 |
| `/api/puco/ws/lobby/{room_id}` | 로비 상태 실시간 스트림 |

### Legacy API

기존 프런트/실험용 호환 경로는 `/api/*` 아래에 남아 있습니다.

주요 그룹:

- `backend/app/api/legacy/game.py`
  - `/api/new-game`, `/api/game-state`, `/api/final-score`, `/api/bot-types`
- `backend/app/api/legacy/lobby.py`
  - `/api/multiplayer/init`, `/api/lobby/join`, `/api/lobby/start`
- `backend/app/api/legacy/actions.py`
  - `/api/select-role`, `/api/build`, `/api/sell`, `/api/load-ship`, `/api/mayor-distribute` 등
- `backend/app/api/legacy/events.py`
  - `/api/events/stream`

주의:

- legacy 쓰기 엔드포인트는 `X-API-Key` 를 요구할 수 있습니다.
- 값은 `.env` 의 `INTERNAL_API_KEY`, `VITE_INTERNAL_API_KEY` 를 맞춰 사용합니다.

## 자주 참고할 문서

- [backend/README.md](backend/README.md)
  - backend 구조, PostgreSQL/Redis 접속, 로그 읽기
- [frontend/README.md](frontend/README.md)
  - 프론트 화면 구조, socket 흐름, 타입 경계
- [PuCo_RL/README.md](PuCo_RL/README.md)
  - canonical engine, action/env/agent 구조
- [vis/README.md](vis/README.md)
  - lineage/storage/behavior/audit 리포트 생성
- [vis/db/README.md](vis/db/README.md)
  - DB와 로그를 사람이 직접 대조하는 절차
- [docs/merge_readiness.md](docs/merge_readiness.md)
  - 최근 TDD/MLOps/운영 정리

참고:

- 폴더별 세부 역할과 의존성은 각 `README.md`를 따라 내려가며 보는 방식이 가장 정확합니다.

## 개발 체크포인트

- `docker compose down` 은 DB를 지우지 않습니다.
- `docker compose down -v` 는 DB와 Redis volume까지 지웁니다.
- backend Swagger는 `DEBUG=true` 일 때만 보입니다.
- 로그 검토는 보통 아래 순서가 가장 빠릅니다.

1. `games` 에서 대상 `game_id` 확인
2. `game_logs` 에서 액션/요약 확인
3. `data/logs/replay/<game_id>.json` 으로 사람 친화적인 흐름 확인
4. 필요하면 `data/logs/games/<game_id>.jsonl` 로 raw transition까지 추적
5. `vis/` 로 한국어 리포트 생성
