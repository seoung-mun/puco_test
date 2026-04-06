# vis/db

이 문서는 사람이 직접 DB와 로컬 로그를 열어 보면서 "모델이 어떤 상태를 보고 어떤 액션을 냈는지"를 확인하는 절차를 정리한 것이다.

## 1. 먼저 확인할 것

Castone의 주요 데이터 소스는 현재 다섯 가지다.

1. `games`
   - 방/게임 메타데이터
   - `players`, `model_versions`
2. `game_logs`
   - 액션 단위 DB 감사 로그
   - `action_data`, `state_before`, `state_after`, `state_summary`
3. `data/logs/games/<game_id>.jsonl`
   - ML/분석용 transition 로그
   - `action_mask_before`, `phase_id_before`, `model_info`가 있으면 행동 분석이 쉬워짐
4. `data/logs/replay/<game_id>.json`
   - 사람 친화적인 replay 로그
   - `format=backend-replay.v1`, `entries`, `final_scores`, `result_summary`
5. Redis
   - 실시간 전파
   - 원본 감사 저장소가 아님

## 2. 가장 빠른 확인 루트

### A. JSONL만 빠르게 보기

```bash
sed -n '1,5p' data/logs/games/YOUR_GAME_ID.jsonl
```

특정 게임만 찾기:

```bash
rg '"game_id": "YOUR_GAME_ID"' data/logs/games/*.jsonl
```

### B. 자동 리포트 만들기

```bash
python vis/render_lineage_report.py \
  --jsonl data/logs/games/YOUR_GAME_ID.jsonl \
  --output vis/output/lineage.md
```

```bash
python vis/render_behavior_report.py \
  --jsonl data/logs/games/YOUR_GAME_ID.jsonl \
  --output vis/output/behavior.md
```

```bash
python vis/render_storage_report.py \
  --game-id YOUR_GAME_ID \
  --output vis/output/storage.md
```

## 3. PostgreSQL에서 직접 보기

`DATABASE_URL`이 설정되어 있다고 가정한다.

최근 게임 목록:

```sql
SELECT
  id,
  title,
  status,
  players,
  model_versions,
  created_at
FROM games
ORDER BY created_at DESC
LIMIT 10;
```

한 게임의 액션 로그:

```sql
SELECT
  id,
  game_id,
  round,
  step,
  actor_id,
  action_data,
  state_summary,
  timestamp
FROM game_logs
WHERE game_id = 'YOUR_GAME_ID'
ORDER BY step, id;
```

모델 provenance가 남는지 확인:

```sql
SELECT
  step,
  actor_id,
  action_data->'model_info' AS model_info
FROM game_logs
WHERE game_id = 'YOUR_GAME_ID'
ORDER BY step, id;
```

`state_summary`로 사람 친화적으로 보기:

```sql
SELECT
  step,
  state_summary->>'phase' AS phase,
  state_summary->>'current_player' AS current_player,
  state_summary->'players' AS players
FROM game_logs
WHERE game_id = 'YOUR_GAME_ID'
ORDER BY step, id;
```

## 4. SQLite에서 직접 보기

테스트 DB를 로컬에서 보는 경우:

```bash
sqlite3 path/to/file.db
```

테이블 확인:

```sql
.tables
```

게임 목록:

```sql
SELECT id, title, status, players, model_versions
FROM games
ORDER BY created_at DESC;
```

액션 로그:

```sql
SELECT id, round, step, actor_id, action_data, state_summary
FROM game_logs
WHERE game_id = 'YOUR_GAME_ID'
ORDER BY step, id;
```

## 5. 사람이 행동을 읽는 순서

권장 순서는 아래와 같다.

1. `games.model_versions`
   - 어떤 bot_type / artifact가 붙었는지 먼저 본다.
2. `game_logs.action_data.model_info`
   - 실제 액션 로그에 provenance가 붙었는지 확인한다.
3. `games/<game_id>.jsonl`
   - `phase_id_before`, `action_mask_before`, `action`, `model_info`를 본다.
4. `replay/<game_id>.json`
   - `entries[].action`, `commentary`, `final_scores`, `result_summary`를 본다.
5. `state_before` / `state_after`
   - 액션 직전/직후 상태가 이어지는지 본다.

참고:

- 예전 일간 파일 `transitions_YYYY-MM-DD.jsonl` 이 남아 있을 수 있다.
- 새 코드는 game 당 JSONL 하나를 쓰고, `vis/` 도구는 두 형식을 함께 읽는다.
- 기존 일간 파일을 새 구조로 쪼개려면 `python backend/scripts/migrate_transition_logs_to_per_game.py` 를 실행하면 된다.

## 6. 지금 바로 확인 가능한 질문

### 질문: DB와 JSONL row 수가 맞는가?

자동:

```bash
python vis/render_storage_report.py \
  --game-id YOUR_GAME_ID \
  --output vis/output/storage.md
```

이 리포트는 이제 replay JSON의 `format`, `entries`, `total_steps`도 함께 확인한다.

### 질문: 봇이 어떤 모델로 행동했는가?

자동:

```bash
python vis/render_behavior_report.py \
  --game-id YOUR_GAME_ID \
  --output vis/output/behavior.md
```

### 질문: 데이터가 어디서 어디로 이동하는가?

자동:

```bash
python vis/render_lineage_report.py \
  --game-id YOUR_GAME_ID \
  --output vis/output/lineage.md
```

## 7. 현재 한계

현재는 아래 항목이 로그에 완전히 남지 않는다.

- 통합 `step_id`
- `state_hash`
- `game_seed`
- action probabilities
- inference latency

그래서 사람이 볼 때는 다음처럼 해석해야 한다.

- 현재 리포트는 "실제 남아 있는 증거"를 시각화한다.
- 아직 없는 값은 gap으로 표시한다.
- 재현성/확률 heatmap 같은 항목은 추가 instrumentation이 필요하다.
