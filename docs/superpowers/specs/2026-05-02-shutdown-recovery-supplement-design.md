# Shutdown Recovery Supplement — Design

작성일: 2026-05-02
상태: draft
선행 문서: `docs/shutdown_error.md` (2026-04-30, Codex)

## 0. 이 문서의 위치

`docs/shutdown_error.md`는 큰 골격(seed + action journal replay, lazy per-game recovery, at-most-once 사람 액션, recovery_blocked)을 이미 정의했다. 이 문서는 그 골격을 유지한 채, 구현 직전에 막히기 쉬운 빈틈을 메우고 v0/v1/v2 sequencing을 확정하는 보강 spec이다.

선행 문서 §1~§13의 결정 중 다음 4가지는 이 문서에서 **수정**된다:

1. `engine_fingerprint`에 commit hash 포함 → 사람이 의식적으로 +1하는 `engine_compat_version` 정수 + 보조 fingerprint 자동 검증.
2. recovery 전용 `action_journal` 새 테이블 신설 → `game_logs` (GameLog) 에 복구용 컬럼 추가, 단일 테이블이 journal 역할 겸직.
3. pre-patch / 복구 불가 게임의 자동 forfeit → `RECOVERY_BLOCKED` first-class status + 마지막 화면 + 사용자 수동 종료.
4. 단일 PR로 전체 출시 → v0(엔진 RNG 격리) → v1(복구) → v2(idempotency) 세 PR로 분할.

선행 문서의 나머지 결정(seed 기반 lazy recovery, 부작용 없는 replay 경로 분리, WS auth 직후 state sync, 봇 single-flight)은 그대로 유지된다.

## 1. 목표와 비목표

### 1.1 목표 (v0+v1)

- 엔진의 게임 도메인 무작위성을 시드만으로 재현 가능하게 만든다 (v0).
- Render 재시작 후 진행 중 게임을 다시 키면 메모리 엔진을 자동 복구한다 (v1).
- 정확 복구가 불가능한 게임은 마지막 화면을 보여주고 사용자가 종료 결정을 내릴 수 있게 한다 (v1).
- 봇 차례에서 끊겼다면 복구 직후 봇 스케줄링을 정확히 한 번 재개한다 (v1).
- 재연결 직후 클라이언트가 최신 화면을 1회 즉시 받는다 (v1).
- Render 무료 등급(512MB / 0.1 CPU) 안에서 감당 가능하다.

### 1.2 비목표

- 사람 액션의 at-most-once 보장 (v2)
- 다인전 abandonment 처리 (별도 spec)
- /health 분리, DB pool 축소, OMP env (별도 PR)
- Render cold start 자체 제거 (플랫폼 한계)
- pre-patch 진행 중 게임의 정확 복구 (운영상 무관, 사용자 합의)

## 2. Sequencing

| 단계 | 범위 | 출시 게이트 |
|---|---|---|
| **v0** | 엔진 RNG 격리 | 회귀 테스트 4건 + 기존 PuCo_RL/balance/regression 영향 없음 |
| **v1** | 복구 (lazy + journal + bot resume + WS init sync + frozen state UX) | 백엔드 신규 12건 + 프론트 신규 3건 + contract §7 기존 회귀 모두 통과 + Docker 통합 smoke 1회 |
| **v2** | 사람 액션 idempotency (`action_intent_id`, `expected_state_revision`) | 별도 spec |

이 spec의 §3~§7은 v0+v1만 다룬다. v2는 §9에 인터페이스만 메모.

## 3. v0: 엔진 RNG 격리

### 3.1 변경 위치 (전체 5곳)

| 파일:라인 | 현재 | 변경 |
|---|---|---|
| `PuCo_RL/env/pr_env.py:131-132` | `random.seed(seed); np.random.seed(seed)` | `engine._rng = random.Random(seed); engine._np_rng = np.random.default_rng(seed)` (Engine 객체에 RNG 주입) |
| `PuCo_RL/env/engine.py:67` | `random.randint(0, num_players - 1)` | `self._rng.randint(0, num_players - 1)` |
| `PuCo_RL/env/engine.py:96` | `random.shuffle(stack)` | `self._rng.shuffle(stack)` |
| `PuCo_RL/env/engine.py:141` | `random.shuffle(self.plantation_discard)` | `self._rng.shuffle(self.plantation_discard)` |

