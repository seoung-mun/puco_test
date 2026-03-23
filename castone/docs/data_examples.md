# PuCo 데이터 예시 (Data Examples)

> 이 문서는 각 상황별로 실제로 저장되는 데이터의 구체적인 예시를 보여줍니다.
> 데이터 명세는 `data_scheme.md`를 참고하세요.

---

## 시나리오 1: 게임 방 생성 (WAITING)

**상황:** Alice가 3인 게임 방을 만들었고, 아직 시작 전입니다.

### PostgreSQL `games` 레코드

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "title": "Alice의 전략 게임",
  "status": "WAITING",
  "num_players": 3,
  "players": [],
  "model_versions": {},
  "winner_id": null,
  "created_at": "2026-03-22T14:00:00+09:00",
  "updated_at": "2026-03-22T14:00:00+09:00"
}
```

### Redis 데이터 (없음)
Redis 키는 `start_game` 호출 시점에 생성됩니다.

---

## 시나리오 2: 게임 시작 (1인간 + 2봇, 1v2 모드)

**상황:** Alice(인간)와 BOT 2명으로 3인 게임이 시작되었습니다.

### PostgreSQL `games` 업데이트

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "PROGRESS",
  "players": [
    "550e8400-e29b-41d4-a716-446655440000",
    "BOT_PPO_1",
    "BOT_PPO_2"
  ],
  "model_versions": {
    "1": "ppo_agent_update_100.pth",
    "2": "ppo_agent_update_100.pth"
  },
  "updated_at": "2026-03-22T14:01:00+09:00"
}
```

### Redis `game:a1b2c3d4...:state` (STRING, TTL=900초)

```json
{
  "meta": {
    "round": 1,
    "num_players": 3,
    "player_order": ["player_0", "player_1", "player_2"],
    "governor": "player_0",
    "phase": "role_selection",
    "active_role": null,
    "active_player": "player_0",
    "end_game_triggered": false,
    "vp_supply_remaining": 75,
    "bot_thinking": false
  },
  "common_board": {
    "roles": {
      "settler": {"doubloons_on_role": 0, "taken_by": null},
      "mayor": {"doubloons_on_role": 0, "taken_by": null},
      "builder": {"doubloons_on_role": 0, "taken_by": null},
      "craftsman": {"doubloons_on_role": 0, "taken_by": null},
      "trader": {"doubloons_on_role": 0, "taken_by": null},
      "captain": {"doubloons_on_role": 0, "taken_by": null},
      "prospector": {"doubloons_on_role": 0, "taken_by": null}
    },
    "colonists": {"ship": 3, "supply": 45},
    "trading_house": {
      "goods": [],
      "d_spaces_used": 0,
      "d_spaces_remaining": 4,
      "d_is_full": false
    },
    "cargo_ships": [
      {"capacity": 4, "good": null, "d_filled": 0, "d_is_full": false},
      {"capacity": 5, "good": null, "d_filled": 0, "d_is_full": false},
      {"capacity": 6, "good": null, "d_filled": 0, "d_is_full": false}
    ],
    "available_plantations": {
      "face_up": ["corn", "indigo", "sugar", "tobacco", "coffee"],
      "draw_pile": {"corn": 8, "indigo": 10, "sugar": 10, "tobacco": 8, "coffee": 7}
    },
    "available_buildings": {
      "small_indigo_plant": {"cost": 1, "vp": 1, "max_colonists": 1, "copies_remaining": 2},
      "small_sugar_mill": {"cost": 2, "vp": 1, "max_colonists": 1, "copies_remaining": 2}
    },
    "goods_supply": {"corn": 10, "indigo": 11, "sugar": 11, "tobacco": 9, "coffee": 9}
  },
  "players": {
    "player_0": {
      "display_name": "Alice",
      "display_number": 1,
      "is_governor": true,
      "doubloons": 3,
      "vp_chips": 0,
      "goods": {"corn": 0, "indigo": 0, "sugar": 0, "tobacco": 0, "coffee": 0, "d_total": 0},
      "island": {
        "total_spaces": 12,
        "d_used_spaces": 1,
        "plantations": [{"type": "indigo", "colonized": false}]
      },
      "city": {
        "buildings": [],
        "colonists_unplaced": 0
      },
      "production": {
        "corn": {"can_produce": false, "amount": 0},
        "indigo": {"can_produce": false, "amount": 0}
      }
    },
    "player_1": {
      "display_name": "BOT_PPO_1",
      "display_number": 2,
      "is_governor": false,
      "doubloons": 3,
      "vp_chips": 0
    },
    "player_2": {
      "display_name": "BOT_PPO_2",
      "display_number": 3,
      "is_governor": false,
      "doubloons": 4,
      "vp_chips": 0
    }
  },
  "decision": {
    "type": "role_selection",
    "player": "player_0",
    "note": ""
  },
  "bot_players": {"player_1": "ppo", "player_2": "ppo"}
}
```

