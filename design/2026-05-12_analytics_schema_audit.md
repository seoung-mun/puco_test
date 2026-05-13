# Analytics Schema Audit — 2026-05-12

목적: dev compose DB에서 `games` / `users` 테이블의 실제 JSONB 구조를 확인하고,
Task B2 분석 쿼리 구현에 필요한 사전 정보를 수집한다.

---

## 환경

- DB 컨테이너: `puco_db` (postgres:16-alpine), `puco_rl` 데이터베이스
- 접속: `docker compose exec db psql -U puco_user puco_rl`
- 실행 시점 데이터: `games` 11건 (FINISHED), `users` 35건

---

## 1. 테이블 스키마

### `users`

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | uuid | PK |
| google_id | varchar | UNIQUE |
| nickname | varchar | UNIQUE |
| total_games | integer | default 0 |
| win_rate | float8 | default 0.0 |
| email | varchar | UNIQUE |
| created_at | timestamptz | |

### `games`

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | uuid | PK |
| title | varchar | |
| status | varchar | 'WAITING'/'IN_PROGRESS'/'FINISHED' |
| num_players | integer | |
| players | jsonb | 배열, default '[]' |
| model_versions | jsonb | 객체, default '{}' |
| winner_id | varchar | NULL 가능 |
| created_at | timestamptz | |
| updated_at | timestamptz | |
| is_private | boolean | |
| host_id | varchar | |
| game_seed | bigint | |
| governor_idx | integer | |
| engine_compat_version | integer | |
| state_revision | integer | |
| recovery_blocked_reason | varchar(64) | |

인덱스: `ix_games_status` (status), `ix_games_host_id` (host_id)

---

## 2. JSONB 구조 실측

### 2-1. `players` 배열 형식

```
-- 인간 포함 게임
["f3e7ce8a-cbb2-4fc7-99ce-cde6f73107f8", "BOT_ppo", "BOT_ppo"]

-- 봇 전용 게임
["BOT_ppo", "BOT_ppo", "BOT_ppo"]
["BOT_ppo", "BOT_ppo", "BOT_action_value"]
```

**확인 사항:**
- 인간 플레이어: UUID 문자열 (하이픈 포함 표준 UUID)
- 봇 플레이어: `"BOT_ppo"`, `"BOT_action_value"` 형식 (인덱스 없음, `"BOT_ppo_0"` 형식 아님)
- 동일 봇 타입이 여러 슬롯에 중복 등장 가능

### 2-2. `winner_id` 실측 값

| 케이스 | 실측 값 |
|---|---|
| 봇 승리 (PPO) | `"BOT_ppo"` |
| 봇 승리 (action_value) | `"BOT_action_value"` |
| 게임 미완료 / NULL | `NULL` |
| 인간 승리 | (실측 데이터 없음 — 현재 인간 참여 게임은 모두 winner_id NULL) |

**주의:** 인간 승리 시 winner_id는 UUID 문자열(`"f3e7ce8a-..."`)로 기록될 것으로 예상되나,
현재 DB에는 인간이 승리한 FINISHED 게임이 없음.

### 2-3. `model_versions` JSONB 키 구조

키는 `"player_0"`, `"player_1"`, `"player_2"` 형식 (0-indexed 슬롯 번호).
일부 최신 게임에는 `"__engine__"` 키가 추가됨.

**인간 슬롯 (`actor_type: "human"`):**
```json
{
  "player_0": {
    "player_id": "f3e7ce8a-cbb2-4fc7-99ce-cde6f73107f8",
    "actor_type": "human",
    "fingerprint": {
      "env": "puco-upstream/main@4949773|...",
      "action_space": "castone.action-space.slot-mayor.v1",
      "schema_version": "artifact-fingerprint.v1",
      "mayor_semantics": "castone.mayor.slot-direct.v1"
    }
  }
}
```