게임 룰의 무작위성(셔플, 거버너 선정)은 그대로다. 변경되는 것은 RNG의 소스가 전역 모듈에서 per-engine 인스턴스로 격리된다는 점뿐이다.

### 3.2 시드 명시화

`reset(seed=None)`인 경우 시스템 엔트로피로 초기화하되, 사용된 시드를 캡처해서 외부에 노출한다.

```python
self._seed_used = seed if seed is not None else random.randrange(2**63)
self._rng = random.Random(self._seed_used)
self._np_rng = np.random.default_rng(self._seed_used)
```

`backend/app/engine_wrapper/wrapper.py`에 read-only property:

```python
@property
def seed_used(self) -> int:
    return self.env.unwrapped._seed_used

@property
def initial_governor_idx(self) -> int:
    return self._initial_governor_idx  # reset 시점 캡처
```

`backend`는 이 두 값을 game start 시 DB에 저장한다 (§5.2).

### 3.3 회귀 테스트 (TDD: PR 머지 게이트)

PuCo_RL/tests/ 하위에 추가:

1. **`test_same_seed_produces_same_sequence`**
   같은 시드로 두 번 reset → governor_idx, 초기 셔플된 deck, 첫 5수 결과 동일.

2. **`test_different_seeds_produce_different_sequences`**
   다른 시드 두 개 → 결과 다름.

3. **`test_concurrent_global_random_does_not_affect_engine`**
   ```python
   ea = create_game_engine(num_players=3, game_seed=12345)
   ea_state_alone = capture_initial_state(ea)
   ea = create_game_engine(num_players=3, game_seed=12345)
   eb = create_game_engine(num_players=3, game_seed=67890)
   _ = capture_initial_state(eb)
   ea_state_with_b = capture_initial_state(ea)
   assert ea_state_alone == ea_state_with_b
   ```

4. **`test_random_module_global_state_unchanged_by_engine`**
   엔진 reset 전후로 전역 `random.getstate()`, `np.random.get_state()` 동일.

### 3.4 위험과 대응

- **PPO 모델 호환**: 동작/결과 분포는 같은 시드 → 같은 결과로 유지. 모델 추론 영향 없음.
- **`PuCo_RL/tests/balance_test.py:58-60`**: 명시적 전역 시드 사용 도구. 그대로 둠 (recovery와 무관).
- **봇 서비스의 `np.random.*`**: 변경 없음. 봇이 어떤 액션을 골랐는지는 journal에 적히므로 결정성 불필요. 전역 RNG 사용도 격리된 엔진엔 영향 없음.

## 4. v1: 데이터 모델 변경

### 4.1 `games` 테이블 (GameSession) 신규 컬럼

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `game_seed` | `BIGINT` | YES | 게임 시작 시 엔진 시드. NULL = pre-patch / unrecoverable. |
| `governor_idx` | `INTEGER` | YES | 시작 시점 거버너 인덱스. |
| `engine_compat_version` | `INTEGER` | YES | 시작 시점 엔진 룰 버전. NULL = unrecoverable. |
| `state_revision` | `INTEGER` | NO, DEFAULT 0 | 액션 적용마다 +1. |
| `recovery_blocked_reason` | `VARCHAR(64)` | YES | 정지화면 진입 사유. NULL = 정상. |

`status` 컬럼(STRING)에 새 값 추가: `WAITING / PROGRESS / FINISHED / **RECOVERY_BLOCKED**`.

`GET /api/puco/rooms/`는 `WAITING`만 노출하므로(`contract.md` §2.3) 새 값은 lobby 목록에 자동으로 가려진다.

### 4.2 `game_logs` 테이블 (GameLog → journal 겸직) 신규 컬럼

| 컬럼 | 타입 | NULL | 설명 |
|---|---|---|---|
| `revision` | `INTEGER` | YES | 이 액션 적용 후의 `state_revision`. NULL = pre-patch row. |
| `phase_before` | `VARCHAR(32)` | YES | 적용 직전 phase (검증용). |
| `active_player_before` | `VARCHAR(16)` | YES | 적용 직전 active player ref (검증용). |

