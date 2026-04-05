# Backend Guide

## 개요

`backend/`는 FastAPI 기반 서버로, 방/로비/게임 진행, 봇 추론 연결, WebSocket 전달, 그리고 게임 데이터 저장을 담당합니다.

주요 책임은 아래와 같습니다.

- REST API와 WebSocket으로 프론트엔드 요청 처리
- `PuCo_RL` 엔진을 감싸 실제 게임 상태를 진행
- PostgreSQL에 게임 세션과 액션 로그 저장
- Redis에 실시간 상태와 연결 상태 저장
- 로컬 파일에 ML용 전이 로그와 사람 확인용 replay 로그 저장

핵심 진입점:

- `backend/app/main.py`
- `backend/app/api/channel/`
- `backend/app/services/game_service.py`
- `backend/app/services/ml_logger.py`
- `backend/app/services/replay_logger.py`

## Docker 환경에서 접속하기

프로젝트 루트에서 docker compose가 올라가 있다는 기준입니다.

### PostgreSQL 접속

컨테이너 안에서 바로 들어가기:

```bash
docker compose exec db psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl
```

자주 보는 테이블:

```sql
\dt
SELECT id, title, status, created_at FROM games ORDER BY created_at DESC LIMIT 20;
SELECT game_id, round, step, actor_id, action_data, state_summary
FROM game_logs
ORDER BY id DESC
LIMIT 20;
```

브라우저로 보기:

- Adminer: `http://localhost:8080`

### Redis 접속

```bash
docker compose exec redis redis-cli -a "$REDIS_PASSWORD"
```

자주 보는 키:

```redis
KEYS game:*
HGETALL game:<game_id>:meta
HGETALL game:<game_id>:players
GET game:<game_id>:state
```

## 데이터가 어디에 저장되는가

### 1. PostgreSQL

정규화된 서버 기록입니다.

- `games`
  - 방/게임 메타데이터
  - `players`, `model_versions`, `host_id`, `status`
- `game_logs`
  - 각 액션의 서버 기준 정본 로그
  - `action_data`, `available_options`, `state_before`, `state_after`, `state_summary`

장점:

- 질의하기 좋음
- 운영 디버깅에 강함
- 특정 step만 빠르게 찾기 좋음

### 2. Redis

실시간 전달/캐시 레이어입니다.

- `game:<game_id>:state`
  - 최신 직렬화 상태
- `game:<game_id>:meta`
  - 상태, 사람 수 같은 메타 정보
- `game:<game_id>:players`
  - 접속 상태
- pub/sub 이벤트
  - WebSocket 브로드캐스트용

장점:

- 빠른 전달
- 연결 상태 추적

주의:

- 영구 저장소가 아닙니다.

### 3. `data/logs/games/<game_id>.jsonl`

ML 재학습/분석용 raw transition 로그입니다.

생성 코드:

- `backend/app/services/ml_logger.py`

저장되는 값:

- `timestamp`
- `game_id`
- `actor_id`
- `state_before`
- `action`
- `reward`
- `done`
- `state_after`
- `info`
- 선택적으로 `action_mask_before`, `phase_id_before`, `current_player_idx_before`, `model_info`

성격:

- 기계가 읽기 좋은 원본 로그
- offline RL, lineage 분석, state diff에 적합

### 4. `data/logs/replay/<game_id>.json`

사람이 확인하기 좋은 replay 로그입니다.

생성 코드:

- `backend/app/services/replay_logger.py`

형식은 `PuCo_RL/logs/replay/*.json` 스타일을 최대한 따라가되, backend 런타임 정보에 맞게 확장했습니다.

저장되는 값:

- top-level 메타
  - `game_id`, `title`, `status`, `players`, `model_versions`, `initial_state_summary`
- `entries`
  - `step`, `round`, `player`, `actor_id`, `actor_name`
  - `phase`, `phase_id`
  - `action_id`, `action`
  - `value_estimate`, `top_actions`, `commentary`
  - `reward`, `done`
  - `valid_action_count`
  - `state_summary_before`, `state_summary_after`
  - 필요 시 `model_info`, `role_selected`
- 게임 종료 시
  - `final_scores`
  - `result_summary`

성격:

- 사람이 따라 읽기 쉬움
- `PuCo_RL` replay처럼 `entries`를 순서대로 따라가며 읽기 좋음
- "누가, 언제, 어떤 phase에서, 무슨 행동을 했는지" 확인하기 좋음

## 게임 로그를 명확하게 보는 방법

### PostgreSQL에서 최근 액션 보기

```bash
docker compose exec db psql -U "${POSTGRES_USER:-puco_user}" -d puco_rl -c "
SELECT game_id, round, step, actor_id, action_data, state_summary
FROM game_logs
ORDER BY id DESC
LIMIT 30;
"
```

### JSONL raw 로그 보기

```bash
python - <<'PY'
import json
path = 'data/logs/games/YOUR_GAME_ID.jsonl'
with open(path, 'r', encoding='utf-8') as f:
    for _ in range(3):
        print(json.dumps(json.loads(next(f)), ensure_ascii=False, indent=2))
PY
```

이 로그는 상태 전체가 들어 있어서 가장 자세하지만 길 수 있습니다.

### replay JSON 보기

```bash
python - <<'PY'
import json
path = 'data/logs/replay/YOUR_GAME_ID.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)
print(json.dumps({
    'game_id': data['game_id'],
    'status': data['status'],
    'players': data['players'],
    'last_entries': data['entries'][-5:],
    'final_scores': data.get('final_scores', []),
}, ensure_ascii=False, indent=2))
PY
```

이 파일이 사람이 직접 확인하기엔 가장 편합니다.

특히 최근 몇 수를 빠르게 읽고 싶다면:

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

## `vis/`와 함께 보는 방법

`vis/`는 `game_logs` + `JSONL`을 읽어 Markdown 리포트를 만듭니다.

예시:

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

## 저장 방식별 추천 용도

- 운영 이슈 추적:
  - PostgreSQL `game_logs`
- 실시간 연결/전달 확인:
  - Redis
- 모델 재학습/데이터 계보:
  - `data/logs/games/*.jsonl`
- 사람이 게임 내용을 읽고 검수:
  - `data/logs/replay/*.json`

## 주의할 점

- `data/logs/games/` 아래에는 과거 테스트가 남긴 샘플 JSONL이 섞일 수 있습니다.
- 현재 `backend/tests/test_ml_logger.py`는 임시 디렉터리로 격리되어, 앞으로는 실제 로그 폴더를 오염시키지 않도록 수정했습니다.
- 실제 운영 데이터를 볼 때는 `data/logs/replay/<game_id>.json` 또는 PostgreSQL `game_logs`를 같이 대조하는 것을 권장합니다.