**봇 슬롯 (`actor_type: "bot"`):**
```json
{
  "player_1": {
    "family": "ppo",
    "obs_dim": 210,
    "bot_type": "ppo",
    "action_dim": 200,
    "actor_type": "bot",
    "policy_tag": "champion",
    "fingerprint": { ... },
    "num_players": 3,
    "architecture": "ppo_residual",
    "artifact_name": "PPO_PR_Server_hybrid_selfplay_curriculum_5billion_from_scratch_20260412_122638_step_481689600",
    "potential_mode": "option3",
    "metadata_source": "bootstrap_derived",
    "bootstrap_profile": "ppo_pr_server_v1",
    "checkpoint_filename": "PPO_PR_Server_hybrid_selfplay_curriculum_5billion_from_scratch_20260412_122638_step_481689600.pth"
  }
}
```

**`__engine__` 키 (최신 게임에만 존재):**
```json
{
  "__engine__": {
    "action_space": "e222b45e75da7815",
    "compat_version": 1,
    "mayor_semantics": "910324a0bc1cb6bd"
  }
}
```

---

## 3. JSONB `@>` 연산자 동작 검증

### 3-1. UUID 필터 (인간 플레이어 게임 조회)

```sql
SELECT COUNT(*)
FROM games
WHERE status = 'FINISHED'
  AND players @> '["f3e7ce8a-cbb2-4fc7-99ce-cde6f73107f8"]'::jsonb;
```

결과: `1` — 정상 동작.

### 3-2. 봇 타입 필터

```sql
SELECT
  COUNT(*) FILTER (WHERE players @> '["BOT_ppo"]'::jsonb) as has_bot_ppo,
  COUNT(*) FILTER (WHERE players @> '["BOT_action_value"]'::jsonb) as has_bot_action_value,
  COUNT(*) as total
FROM games
WHERE status = 'FINISHED';
```

결과:
```
 has_bot_ppo | has_bot_action_value | total
-------------+----------------------+-------
          11 |                    3 |    11
```

`@>` 연산자는 배열 원소 단일 일치 검색에 정상 동작. GIN 인덱스가 없더라도 seq scan으로 동작 확인됨.

> **B2 구현 시 고려**: `players` 컬럼에 GIN 인덱스 추가 권장 (사용자 수 증가 시 성능)
> ```sql
> CREATE INDEX CONCURRENTLY ix_games_players_gin ON games USING GIN (players);
> ```

---

## 4. 분석 쿼리 실행 결과

### Query 1: 사용자 목록 (total_games 내림차순)

```sql
SELECT id, nickname, total_games FROM users ORDER BY total_games DESC LIMIT 10;
```

결과:
```
                  id                  |  nickname   | total_games
--------------------------------------+-------------+-------------
 f3e7ce8a-cbb2-4fc7-99ce-cde6f73107f8 | test        |           0
 d6946b0f-011c-45a8-a36b-e51d2c3b8766 | SettlerDbg1 |           0
 fce6f1dd-2e2f-432d-b045-cce02a06bd1c | tester      |           0
 661e4121-d984-4647-95b4-bb5d3169d2c3 | SettlerDbg2 |           0
 2a321ed9-abae-4d70-ac62-e4f02324022c | loadtest1   |           0
 ...
```

**발견:** `total_games` 컬럼은 현재 모두 0. 게임 완료 시 업데이트되는 로직이 있는지 별도 확인 필요.

### Query 2: 특정 사용자의 게임 데이터 (JSONB 필터)

```sql
SELECT
  winner_id,
  players,
  model_versions
FROM games
WHERE status = 'FINISHED'
  AND players @> '["f3e7ce8a-cbb2-4fc7-99ce-cde6f73107f8"]'::jsonb
LIMIT 5;
```

결과: 1행 반환, `winner_id = NULL` (해당 게임 인간 승리 아님).
`players @>` UUID 필터 정상 동작 확인.

### Query 3: 시간순 판수별 승률 (특정 사용자)

```sql
SELECT id, winner_id, created_at
FROM games
WHERE status = 'FINISHED'
  AND players @> '["f3e7ce8a-cbb2-4fc7-99ce-cde6f73107f8"]'::jsonb
ORDER BY created_at
LIMIT 10;
```

결과:
```
                  id                  | winner_id |          created_at
--------------------------------------+-----------+-------------------------------
 8e81749e-f66c-4af4-b7ea-6dc1daab7d1a |           | 2026-04-13 07:04:10.967406+00
```

현재 `test` 유저 참여 FINISHED 게임 1건. 시간순 정렬 및 필터 동작 정상.