기존 `action_data: JSONB`에 이미 `action_index`, `canonical_id`, actor 정보가 있으므로 journal payload는 그대로 사용. `state_before`/`state_after`는 model-observation으로, replay에는 사용하지 않는다.

### 4.3 인덱스

신규: `UNIQUE (game_id, revision) WHERE revision IS NOT NULL`
기존 유지: `ix_game_logs_game_round`

### 4.4 Alembic 마이그레이션 1건

`backend/alembic/versions/<timestamp>_recovery_metadata.py`:

```python
def upgrade():
    op.add_column('games', sa.Column('game_seed', sa.BigInteger(), nullable=True))
    op.add_column('games', sa.Column('governor_idx', sa.Integer(), nullable=True))
    op.add_column('games', sa.Column('engine_compat_version', sa.Integer(), nullable=True))
    op.add_column('games', sa.Column('state_revision', sa.Integer(),
                                    nullable=False, server_default='0'))
    op.add_column('games', sa.Column('recovery_blocked_reason', sa.String(64), nullable=True))

    op.add_column('game_logs', sa.Column('revision', sa.Integer(), nullable=True))
    op.add_column('game_logs', sa.Column('phase_before', sa.String(32), nullable=True))
    op.add_column('game_logs', sa.Column('active_player_before', sa.String(16), nullable=True))

    op.create_index(
        'ux_game_logs_game_revision',
        'game_logs', ['game_id', 'revision'],
        unique=True,
        postgresql_where=sa.text('revision IS NOT NULL'),
    )

def downgrade():
    op.drop_index('ux_game_logs_game_revision', table_name='game_logs')
    op.drop_column('game_logs', 'active_player_before')
    op.drop_column('game_logs', 'phase_before')
    op.drop_column('game_logs', 'revision')
    op.drop_column('games', 'recovery_blocked_reason')
    op.drop_column('games', 'state_revision')
    op.drop_column('games', 'engine_compat_version')
    op.drop_column('games', 'governor_idx')
    op.drop_column('games', 'game_seed')
```

기존 row backfill 불필요. 모든 신규 컬럼은 NULL 허용 또는 server_default 보유. 즉시 적용 가능.

### 4.5 `engine_compat_version` 보관 위치

`backend/app/services/engine_gateway/factory.py` 모듈 상수:

```python
ENGINE_COMPAT_VERSION = 1  # 게임 룰을 바꾸는 변경에서만 사람이 +1
```

룰을 바꾸는 PR은 이 한 줄을 +1 한다. 깜빡해도 §6.5의 보조 fingerprint와 §6.3의 step 검증이 안전망이 된다.

### 4.6 `model_versions` snapshot 보강

`build_model_versions_snapshot`이 만드는 dict에 `__engine__` 키 추가:

```python
snapshot["__engine__"] = {
    "compat_version": ENGINE_COMPAT_VERSION,
    "action_space": _action_space_fingerprint(),
    "mayor_semantics": _mayor_semantics_fingerprint(),
}
```

복구 시 보조 검증의 단일 출처 (§6.3 step 2).

## 5. v1: 게임 시작 시 metadata 기록

### 5.1 `start_game` 변경

`backend/app/services/game_service.py:93-111` 변경 부분:

```python
# 시드를 사전 결정해서 엔진과 DB 양쪽에 명시 주입
game_seed = secrets.randbits(63)
engine = create_game_engine(
    num_players=actual_players,
    game_seed=game_seed,
    player_control_modes=build_player_control_modes(room),
)
GameService.active_engines[game_id] = engine
GameService._engine_revision[game_id] = 0

# PROGRESS 전환과 함께 recovery metadata 기록 (한 트랜잭션)
room.status = "PROGRESS"
room.model_versions = build_model_versions_snapshot(room)
room.game_seed = game_seed
room.governor_idx = engine.initial_governor_idx
room.engine_compat_version = ENGINE_COMPAT_VERSION
room.state_revision = 0
self.db.commit()
```

엔진 생성과 DB 저장이 같은 트랜잭션에 묶여 한쪽만 성공할 수 없다.