### Redis `game:a1b2c3d4...:meta` (HASH, TTL=900초)

```
status      → "PROGRESS"
human_count → "1"
num_players → "3"
```

### Redis `game:a1b2c3d4...:players` (HASH, TTL=900초)

```
550e8400-e29b-41d4-a716-446655440000 → "connected"
```

---

## 시나리오 3: 액션 수행 — 개척자(Settler) 역할 선택

**상황:** Alice(player_0)가 역할 선택 단계에서 개척자(action_index=0)를 선택했습니다.

### PostgreSQL `game_logs` 신규 레코드

```json
{
  "id": 1,
  "game_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "round": 1,
  "step": 0,
  "actor_id": "player_0",
  "action_data": {
    "action": 0
  },
  "available_options": [1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
  "state_before": {
    "meta": {
      "round": 1,
      "phase": "role_selection",
      "active_player": "player_0",
      "active_role": null
    },
    "players": {
      "player_0": {"doubloons": 3, "island": {"plantations": [{"type": "indigo", "colonized": false}]}}
    }
  },
  "state_after": {
    "meta": {
      "round": 1,
      "phase": "settler_action",
      "active_player": "player_0",
      "active_role": "settler"
    },
    "common_board": {
      "available_plantations": {
        "face_up": ["corn", "indigo", "sugar", "tobacco", "coffee"],
        "quarry_accessible": true
      }
    },
    "players": {
      "player_0": {"doubloons": 3}
    }
  },
  "timestamp": "2026-03-22T14:01:30+09:00"
}
```

### JSONL 파일 (`/data/logs/transitions_2026-03-22.jsonl`) 신규 라인

```json
{"game_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "actor_id": "player_0", "state_before": {"meta": {"round": 1, "phase": "role_selection", "active_player": "player_0"}}, "action": 0, "reward": 0.0, "done": false, "state_after": {"meta": {"round": 1, "phase": "settler_action", "active_player": "player_0"}}, "info": {"round": 1, "step": 0}}
```

---

## 시나리오 4: 개척자 단계 — 채석장 선택

**상황:** Alice가 개척자 역할 수행 중, 채석장(quarry)을 자신의 섬에 추가했습니다.

### PostgreSQL `game_logs` 신규 레코드 (round=1, step=1)

```json
{
  "id": 2,
  "game_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "round": 1,
  "step": 1,
  "actor_id": "player_0",
  "action_data": {
    "action": 12
  },
  "available_options": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0],
  "state_before": {
    "meta": {"round": 1, "phase": "settler_action", "active_player": "player_0"},
    "players": {
      "player_0": {
        "island": {
          "plantations": [{"type": "indigo", "colonized": false}],
          "d_used_spaces": 1
        }
      }
    }
  },
  "state_after": {
    "meta": {"round": 1, "phase": "settler_action", "active_player": "player_1"},
    "players": {
      "player_0": {
        "island": {
          "plantations": [
            {"type": "indigo", "colonized": false},
            {"type": "quarry", "colonized": false}
          ],
          "d_used_spaces": 2,
          "d_active_quarries": 0
        }
      }
    }
  },
  "timestamp": "2026-03-22T14:01:45+09:00"
}
```

---

## 시나리오 5: 플레이어 이탈 (2인간 게임, 2v1 모드)

**상황:** Bob이 연결을 끊었고, Alice에게 종료 여부를 물어봐야 합니다.

### Redis `game:{id}:players` 업데이트

```
alice_uuid → "connected"
bob_uuid   → "disconnected"     ← 이탈 감지 후 업데이트
```

### WebSocket 브로드캐스트 (Alice에게 전송)

```json
{
  "type": "PLAYER_DISCONNECTED",
  "player_id": "bob_uuid",
  "message": "Player bob_uuid has disconnected.",
  "options": ["end_game", "wait"],
  "timeout_seconds": 600
}
```

### asyncio 타이머 시작
```
_disconnect_timers["{game_id}:bob_uuid"] = asyncio.Task(_disconnect_timeout, sleep=600s)
```

