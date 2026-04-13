# Replay 로그 시스템 재설계

> 날짜: 2026-04-09  
> 상태: Draft  
> 범위: 리플레이 로그 v2 구조 확정 + 선택적 저장 + MLLogger 비활성화

---

## 1. 배경 및 동기

### 현재 3중 로깅 시스템

| # | 로거 | 저장 위치 | 포맷 | 용도 |
|---|------|----------|------|------|
| 1 | DB `GameLog` | PostgreSQL `game_logs` 테이블 | JSONB | 웹에서 사람이 게임 로그 열람 (현재 미사용) |
| 2 | `MLLogger` | `data/logs/games/{game_id}.jsonl` | JSONL (S,A,R,Done,S') | 오프라인 RL 학습용 |
| 3 | `ReplayLogger` | `data/logs/replay/{game_id}.json` | JSON (commentary 포함) | 리플레이 시각화용 |

### 문제점

1. **DB GameLog**: 사람이 웹에서 게임 로그를 볼 일이 없다. DB 부하만 증가.
2. **MLLogger**: 현재 학습 스크립트(`train_ppo_selfplay_server.py`)는 **온라인 PPO**로 환경을 직접 구동하므로 로그 파일을 사용하지 않음. PPO에 필수인 `log_prob`, `value_estimate`도 미저장.
3. **ReplayLogger**: 모든 게임에 대해 무조건 저장됨. `state_summary_before/after`는 요약 데이터로 **시각적 보드 재현 불가** (타일 순서, 일꾼 배치, 화물선/trading house 상태 누락).

### 목표

- **단기**: 리플레이 로그를 보드 재현 가능한 스냅샷 기반으로 확장하고, 선택적 저장으로 전환
- **단기**: MLLogger 비활성화 (불필요한 I/O 제거)
- **중기**: DB GameLog 제거 (리플레이 로그 확정 후)
- **장기**: 오프라인 RL 학습 파이프라인 (MLLogger 재설계 시)

---

## 2. 설계 결정 (Decision Log)

### D1. 리플레이 재현 방식: 스냅샷 리플레이

- **결정**: 매 턴 상태 스냅샷을 로그에 저장. 프론트엔드가 로그만으로 보드 렌더링.
- **대안 검토**:
  - (A) 이벤트 리플레이 (action 시퀀스만 저장, 서버에서 엔진 재실행) — 서버 연산 부담, 엔진 버전 호환 문제
  - (B) 스냅샷 리플레이 — 파일 크기 증가하나 서버 연산 없이 재생 가능 ✅
- **이유**: 서버 부담 없이 프론트엔드 단독 재생 가능. 엔진 업데이트에도 기존 리플레이 호환 유지.

### D2. 스냅샷 포맷: 프론트엔드 `GameState` 호환

- **결정**: 리플레이 스냅샷을 `serialize_game_state_from_engine`이 생성하는 **rich `GameState`** 형식으로 저장.
- **대안 검토**:
  - (A) raw engine observation dict — 프론트에서 별도 변환 필요, 파서 이중 관리
  - (B) rich `GameState` 호환 — 기존 `GameScreen`, `IslandGrid`, `CityGrid` 등 컴포넌트 **재사용 가능** ✅
  - (C) 하이브리드 (summary + 필수 필드 추가) — 중간이지만 결국 GameState와 동기화 부담
- **이유**: 프론트엔드가 이미 `GameState` 기준으로 렌더링함. 동일 포맷을 쓰면 리플레이 뷰어에서 기존 게임 컴포넌트를 그대로 마운트 가능.

### D3. 보드 재현 데이터 전략

| 데이터 | 현재 replay | v2 replay | 재현 방법 |
|--------|------------|-----------|----------|
| 섬 타일 위치 (12칸) | ❌ 개수만 | ✅ ordered array | `GameState.players[x].island.plantations[]` — `IslandGrid`가 배열 순서대로 그리드 배치 |
| 건물 슬롯 위치 (12칸) | ❌ 이름만 | ✅ ordered array | `GameState.players[x].city.buildings[]` — `CityGrid.buildColumnLayout`이 순서대로 배치 |
| 일꾼 배치 | ❌ unplaced만 | ✅ `colonized`/`current_colonists` | 각 plantation의 `colonized`, building의 `current_colonists` 필드 |
| Mayor 전략 | ⚠️ action_id만 | ✅ `action_id` + 전략명 | `action_id` 69-71 → "Captain Focus" / "Trade/Factory Focus" / "Building Focus" |
| 화물선 상태 | ❌ 없음 | ✅ `common_board.cargo_ships[]` | capacity, good, filled, remaining_space |
| Trading house | ❌ 없음 | ✅ `common_board.trading_house` | goods[], spaces_used/remaining, is_full |
| 역할 보드 | ❌ 없음 | ✅ `common_board.roles` | 각 역할의 doubloons, taken_by |
| 공급 자원 | ❌ 없음 | ✅ `common_board.goods_supply` | corn/indigo/sugar/tobacco/coffee 수량 |

### D4. 선택적 저장

- **결정**: `GameSession` 모델에 `save_replay` boolean 컬럼 추가. 대기방 생성 / 봇전 생성 시 UI 토글로 제어.
- **대안 검토**:
  - (A) 모든 게임 저장 (현재 방식) — 저장 비용 과다
  - (B) 특정 게임만 선택적 저장 ✅
- **이유**: 대부분의 게임은 리플레이가 불필요. 사용자가 명시적으로 선택한 게임만 저장하면 디스크 사용량 대폭 감소.

### D5. MLLogger 비활성화

- **결정**: feature flag 방식으로 비활성화 (코드 삭제 아님).
- **대안 검토**:
  - (A) 코드 완전 삭제 — 향후 오프라인 RL 파이프라인 구축 시 재작성 필요
  - (B) feature flag로 no-op ✅ — 기존 코드 유지, 필요 시 재활성화
- **이유**: 향후 `log_prob`, `value_estimate` 추가 등 MLLogger 확장 가능성 보존.

### D6. DB GameLog 유지 (이번 범위 아님)

- **결정**: 리플레이 로그 v2 확정 후 별도 작업으로 제거.
- **이유**: 리플레이 시스템이 안정적으로 동작하는 것을 확인한 뒤 안전하게 제거.

---

## 3. Replay v2 페이로드 구조

### 3.1 파일 구조

```
data/logs/replay/{game_id}.json
```

### 3.2 전체 페이로드

```jsonc
{
  "format": "backend-replay.v2",        // v1 → v2 버전 범프
  "game_id": "uuid",
  "title": "방 제목",
  "status": "FINISHED",
  "host_id": "user-uuid",
  "num_players": 3,
  "players": [
    {
      "player_id": "uuid-or-BOT_xxx",
      "display_name": "Player1",
      "is_bot": false,
      "bot_type": null
    }
  ],
  "model_versions": { ... },
  "parity": { ... },
  "created_at": "2026-04-09T12:00:00Z",
  "updated_at": "2026-04-09T12:30:00Z",

  // ── v2 신규 ──
  "initial_snapshot": { /* GameState */ },   // 게임 시작 직후 전체 상태

  "total_steps": 150,
  "entries": [
    {
      "step": 1,
      "round": 1,
      "player": 0,
      "actor_id": "uuid",
      "actor_name": "Player1",
      "phase": "ROLE_SELECTION",
      "phase_id": 8,
      "action_id": 3,
      "action": "Select Role: Builder",
      "reward": 0.0,
      "done": false,
      "commentary": "Doubloons +1 | Phase ROLE_SELECTION -> BUILDER",

      // ── v2 변경: summary → snapshot ──
      "snapshot_after": { /* GameState */ }   // action 수행 후 전체 상태
    }
  ],
  "final_scores": [ ... ],
  "result_summary": { ... }
}
```

### 3.3 v1 → v2 변경사항

| 필드 | v1 | v2 | 비고 |
|------|----|----|------|
| `format` | `"backend-replay.v1"` | `"backend-replay.v2"` | 버전 식별 |
| `initial_snapshot` | 없음 (`initial_state_summary`만) | `GameState` 전체 | 게임 시작 상태 보드 렌더링용 |
| `entries[].state_summary_before` | 요약 dict | **삭제** | `snapshot_after`로 대체 (이전 턴의 `snapshot_after` = 현재 턴의 before) |
| `entries[].state_summary_after` | 요약 dict | **삭제** | `snapshot_after`로 대체 |
| `entries[].snapshot_after` | 없음 | `GameState` 전체 | action 수행 후 보드 상태 |
| `entries[].value_estimate` | null | 삭제 | v2에서 불필요 |
| `entries[].top_actions` | [] | 삭제 | v2에서 불필요 |
| `entries[].valid_action_count` | 숫자 | 유지 | 리플레이 정보 표시용 |
| `entries[].model_info` | optional | 유지 | 봇 모델 정보 |

### 3.4 스냅샷 최적화: `snapshot_after`만 저장하는 이유

- `initial_snapshot`이 step 0의 `before` 역할
- entry N의 `snapshot_after`가 entry N+1의 `before` 역할
- 따라서 `before`/`after` 둘 다 저장할 필요 없음 → **파일 크기 ~50% 절감**

### 3.5 `GameState` 스냅샷에서 제외할 필드

리플레이에 불필요한 라이브 게임 전용 필드:

```python
REPLAY_EXCLUDE_KEYS = [
    "action_mask",         # 리플레이 시 action 선택 불필요
    "bot_thinking",        # UI 상태
    "history",             # 별도 entries로 대체
]
```

### 3.6 예상 파일 크기

| 항목 | v1 (현재) | v2 (예상) |
|------|----------|----------|
| entry 1개 (summary) | ~1.5 KB | — |
| entry 1개 (snapshot) | — | ~4-5 KB |
| 150턴 게임 | ~250 KB | ~700 KB |
| 메타 + initial | ~2 KB | ~7 KB |
| **총 파일 크기** | **~250 KB** | **~700 KB** |

선택적 저장이므로 전체 디스크 사용량은 오히려 감소할 것으로 예상.

---

## 4. 데이터 흐름

### 4.1 게임 시작 시 (ReplayLogger.initialize_game)

```
GameService.start_game()
  ├─ engine = create_game_engine(...)
  ├─ rich_state = build_rich_state(db, game_id, engine, room)
  │
  ├─ [현재] ReplayLogger.initialize_game(initial_state_summary=summarize(...))
  │
  └─ [v2] if room.save_replay:
         ReplayLogger.initialize_game(initial_snapshot=rich_state)
```

### 4.2 매 액션 시 (ReplayLogger.append_entry)

```
GameService.process_action()
  ├─ result = engine.step(action)
  ├─ rich_state = build_rich_state(db, game_id, engine, room)   # ← 이미 생성됨
  │
  ├─ [현재] ReplayLogger.append_entry(entry=build_replay_entry(...))
  │         └─ entry에 state_summary_before/after 포함
  │
  └─ [v2] if room.save_replay:
         replay_entry = build_replay_entry_v2(
             ...,
             snapshot_after=strip_replay_excluded(rich_state),
         )
         ReplayLogger.append_entry(entry=replay_entry)
```

### 4.3 핵심 포인트

- `rich_state`는 이미 WebSocket 브로드캐스트를 위해 **매 턴 생성됨** → 추가 직렬화 비용 없음
- ReplayLogger에 전달할 때 `copy.deepcopy` 후 불필요 필드 제거

### 4.4 MLLogger 비활성화

```python
# ml_logger.py
ML_LOGGING_ENABLED = os.environ.get("ML_LOGGING_ENABLED", "false").lower() == "true"

class MLLogger:
    @staticmethod
    async def log_transition(...):
        if not ML_LOGGING_ENABLED:
            return
        # 기존 로직
```

---

## 5. 스키마 변경

### 5.1 DB: `GameSession` 모델

```python
# app/db/models.py — GameSession 클래스에 추가
save_replay = Column(Boolean, default=False, nullable=False, server_default="false")
```

### 5.2 Alembic Migration

```python
# alembic/versions/004_add_save_replay_to_games.py
def upgrade():
    op.add_column('games', sa.Column('save_replay', sa.Boolean(), nullable=False, server_default='false'))

def downgrade():
    op.drop_column('games', 'save_replay')
```

### 5.3 Pydantic Schema

```python
# app/schemas/game.py

class GameRoomCreate(BaseModel):
    title: str = Field(min_length=1, max_length=30)
    is_private: bool = False
    password: Optional[str] = None
    save_replay: bool = False           # ← 추가

class BotGameCreateRequest(BaseModel):
    bot_types: List[str] = Field(default_factory=lambda: ["random", "random", "random"])
    save_replay: bool = False           # ← 추가
```

---

## 6. API 변경

### 6.1 방 생성 (기존 엔드포인트 수정)

**POST `/api/puco/rooms/`** — `save_replay` 필드 추가

```python
# room.py — create_room
room = GameSession(
    ...
    save_replay=room_info.save_replay,    # ← 추가
)
```

**POST `/api/puco/rooms/bot-game`** — `save_replay` 필드 추가

```python
# room.py — create_bot_game
room = GameSession(
    ...
    save_replay=body.save_replay,          # ← 추가
)
```

### 6.2 리플레이 조회 (신규 엔드포인트)

**GET `/api/puco/game/{game_id}/replay`**

```python
# app/api/channel/game.py 에 추가

@router.get("/{game_id}/replay")
async def get_replay(
    game_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    room = db.query(GameSession).filter(GameSession.id == game_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="게임을 찾을 수 없습니다")
    if not room.save_replay:
        raise HTTPException(status_code=404, detail="리플레이가 저장되지 않은 게임입니다")

    replay_path = get_replay_file_path(game_id)
    if not os.path.exists(replay_path):
        raise HTTPException(status_code=404, detail="리플레이 파일이 없습니다")

    with open(replay_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    return payload
```

### 6.3 리플레이 가능 게임 목록 (신규 엔드포인트)

**GET `/api/puco/game/replays`**

```python
@router.get("/replays")
async def list_replays(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    games = db.query(GameSession).filter(
        GameSession.save_replay == True,
        GameSession.status == "FINISHED",
    ).order_by(GameSession.updated_at.desc()).limit(50).all()

    return [
        {
            "game_id": str(g.id),
            "title": g.title,
            "num_players": g.num_players,
            "finished_at": g.updated_at.isoformat() if g.updated_at else None,
        }
        for g in games
    ]
```

---

## 7. 프론트엔드 변경 (개요)

### 7.1 방 생성 UI — 리플레이 토글

대기방 생성 화면과 봇전 생성 화면에 "리플레이 저장" 토글 버튼 추가.

**영향 파일:**
- `frontend/src/App.tsx` (또는 방 생성 모달 컴포넌트)
- 봇전 생성 요청에 `save_replay: true/false` 포함

### 7.2 리플레이 뷰어 (향후 별도 작업)

이번 범위에서는 **로그 구조만 확정**. 리플레이 뷰어 UI는 후속 작업.

개념 설계:
```
ReplayViewer
  ├─ 리플레이 목록에서 게임 선택
  ├─ GET /api/puco/game/{id}/replay → payload 로드
  ├─ step index 상태 관리 (0 ~ total_steps)
  ├─ step 0: initial_snapshot → GameScreen 렌더링
  ├─ step N: entries[N-1].snapshot_after → GameScreen 렌더링
  ├─ 컨트롤: ◀ 이전 | ▶ 다음 | ⏩ 배속 자동재생 | ⏸ 일시정지
  └─ 하단: entries[N-1].commentary 표시
```

기존 컴포넌트 재사용 가능 목록:
- `GameScreen` — 전체 게임 보드 레이아웃
- `IslandGrid` — 섬 타일 렌더링 (ordered `plantations[]` 사용)
- `CityGrid` — 도시 건물 렌더링 (ordered `buildings[]` 사용)
- `CommonBoard` 관련 컴포넌트 — 역할 보드, 화물선, trading house

---

## 8. 코드 변경 요약

### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/db/models.py` | `GameSession.save_replay` 컬럼 추가 |
| `backend/app/schemas/game.py` | `GameRoomCreate.save_replay`, `BotGameCreateRequest.save_replay` 추가 |
| `backend/app/api/channel/room.py` | `create_room`, `create_bot_game`에 `save_replay` 전달 |
| `backend/app/api/channel/game.py` | `get_replay`, `list_replays` 엔드포인트 추가 |
| `backend/app/main.py` | 라우터 등록 (game 라우터에 이미 포함) |
| `backend/app/services/replay_logger.py` | v2 페이로드 구조: `initial_snapshot`, `snapshot_after` 지원 |
| `backend/app/services/game_service.py` | `room.save_replay` 체크 후 ReplayLogger 호출 조건부 실행 |
| `backend/app/services/ml_logger.py` | `ML_LOGGING_ENABLED` 환경변수 기반 feature flag |
| `backend/alembic/versions/004_*.py` | 마이그레이션: `save_replay` 컬럼 |
| `frontend/src/App.tsx` (or 모달) | 방 생성 / 봇전 생성 시 리플레이 토글 UI |

### 신규 파일

없음 (기존 파일 수정으로 충분).

---

## 9. 구현 계획

### Scope

- **In**:
  - ReplayLogger v2 페이로드 구조 (`initial_snapshot` + `snapshot_after`)
  - `GameSession.save_replay` DB 컬럼 + migration
  - 방 생성 / 봇전 생성 API에 `save_replay` 파라미터
  - 조건부 리플레이 저장 (`save_replay == True`인 게임만)
  - MLLogger feature flag 비활성화
  - 리플레이 조회 API (`GET /replay`, `GET /replays`)
  - 프론트엔드 방 생성 UI에 토글 추가

- **Out**:
  - 리플레이 뷰어 UI (후속 작업)
  - DB GameLog 삭제 (후속 작업)
  - 오프라인 RL 학습 파이프라인 (장기)

### Action Items

```
[ ] 1. Alembic migration 작성: games 테이블에 save_replay 컬럼 추가
[ ] 2. GameSession 모델에 save_replay 필드 추가 (models.py)
[ ] 3. Pydantic schema에 save_replay 필드 추가 (GameRoomCreate, BotGameCreateRequest)
[ ] 4. room.py의 create_room, create_bot_game에 save_replay 전달
[ ] 5. replay_logger.py 수정: v2 페이로드 (initial_snapshot, snapshot_after)
[ ] 6. game_service.py 수정: save_replay 체크 + rich_state를 snapshot으로 전달
[ ] 7. ml_logger.py에 ML_LOGGING_ENABLED feature flag 추가
[ ] 8. game.py에 replay 조회 API 추가 (GET replay, GET replays)
[ ] 9. 프론트엔드 방 생성 / 봇전 생성 UI에 리플레이 토글 추가
[ ] 10. Docker 환경에서 통합 테스트: 게임 생성 → 진행 → 리플레이 조회 확인
```

---

## 10. 미해결 질문

1. **리플레이 로그 보존 기간**: 무기한? N일 후 자동 삭제? → 우선 무기한, 필요 시 정리 정책 추가
2. **리플레이 파일 서빙 방식**: 현재 설계는 API에서 JSON 직접 반환. 대규모 트래픽 시 CDN/정적 파일 서빙 검토 가능 → 현재 규모에서는 불필요
3. **v1 기존 리플레이 호환**: v1 파일은 그대로 유지. 프론트엔드 뷰어에서 `format` 필드로 분기 가능

---

## 11. 온라인 학습 vs 오프라인 학습 참고 (향후)

현재 `train_ppo_selfplay_server.py`는 온라인 PPO:
- rollout worker가 `PuertoRicoEnv`를 직접 구동
- 공유 메모리로 (obs, action, log_prob, reward, done, value) 수집
- **로그 파일을 사용하지 않음**

향후 오프라인 학습 파이프라인 구축 시 MLLogger에 추가해야 할 필드:
- `log_prob`: importance sampling ratio 계산용
- `value_estimate`: GAE 계산용
- 또는 CQL/IQL/Behavioral Cloning 등 off-policy 알고리즘으로 전환

이번 작업에서는 MLLogger를 비활성화만 하고, 오프라인 학습 설계는 별도 작업으로 진행.