### 5.2 `process_action`에서 revision 갱신

GameLog write 블록에 revision/phase_before/active_player_before 동봉, GameSession.state_revision update를 같은 트랜잭션에 묶는다:

```python
# 액션 적용 직전 캡처
phase_before_step = engine.current_phase
active_player_before_step = engine.active_player

# engine.step(action) 후
new_revision = self._engine_revision[game_id] + 1

GameLog 행 생성:
    revision = new_revision,
    phase_before = phase_before_step,
    active_player_before = active_player_before_step,
    # 기존 필드들 (round, step, actor_id, action_data, state_before, state_after) 그대로

self.db.execute(
    update(GameSession).where(GameSession.id == game_id).values(state_revision=new_revision)
)
self.db.commit()

self._engine_revision[game_id] = new_revision
```

원자성: 둘 중 하나만 commit되면 다음 복구 시 §6.3 step 7에서 mismatch로 잡혀 정지화면으로 안전 fallback.

### 5.3 EngineWrapper 노출 API

```python
@property
def current_phase(self) -> str:
    """state_serializer가 emit하는 phase 문자열과 동일 형식.
    END_ROUND/PROSPECTOR는 role_selection으로 평탄화."""
    return _serialize_phase(self.env.unwrapped.engine.current_phase)

@property
def active_player(self) -> str:
    return f"player_{self.env.unwrapped.engine.current_player_idx}"

@property
def initial_governor_idx(self) -> int:
    return self._initial_governor_idx  # reset 시점 캡처
```

`current_phase`/`active_player`는 검증용이므로 반드시 serializer와 동일한 정규화 헬퍼를 통해 emit. 그래야 journal과 일관됨.

## 6. v1: lazy 복구

### 6.1 새 진입점 `ensure_engine_loaded(game_id) -> EngineLoadResult`

```python
@dataclass
class EngineLoadResult:
    state: Literal["ready", "blocked"]
    reason: Optional[str] = None
    state_revision: Optional[int] = None
```

호출 사이트:

| 위치 | 파일 | 시점 |
|---|---|---|
| `POST /api/puco/game/{id}/action` | `backend/app/api/channel/game.py` | 라우터 진입 직후 |
| `WebSocket /api/puco/ws/{id}` | `backend/app/api/channel/ws.py` | `auth_ok` 직후 |
| `GET /api/puco/game/{id}/final-score` | `backend/app/api/channel/game.py` | PROGRESS 게임만 |
| `GET /api/puco/games/{id}/playback` | `backend/app/api/channel/playback.py` | 진입 직후 |
| `POST /api/puco/games/{id}/speed`, `/pause` | `backend/app/api/channel/playback.py` | 진입 직후 |

`state == "blocked"` 처리:
- HTTP: 409 + `{"error": "recovery_blocked", "reason": <string>}`.
- WebSocket: `{"type": "RECOVERY_BLOCKED", "reason": <string>}` 1회 전송 후 일반 stream 시작 (action은 어차피 거절됨).

### 6.2 per-game lock (single-flight)

```python
class GameService:
    _recovery_locks: Dict[UUID, asyncio.Lock] = {}
    _recovery_locks_meta_lock = asyncio.Lock()

    async def ensure_engine_loaded(self, game_id: UUID) -> EngineLoadResult:
        if game_id in self.active_engines:
            return EngineLoadResult(state="ready",
                                    state_revision=self._engine_revision[game_id])
        lock = await self._get_or_create_recovery_lock(game_id)
        async with lock:
            if game_id in self.active_engines:
                return EngineLoadResult(state="ready",
                                        state_revision=self._engine_revision[game_id])
            return await self._do_recovery(game_id)
```

이중 체크 패턴. 동시 WS 두 개가 같은 game_id로 들어와도 replay는 1회만 실행. 게임이 `FINISHED`/`RECOVERY_BLOCKED`로 영구 전환될 때 lock dict entry 제거.

### 6.3 `_do_recovery(game_id)` 흐름