---

## 시나리오 6: 즉시 게임 종료 (Alice가 "end_game" 선택)

**상황:** Alice가 `END_GAME_REQUEST`를 서버에 전송했습니다.

### WebSocket 수신 메시지 (클라이언트 → 서버)

```json
{
  "type": "END_GAME_REQUEST"
}
```

### 처리 결과

**PostgreSQL `games` 업데이트:**
```json
{
  "status": "FINISHED",
  "winner_id": null,
  "updated_at": "2026-03-22T14:15:00+09:00"
}
```

**asyncio 타이머 취소:**
```
_disconnect_timers["{game_id}:bob_uuid"].cancel()
```

**WebSocket 브로드캐스트 (모든 클라이언트에게):**
```json
{
  "type": "GAME_ENDED",
  "reason": "player_request",
  "requested_by": "alice_uuid"
}
```

**Redis TTL 단축:**
```
game:{id}:state → EX 300 (5분으로 단축)
game:{id}:meta  → status: "FINISHED", EX 300
```

---

## 시나리오 7: 타임아웃으로 자동 게임 종료

**상황:** Bob이 이탈한 후 10분이 지났고, Alice가 아무것도 선택하지 않았습니다.

### 처리 결과

**PostgreSQL `games` 업데이트:**
```json
{
  "status": "FINISHED",
  "winner_id": null,
  "updated_at": "2026-03-22T14:25:00+09:00"
}
```

**WebSocket 브로드캐스트:**
```json
{
  "type": "GAME_ENDED",
  "reason": "player_disconnect_timeout",
  "disconnected_player": "bob_uuid"
}
```

---

## 시나리오 8: 게임 정상 종료 (VP 바닥)

**상황:** VP 칩이 모두 소진되어 게임이 종료되었습니다.

### PostgreSQL `games` 최종 상태

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "FINISHED",
  "winner_id": "550e8400-e29b-41d4-a716-446655440000",
  "updated_at": "2026-03-22T14:45:00+09:00"
}
```

### PostgreSQL `users` 업데이트 (Alice)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "total_games": 1,
  "win_rate": 1.0
}
```

### 마지막 `game_logs` 레코드 예시 (done=true)

```json
{
  "id": 157,
  "game_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "round": 12,
  "step": 8,
  "actor_id": "player_2",
  "action_data": {"action": 45},
  "available_options": [0, 0, ..., 1, 0],
  "state_before": {
    "meta": {
      "round": 12,
      "vp_supply_remaining": 1,
      "end_game_triggered": true
    }
  },
  "state_after": {
    "meta": {
      "round": 12,
      "vp_supply_remaining": 0,
      "end_game_triggered": true
    }
  },
  "timestamp": "2026-03-22T14:44:58+09:00"
}
```

### JSONL 마지막 라인 (done=true)

```json
{"game_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890", "actor_id": "player_2", "state_before": {"meta": {"vp_supply_remaining": 1}}, "action": 45, "reward": 38.0, "done": true, "state_after": {"meta": {"vp_supply_remaining": 0}}, "info": {"round": 12, "step": 8}}
```

---

## 시나리오 9: /health 응답 예시

### 정상 상태
```json
GET /health → 200 OK

{
  "status": "ok",
  "checks": {
    "postgresql": "ok",
    "redis": "ok"
  }
}
```

### PostgreSQL 다운
```json
GET /health → 503 Service Unavailable

{
  "status": "degraded",
  "checks": {
    "postgresql": "error: (psycopg2.OperationalError) connection refused",
    "redis": "ok"
  }
}
```

### Redis 다운
```json
GET /health → 503 Service Unavailable

{
  "status": "degraded",
  "checks": {
    "postgresql": "ok",
    "redis": "error: Connection refused"
  }
}
```

---

## 데이터 볼륨 추정

| 항목 | 값 |
|------|-----|
| 게임당 평균 스텝 수 | ~150 스텝 |
| `game_logs` 레코드당 평균 크기 | ~5~15 KB (state JSON 포함) |
| 게임 1회분 DB 용량 | ~1~2 MB |
| 월 100게임 기준 | ~100~200 MB |
| `game:*:state` Redis 키 최대 크기 | ~15 KB |
| 동시 최대 게임 수 (소규모 서비스) | 10~20개 |
| Redis 최대 메모리 사용 (게임 상태) | ~300 KB (TTL로 자동 정리) |