### Query 4: JSONB 구조 확인 (최근 3건)

```sql
SELECT id, players, winner_id, model_versions
FROM games
WHERE status = 'FINISHED'
LIMIT 3;
```

결과: 3건 반환, JSONB 구조 2-1~2-3항 그대로 확인됨.

### Query 5: 사용자별 승패 집계 (B2 핵심 쿼리)

```sql
SELECT
  u.nickname,
  u.id as user_id,
  COUNT(g.id) as total_games,
  COUNT(g.id) FILTER (WHERE g.winner_id = u.id::text) as wins,
  COUNT(g.id) FILTER (WHERE g.winner_id IS NOT NULL AND g.winner_id != u.id::text) as losses
FROM users u
JOIN games g ON g.players @> to_jsonb(u.id::text)
WHERE g.status = 'FINISHED'
GROUP BY u.id, u.nickname
ORDER BY total_games DESC;
```

결과:
```
 nickname |               user_id                | total_games | wins | losses
----------+--------------------------------------+-------------+------+--------
 tester   | fce6f1dd-2e2f-432d-b045-cce02a06bd1c |           2 |    0 |      0
 test     | f3e7ce8a-cbb2-4fc7-99ce-cde6f73107f8 |           1 |    0 |      0
```

`to_jsonb(u.id::text)` 형식으로 UUID를 JSONB 단일 값으로 변환하여 `@>` 필터 정상 동작.
인간 플레이어가 참여한 FINISHED 게임에서 현재 인간 승리 없음(모두 NULL).

---

## 5. B2 구현 시 참고사항

### 5-1. winner_id 해석 규칙

| winner_id 값 | 의미 |
|---|---|
| `NULL` | 게임 미완료 또는 winner 미기록 |
| `"BOT_ppo"` | PPO 봇 승리 |
| `"BOT_action_value"` | action_value 봇 승리 |
| UUID 문자열 | 인간 플레이어 승리 (해당 UUID 보유자) |

### 5-2. players 배열에서 인간 참여 여부 판별

```sql
-- 인간 참여 게임 필터
WHERE players @> to_jsonb(user_id::text)

-- 봇 전용 게임 필터 (인간 없는 게임)
WHERE NOT EXISTS (
  SELECT 1 FROM jsonb_array_elements_text(players) elem
  WHERE elem NOT LIKE 'BOT_%'
)
```

### 5-3. model_versions에서 슬롯별 봇 타입 추출

```sql
-- player_0의 bot_type 추출
model_versions->'player_0'->>'bot_type'

-- player_0의 actor_type (human/bot 구분)
model_versions->'player_0'->>'actor_type'

-- 각 플레이어 슬롯의 player_id (인간 슬롯만)
model_versions->'player_0'->>'player_id'
```

### 5-4. 인간 승리 케이스에서 winner_id 비교

```sql
-- 사용자 UUID가 winner_id인 경우 (인간 승리)
WHERE winner_id = user_id::text

-- 봇이 이긴 경우
WHERE winner_id LIKE 'BOT_%'
```

### 5-5. GIN 인덱스 없음 (현재)

현재 `players` 컬럼에 GIN 인덱스 없음. 데이터 규모 소량이므로 seq scan으로 동작 가능.
사용자 수 증가 시 추가 권장:
```sql
CREATE INDEX CONCURRENTLY ix_games_players_gin ON games USING GIN (players);
```

---

## 6. 요약

| 확인 항목 | 결과 |
|---|---|
| players 배열 원소 형식 | UUID 문자열 or `"BOT_ppo"` / `"BOT_action_value"` (인덱스 없음) |
| winner_id 인간 케이스 | UUID 문자열 예상 (현재 실측 데이터 없음) |
| winner_id 봇 케이스 | `"BOT_ppo"`, `"BOT_action_value"` 확인 |
| winner_id NULL 케이스 | 6건 / 11건 (NULL, 미기록) |
| model_versions 키 구조 | `"player_0"`, `"player_1"`, `"player_2"` (일부 `"__engine__"`) |
| JSONB `@>` 연산자 | UUID 및 봇 문자열 필터 모두 정상 동작 |
| 분석 쿼리 4종 | 모두 실행 성공, 결과 정합성 확인 |