```python
async def _do_recovery(self, game_id: UUID) -> EngineLoadResult:
    # 1. metadata 조회
    game = await db.get_game(game_id)
    if not game or game.status != "PROGRESS":
        return EngineLoadResult(state="blocked", reason="not_recoverable")

    if game.game_seed is None or game.engine_compat_version is None:
        await self._mark_blocked(game_id, "no_metadata")
        return EngineLoadResult(state="blocked", reason="no_metadata")

    if game.engine_compat_version != ENGINE_COMPAT_VERSION:
        await self._mark_blocked(game_id, "engine_version_mismatch")
        return EngineLoadResult(state="blocked", reason="engine_version_mismatch")

    # 2. 보조 fingerprint 검증
    if not self._fingerprints_match(game.model_versions):
        await self._mark_blocked(game_id, "fingerprint_mismatch")
        return EngineLoadResult(state="blocked", reason="fingerprint_mismatch")

    # 3. fresh engine 생성
    engine = create_game_engine(
        num_players=game.num_players,
        game_seed=game.game_seed,
        governor_idx=game.governor_idx,
    )

    # 4. journal 조회 (revision asc, NULL 제외)
    entries = await db.get_game_log_journal_entries(game_id)

    # 5. 순서 검증
    expected_rev = 0
    for e in entries:
        expected_rev += 1
        if e.revision != expected_rev:
            await self._mark_blocked(game_id, "journal_corrupt")
            return EngineLoadResult(state="blocked", reason="journal_corrupt")

    # 6. RECOVERY_STARTED hint (entry 30개 이상이면 250ms 초과 가능성)
    if len(entries) >= 30:
        await self._notify_recovery_started(game_id)

    # 7. 부작용 없는 step 재생 + 매 step 검증
    for e in entries:
        if engine.current_phase != e.phase_before:
            await self._mark_blocked(game_id, "replay_validation_failed")
            return EngineLoadResult(state="blocked", reason="replay_validation_failed")
        if engine.active_player != e.active_player_before:
            await self._mark_blocked(game_id, "replay_validation_failed")
            return EngineLoadResult(state="blocked", reason="replay_validation_failed")
        try:
            engine.replay_step(int(e.action_data["action_index"]))
        except Exception:
            logger.exception("[RECOVERY] replay_step failed game=%s revision=%d", game_id, e.revision)
            await self._mark_blocked(game_id, "replay_validation_failed")
            return EngineLoadResult(state="blocked", reason="replay_validation_failed")

    # 8. 최종 검증
    if game.state_revision != len(entries):
        await self._mark_blocked(game_id, "replay_validation_failed")
        return EngineLoadResult(state="blocked", reason="replay_validation_failed")

    # 9. 메모리 등록
    self.active_engines[game_id] = engine
    self._engine_revision[game_id] = game.state_revision

    # 10. Redis state cache + meta 갱신
    rich_state = build_rich_state(self.db, game_id, engine, game)
    self._sync_to_redis(game_id, rich_state)
    self._store_game_meta(game_id, game)

    # 11. bot resume (정확히 1회)
    self._maybe_resume_bot(game_id, game, engine)

    return EngineLoadResult(state="ready", state_revision=game.state_revision)
```

### 6.4 부작용 없는 step: `EngineWrapper.replay_step`

```python
def replay_step(self, action_index: int) -> None:
    """Apply a journal-recorded action without persistence side effects.
    No DB write, no logger, no broadcast. Engine state mutation only.
    """
    self.last_obs, *_ = self.env.step(action_index)
```

`process_action`을 재사용하지 않는다. 액션은 원본 시점에 이미 검증됐으므로(checked-once-write) 다시 검증할 필요 없음. 검증은 `_do_recovery` step 7의 `phase_before`/`active_player_before` 비교로 수행.

### 6.5 `_mark_blocked(game_id, reason)`

```python
async def _mark_blocked(self, game_id: UUID, reason: str) -> None:
    await db.execute(
        update(GameSession)
        .where(GameSession.id == game_id)
        .values(status="RECOVERY_BLOCKED", recovery_blocked_reason=reason)
    )
    self._recovery_locks.pop(game_id, None)
    logger.warning("[RECOVERY] blocked game=%s reason=%s", game_id, reason)
```

이 호출 후 `active_engines`에는 들어가지 않는다. 같은 game_id로 다시 `ensure_engine_loaded`가 와도 step 1에서 `not_recoverable` 반환.

## 7. v1: WS 초기 동기화 + 봇 재개 + 정지화면 UX

### 7.1 WS 초기 동기화 시퀀스

`backend/app/api/channel/ws.py:81-83` 사이에 삽입:

```python
await websocket.send_json({"type": "auth_ok", "player_id": player_id})

load_result = await game_service.ensure_engine_loaded(UUID(game_id))

if load_result.state == "blocked":
    last_state = await _fetch_last_rich_state(game_id)
    if last_state is not None:
        await websocket.send_json({"type": "STATE_UPDATE", "data": last_state})
    await websocket.send_json({
        "type": "RECOVERY_BLOCKED",
        "reason": load_result.reason,
    })
elif load_result.state == "ready":
    rich_state = await _fetch_or_build_rich_state(game_id)
    await websocket.send_json({"type": "STATE_UPDATE", "data": rich_state})

await manager.connect(game_id, websocket, player_id=player_id)
```

### 7.2 추가 WS 메시지 타입 (계약 확장)

`contract.md` §2.6에 추가:

| 타입 | 시점 | shape |
|---|---|---|
| `STATE_UPDATE` (직후 1회) | auth_ok 직후 ready일 때 | 기존 shape 그대로 |
| `RECOVERY_STARTED` | journal entry ≥ 30 일 때 replay 시작 직전 | `{"type": "RECOVERY_STARTED"}` |
| `RECOVERY_BLOCKED` | 복구 불가 | `{"type": "RECOVERY_BLOCKED", "reason": "<string>"}` |

기존 메시지 타입(`STATE_UPDATE`, `PLAYER_DISCONNECTED`, `GAME_ENDED`, `PING`, `END_GAME_REQUEST`)은 변경 없음.

### 7.3 봇 재개 single-flight: `_maybe_resume_bot`

```python
def _maybe_resume_bot(self, game_id: UUID, room: GameSession, engine: EngineWrapper) -> None:
    if room.status != "PROGRESS":
        return
    if self._game_paused.get(game_id, False):
        return

    active_idx = engine.env.unwrapped.engine.current_player_idx
    actor_id = (room.players or [])[active_idx]
    if not str(actor_id).startswith("BOT_"):
        return

    existing = self._bot_tasks.get(game_id)
    if existing is not None and not existing.done():
        return

    self._bot_tasks[game_id] = asyncio.create_task(
        self._run_bot_turn(game_id, room, engine)
    )
```

이 함수는 반드시 recovery lock 안에서만 호출된다 (`_do_recovery` step 11) → single-flight 보장. 추가 방어로 `_run_bot_turn` 시작 직후 self-check 가드 1줄.

`contract.md` §2.9: playback 컨트롤은 메모리 전용 → 재시작 후 1배속/미정지로 자동 리셋. `_game_paused.get(game_id, False)`는 항상 False여서 봇이 정상 재개됨. 별도 처리 불필요.

### 7.4 정지화면 UX (frontend 계약)

`frontend/src/hooks/useGameWebSocket.ts`:

```ts
on('RECOVERY_STARTED', () => setRecoveryOverlay(true))
on('RECOVERY_BLOCKED', (msg) => {
  setRecoveryBlocked({ reason: msg.reason })
  setRecoveryOverlay(false)
})
on('STATE_UPDATE', (msg) => {
  setRecoveryOverlay(false)
  setGameState(msg.data)
})
```

화면:
- `recoveryOverlay`: dimmed overlay + "게임 복구 중..." 메시지. 입력 disabled.
- `recoveryBlocked != null`: 마지막 STATE_UPDATE 위에 modal/banner — "이 게임은 복구할 수 없습니다 (사유: <reason>). [그대로 보기] [종료]". 모든 입력 disabled.
- "종료" → 기존 `END_GAME_REQUEST` WS 메시지 재사용. 서버는 `RECOVERY_BLOCKED` → `FINISHED` 전환 + `GAME_ENDED { reason: "recovery_blocked_user_end" }` broadcast.
- "그대로 보기" → modal만 닫음, 화면은 마지막 state 유지, 입력 여전히 disabled.

다인전: `END_GAME_REQUEST`는 1명이 보내도 즉시 게임 종료(`contract.md` §2.6). 한 명이 정리하면 모두 종료 — abandonment 추가 처리 불필요.

### 7.5 `_fetch_last_rich_state` / `_fetch_or_build_rich_state`

```python
async def _fetch_last_rich_state(game_id: UUID) -> Optional[Dict]:
    cached = redis_client.get(f"game:{game_id}:state")
    if cached:
        return json.loads(cached)
    return _read_last_rich_state_from_replay_log(game_id)
    # data/logs/replay/<game_id>.json의 마지막 rich_state entry

async def _fetch_or_build_rich_state(game_id: UUID) -> Dict:
    engine = self.active_engines.get(game_id)
    if engine is not None:
        room = await db.get_game(game_id)
        return build_rich_state(self.db, game_id, engine, room)
    cached = redis_client.get(f"game:{game_id}:state")
    return json.loads(cached) if cached else {}
```

복구 직후엔 항상 fresh build 경로. 정지화면에선 Redis cache → fallback replay log file 순.

## 8. 테스트 계획 (TDD)

### 8.1 v0 PuCo_RL 테스트 (4건)

§3.3 참조. PR 머지 게이트.

### 8.2 v1 백엔드 테스트 (12건)

`backend/tests/test_recovery_*.py` 신규:

**메타데이터/마이그레이션 (3)**
1. `test_start_game_persists_recovery_metadata`
2. `test_alembic_migration_adds_columns_idempotent`
3. `test_action_apply_increments_revision_atomically`

**정상 복구 (3)**
4. `test_lazy_recovery_on_action_endpoint_after_engine_eviction`
5. `test_lazy_recovery_on_ws_connect_emits_state_update_once`
6. `test_concurrent_recovery_runs_replay_only_once`

**정지화면 (3)**
7. `test_recovery_blocked_when_metadata_absent` (no_metadata)
8. `test_recovery_blocked_when_engine_compat_version_mismatch`
9. `test_recovery_blocked_when_journal_validation_fails`

**봇 재개 (2)**
10. `test_recovery_resumes_bot_turn_exactly_once`
11. `test_bot_resume_does_not_trigger_when_human_turn_active`

**부작용 격리 (1)**
12. `test_replay_step_does_not_invoke_loggers_or_broadcast`

### 8.3 v1 프론트 테스트 (3건)

`frontend/src/hooks/__tests__/useGameWebSocket.test.ts`:

1. `recovery_started_shows_overlay`
2. `state_update_after_recovery_clears_overlay`
3. `recovery_blocked_disables_input_and_shows_modal`

### 8.4 진행 순서

v0 머지 후:

1. 마이그레이션 작성 → test 2
2. start_game 변경 → test 1
3. process_action revision → test 3
4. EngineWrapper.replay_step → test 12
5. _do_recovery → test 4
6. WS init sync → test 5
7. per-game lock → test 6
8. _mark_blocked + 라우터 처리 → test 7~9
9. _maybe_resume_bot → test 10~11
10. frontend RECOVERY_* handling → frontend 1~3

각 단계마다 `contract.md` §7의 기존 회귀 테스트 모두 통과 유지.

### 8.5 검증 환경

도커 기준:
- backend: `docker compose exec backend pytest backend/tests/test_recovery_*.py -v`
- frontend: `docker compose exec frontend npm run test -- recovery`

## 9. 위험과 대응

### 9.1 revision unique 충돌 (race)

**상황**: 사람·봇 액션이 미세 race로 같은 revision insert 시도.
**대응**: `process_action`은 game_id별 lock으로 직렬화 (현재 구조). unique violation 발생 시 트랜잭션 롤백 + 1회 재시도, 그래도 실패면 사용자에게 409.

### 9.2 `ENGINE_COMPAT_VERSION` +1 누락

**상황**: 룰을 바꾼 PR이 +1 누락.
**대응**:
- 1차: 보조 fingerprint(`action_space`, `mayor_semantics`) 자동 검증.
- 2차: replay 후 phase/active_player/state_revision 검증 mismatch.
- 3차(별도 PR): pre-commit/CI 검사로 `PuCo_RL/env/engine.py` 변경 + `ENGINE_COMPAT_VERSION` 미변경 PR 경고.
- 결과: 잘못된 진행은 안 일어남, 최악은 정지화면.

### 9.3 큰 게임 replay latency

**상황**: 14라운드 supersized 게임 → 230 step → free tier 8~15초.
**대응**: `RECOVERY_STARTED` overlay. 머지 후 메트릭 수집(`logger.warning("[RECOVERY] elapsed=%dms entries=%d", ...)`). 임계치(예: 30초) 정책은 v2.

### 9.4 pre-patch 게임이 손에 안 닿고 영영 PROGRESS

**상황**: 사용자가 들어오지 않으면 status=PROGRESS 잔존.
**대응**: 사용자 합의로 무관(현재 다른 유저 없음). 별도 야간 batch는 후속 spec.

### 9.5 `replay_step` 예외

**상황**: journal 정상이지만 engine 내부 버그.
**대응**: try/except → `_mark_blocked("replay_validation_failed")`. 사용자는 정지화면. 서버 살아 있음. stack trace 로그.

### 9.6 lock dict 메모리 누수

**상황**: `_recovery_locks` dict 누적.
**대응**: `_mark_blocked` 시 pop, `END_GAME_REQUEST`/disconnect timeout 정리 경로에서 pop. game_id당 lock 1개라 영향 매우 작음.

## 10. v2 인터페이스 (참고용)

이 spec은 v2를 다루지 않지만, v1 구현 시 v2와 충돌 없이 확장 가능하도록 다음 인터페이스를 미리 가정:

- `ActionRequestPayload` (`backend/app/schemas/game.py`) `extra="forbid"` 정책 변경 필요. `action_intent_id: Optional[str]`, `expected_state_revision: Optional[int]` 추가.
- `game_logs` 테이블에 `action_intent_id: VARCHAR(64) NULL` + `UNIQUE (game_id, action_intent_id) WHERE action_intent_id IS NOT NULL`.
- frontend `channelAction` helper는 클릭마다 새 UUID 생성 + 마지막 revision tracking.
- Stale revision은 `409 stale_state` + 클라이언트 강제 resync.

v2 spec은 v1 머지 후 별도 작성.

## 11. 분리 PR 메모

- **footprint 최적화**: `/health` 분리, DB pool 축소(현재 20/40), OMP_NUM_THREADS 등(`shutdown_error.md` §9). recovery v1 머지 후 별도 PR.
- **`ENGINE_COMPAT_VERSION` 가드 CI**: pre-commit 또는 GHA. 별도 PR.
- **다인전 abandonment 정책**: 600s timeout 외 정책. 별도 spec.
- **pre-patch PROGRESS 게임 batch 정리**: 운영용. 별도 spec.

## 12. 영향 받는 기존 계약 요약

| 영역 | 영향 |
|---|---|
| `contract.md` §2.3 room status | `RECOVERY_BLOCKED` 추가. `GET /rooms/`는 `WAITING`만 노출이라 자동 가려짐. |
| `contract.md` §2.5 action endpoint | v1 변경 없음. v2에서 `extra="forbid"` 변경. |
| `contract.md` §2.6 game WS | `auth_ok` 직후 `STATE_UPDATE`/`RECOVERY_STARTED`/`RECOVERY_BLOCKED` 추가. |
| `contract.md` §6 persistence | 정본이 `GameService.active_engines[game_id]` → "PostgreSQL 액션 기록부, 메모리 엔진은 캐시"로 격상. Redis 역할 그대로. |
| `contract.md` §7 회귀 테스트 | `test_game_ws_auth_contract.py` 케이스 보강, `test_model_version_snapshot.py` snapshot shape 검증 보강 가능. |

## 13. 다음 단계

이 spec 승인 후:

1. spec review loop (spec-document-reviewer 서브에이전트).
2. user 최종 승인.
3. writing-plans 스킬로 v0 PR + v1 PR 각각의 implementation plan 작성.
4. v0 → v1 순으로 구현/머지.
5. v1 머지 후 별도 spec으로 v2(idempotency) + footprint 최적화 + 다인전 abandonment 진행.
