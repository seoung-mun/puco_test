# Shutdown / Restart Recovery Design

작성일: 2026-04-30
상태: draft
저자: Codex

## 1. 요약

현재 봇전이 중간에 멈추는 직접 원인은 Render 인스턴스 재시작 자체보다, 진행 중 게임의 진실 원본이 프로세스 메모리에만 있다는 점이다.

- `GameService.active_engines`, `_bot_tasks`, `_game_speed`, `_game_paused`는 모두 메모리 전용이다.
- Render가 graceful shutdown 또는 instance replacement를 수행하면 진행 중 엔진과 bot task가 함께 사라진다.
- 서버가 다시 올라와도 `PROGRESS` 게임을 복원하는 startup 경로가 없어 게임이 멈춘다.

이 문서는 다음 방향을 채택한다.

- 복구 방식: `seed + action journal replay`
- 사람 액션 안정성: `at-most-once`
- 복구 범위: 패치 이후 시작한 게임은 `정확 복구`, 이미 진행 중인 게임은 `best-effort`
- 복구 트리거: startup eager recovery가 아니라 `lazy per-game recovery`

## 2. 확인된 사실

### 2.1 Render 재시작이 실제로 게임을 끊는다

실서비스 로그에서 다음 순서가 확인됐다.

1. `BOT_TRACE`가 정상 진행된다.
2. 새 server process가 시작된다.
3. 기존 process가 `Shutting down`으로 종료된다.
4. 진행 중 bot task가 `cancelled=True`로 끝난다.

즉 이번 문제는 봇 추론 예외가 아니라 인스턴스 재시작 후 메모리 엔진이 사라지는 구조적 문제다.

### 2.2 코드상 `obm`이라는 별도 개념은 없고, 현재 쓰이는 값은 `obs`다

코드베이스에는 `obm`이라는 심볼이 없다. 이 문서는 사용자가 말한 `obm`을 현재 코드의 `obs` 또는 observation 의미로 해석한다.

### 2.3 `obs`는 당시의 게임 화면 전체가 아니다

현재 `EngineWrapper.get_state()`는 프론트가 보는 UI 상태를 반환하지 않는다.

- `backend/app/engine_wrapper/wrapper.py`
  - `get_state()`는 `MODEL_OBSERVATION_STATE_KIND`를 붙인 `model-observation.v1` 상태를 반환한다.
  - 실제 값은 `self.last_obs`이며, 이는 `env.observe()`에서 받은 모델 입력용 observation이다.
- `backend/app/services/state_serializer.py`
  - 프론트가 보는 게임 화면 상태는 별도로 `rich-game-state.v1`로 직렬화된다.

정리:

- `obs` = 모델 입력용 관측 상태
- `rich state` = 플레이어 화면 상태
- replay entry의 `rich_state` = 사람이 읽는 상태 스냅샷

따라서 자동복구는 `obs를 그대로 저장해서 화면을 복구`하는 문제가 아니라,

1. 엔진 도메인 상태를 정확히 다시 만들고
2. 그 결과로 `rich-game-state`를 다시 생성하는 문제다.

### 2.4 현재 재연결 경로는 초기 state re-sync가 약하다

현재 게임 WebSocket은 다음 순서다.

- 클라이언트가 연결
- JWT auth
- 서버가 `auth_ok` 전송
- 이후 `STATE_UPDATE`를 기다림

하지만 연결 직후 최신 상태를 즉시 한 번 밀어주는 경로는 없다. 따라서 서버가 살아 있어도 재연결 시점에는 화면이 멈춘 것처럼 보일 수 있다.

### 2.5 사람 액션은 현재 `exactly-once`도 `at-most-once`도 아니다

현재 사람 액션은 다음 흐름이다.

- 프론트가 REST로 `POST /api/puco/game/{game_id}/action` 전송
- 서버가 메모리 엔진에 action 적용
- 응답 state를 반환
- 동시에 WS로 `STATE_UPDATE`가 퍼진다

하지만 다음 보장이 없다.

- 같은 클릭이 재시도돼도 중복 실행되지 않는다는 보장
- 요청은 적용됐지만 응답이 끊긴 경우, 같은 액션이 다시 들어와도 안전하다는 보장
- stale client가 과거 state 기준 액션을 보내도 거절된다는 보장

따라서 사람 턴에서는 `at-most-once` 안전장치가 필요하다.

## 3. 목표와 비목표

### 3.1 목표

- Render 재시작 후 진행 중 게임을 자동 복구한다.
- 패치 이후 시작한 게임은 action sequence 기준으로 정확 복구를 보장한다.
- 사람 턴에서 네트워크 단절이 발생해도, 사용자가 선택하지 않은 플레이가 서버에서 임의로 진행되지 않게 한다.
- 봇 턴이 active면 복구 직후 다시 스케줄링한다.
- 재연결 직후 클라이언트가 최신 state를 즉시 받도록 한다.
- 512MB RAM / 0.1 CPU 환경에서 감당 가능한 방식으로 설계한다.

### 3.2 비목표

- 패치 이전에 seed가 저장되지 않은 모든 진행 중 게임의 정확 복구
- 엔진 전체 내부 객체 그래프를 binary snapshot으로 직렬화하는 것
- free tier cold start 자체를 제거하는 것
- replay/commentary 구조의 전면 재설계

## 4. 고려한 접근안

### 4.1 접근안 A: `seed + action journal replay`

초기 seed와 governor를 영속화하고, action journal을 순서대로 replay해서 현재 상태를 복원한다.

장점:

- 메모리 사용량이 가장 작다.
- 엔진 변경에 대한 결합이 상대적으로 낮다.
- 현재 `GameLog`와 `GameSession` 중심 구조에 가장 자연스럽게 붙는다.
- free tier 환경에 가장 잘 맞는다.

단점:

- 게임이 길수록 복구 시간이 step 수에 비례한다.

### 4.2 접근안 B: `periodic snapshot + replay tail`

주기적으로 복구 스냅샷을 저장하고, 마지막 snapshot 이후 journal만 재생한다.

장점:

- 긴 게임 복구 속도가 더 빠르다.

단점:

- 스냅샷 포맷 정합성 검증이 어렵다.
- 구현 범위가 커진다.
- 현재 엔진 구조상 snapshot/restore 계약을 새로 설계해야 한다.

### 4.3 접근안 C: `full engine state persistence`

엔진 내부 상태를 거의 그대로 저장/복원한다.

장점:

- 이론상 가장 빠른 복구가 가능하다.

단점:

- upstream 엔진 변경에 매우 취약하다.
- 구현과 검증 비용이 과도하다.
- 현재 문제 크기에 비해 지나치게 무겁다.

### 4.4 채택안

이 문서는 접근안 A를 채택한다.

이유:

- 현재 장애의 핵심은 "메모리 상태만 진실원본으로 둔 것"이다.
- 진실원본을 durable metadata + ordered journal로 옮기면 문제의 중심을 해결할 수 있다.
- free tier 자원 제약에서 가장 현실적이다.

## 5. 복구 보장 범위

### 5.1 패치 이후에 시작한 게임

정확 복구 보장 대상이다.

필수 전제:

- `game_seed`
- `governor_idx`
- `engine/recovery fingerprint`
- ordered action journal

이 네 가지가 모두 있으면 동일 코드/동일 엔진 fingerprint 기준으로 deterministic replay가 가능하다.

### 5.2 이미 진행 중인 게임

`best-effort` 대상이다.

이유:

- 현재는 game start 시 seed가 저장되지 않는다.
- 현재 `GameLog.state_before/state_after`는 `model-observation`이며, 초기 덱 순서나 random state를 정확 재구성하기에 충분하지 않다.

best-effort 정책:

- recovery metadata가 없으면 정확 복구를 시도하지 않는다.
- 마지막 `rich_state` 또는 Redis cached state가 있으면 UI에는 보여준다.
- 하지만 active engine을 재구성할 수 없으면 자동 진행은 하지 않는다.
- 이 상태는 `recovery_blocked`로 표시하고, 사람이 명시적으로 종료/재시작/관리 조치를 선택하게 한다.

## 6. 선택한 아키텍처

### 6.1 핵심 원칙

- 메모리 엔진은 캐시일 뿐, 진실원본이 아니다.
- 진실원본은 Postgres에 둔다.
- Redis는 최신 state fan-out과 reconnect fast-path에만 쓴다.
- 복구는 startup 전체 sweep이 아니라, 해당 `game_id`에 첫 접근이 왔을 때 수행한다.
- 사람 액션은 `at-most-once`를 강제한다.

### 6.2 저장해야 할 durable metadata

`games` 테이블 또는 별도 recovery metadata 테이블에 다음 정보가 필요하다.

- `recovery_schema_version`
- `game_seed`
- `governor_idx`
- `num_players`
- `player_control_modes` 또는 현재 `players`만으로 복원 가능한 정보
- `engine_fingerprint`
  - upstream commit
  - env module
  - action-space fingerprint
  - mayor semantics fingerprint
- `state_revision`
  - 현재 state의 단조 증가 revision
- `recoverable`
  - exact recovery 가능 여부

`engine_fingerprint`가 현재 코드와 다르면 exact replay를 시도하지 않고 `recovery_blocked`로 전환한다.

### 6.3 새 action journal

현재 `GameLog`는 replay 분석과 audit에는 유용하지만, durable recovery journal로 쓰기엔 목적이 섞여 있다. recovery 전용 journal을 별도 두는 쪽이 안전하다.

예상 필드:

- `id`
- `game_id`
- `revision`
- `round_before`
- `step_before`
- `actor_id`
- `actor_kind` (`human` | `bot`)
- `action_index`
- `canonical_id`
- `action_intent_id` nullable
- `expected_state_revision` nullable
- `phase_before`
- `active_player_before`
- `created_at`

제약:

- unique `(game_id, revision)`
- unique `(game_id, action_intent_id)` where `action_intent_id is not null`

`GameLog`는 이후에도 replay/debug용으로 유지하되, recovery는 이 journal을 기준으로 한다.

### 6.4 사람 액션 계약 확장

프론트 요청 payload에 다음을 추가한다.

- `action_intent_id`
  - 클릭 단위 UUID
- `expected_state_revision`
  - 사용자가 보고 있던 최신 state revision

의미:

- `action_intent_id`는 같은 클릭의 중복 재전송을 dedupe한다.
- `expected_state_revision`은 stale client의 오래된 액션을 막는다.

결정:

- 사람 액션은 `at-most-once`
- ambiguous case에서는 자동 진행 금지

### 6.5 lazy per-game recovery

새 진입점 `ensure_engine_loaded(game_id)`를 둔다.

호출 위치:

- `POST /api/puco/game/{game_id}/action`
- game WebSocket connect 후 auth 직후
- `/api/puco/games/{game_id}/playback`
- bot resume가 필요한 서버 내부 경로

동작:

1. 메모리에 engine이 있으면 그대로 반환
2. 없으면 per-game lock 획득
3. 다른 요청이 이미 복구했는지 다시 확인
4. durable metadata 조회
5. exact recoverable이면 fresh engine 생성
6. action journal 순서대로 replay
7. replay 결과 revision / step_count / active_player를 검증
8. `active_engines[game_id] = engine`
9. 최신 `rich-game-state` 생성 후 Redis state cache 갱신
10. active player가 bot이면 bot scheduling 재개

복구 중 같은 game에 대한 동시 접근은 모두 같은 lock을 기다리게 해서 중복 replay를 막는다.

### 6.6 recovery replay는 일반 `process_action()`를 재사용하지 않는다

복구 중 `GameService.process_action()`를 그대로 호출하면 부작용이 중복된다.

- replay logger 중복 append
- ML logger 중복 write
- WebSocket broadcast 중복
- bot task 재스케줄링 중복

따라서 recovery 전용 `ReplayReplayer` 또는 `replay_action_without_side_effects()` 경로가 필요하다.

이 경로는 아래만 수행한다.

- engine step
- step/revision consistency 검증

그리고 아래는 수행하지 않는다.

- DB replay side effect write
- ML logging
- Redis publish
- WS broadcast
- bot scheduling

### 6.7 WebSocket 초기 동기화

현재 `auth_ok` 뒤 즉시 최신 state를 보내지 않는 문제가 있다.

개선:

1. auth 성공
2. `ensure_engine_loaded(game_id)`
3. 필요하면 `RECOVERY_STARTED`
4. recovery 완료 후 `STATE_UPDATE` 1회 즉시 전송
5. 이후 실시간 stream 지속

복구가 250ms 이상 걸릴 가능성이 있으면 `RECOVERY_STARTED` 또는 `RECOVERY_WAIT` 같은 중간 메시지를 보내 클라이언트가 overlay를 띄울 수 있게 한다.

### 6.8 bot resume 규칙

recovery 완료 직후:

- `room.status == PROGRESS`
- `paused == false`
- active player가 bot

이면 정확히 한 번만 bot scheduling을 재개한다.

중복 scheduling 방지:

- recovery lock 내부에서만 scheduling 판단
- game별 active bot task generation 또는 `task already scheduled` 가드 필요

## 7. 사람 페이즈 끊김 시나리오

이 문서는 사람이 선택하지 않은 플레이가 임의로 진행되는 상황을 금지한다.

### 7.1 시나리오 A: 요청이 서버에 도달하지 않았다

상황:

- 사용자가 클릭
- 네트워크가 끊겨 서버가 요청을 못 받음

결과:

- journal에 action 없음
- state revision 변화 없음
- recovery 후에도 같은 사람 턴 상태 유지
- 사용자는 최신 state를 보고 다시 선택

정책:

- 자동 재시도 없음
- 서버 임의 진행 없음

### 7.2 시나리오 B: 요청이 서버에 도달했고 적용됐지만 응답이 끊겼다

상황:

- 서버는 action을 정상 commit
- journal에 기록 완료
- 응답 또는 WS만 사용자에게 도달하지 못함

결과:

- 같은 `action_intent_id`로 재시도하면 중복 실행하지 않음
- 서버는 현재 state를 돌려주거나 WS로 최신 state를 보냄
- 사용자가 선택하지 않은 추가 플레이는 발생하지 않음

정책:

- unique `(game_id, action_intent_id)`로 dedupe
- duplicate intent면 `duplicate=true` 성격의 정상 응답을 허용

### 7.3 시나리오 C: stale client가 과거 state 기준으로 다시 보냈다

상황:

- 사용자는 revision 12를 보고 클릭했는데
- 서버는 이미 revision 13으로 진행됨

결과:

- `expected_state_revision` mismatch
- 서버는 action 거절
- 클라이언트는 최신 state를 다시 동기화

정책:

- `409 stale_state` 또는 동등한 explicit error
- 이 경우도 자동 진행 금지

### 7.4 시나리오 D: 사람 턴 중 서버가 재시작됐다

상황:

- 사람이 아직 선택하지 않음
- 서버만 재시작

결과:

- exact recovery 가능한 게임이면 같은 사람 턴으로 복구
- bot auto-play 금지
- 사용자가 다시 선택

### 7.5 시나리오 E: 사람 액션 이후 bot chain 직전에 재시작됐다

상황:

- 사람 action은 commit됨
- 그 결과 다음 active player는 bot
- bot task 생성 전 또는 sleep 중 서버 재시작

결과:

- recovery 후 active player가 bot임을 보고 bot scheduling 재개
- 사람이 선택하지 않은 새 human action은 절대 생성되지 않음

## 8. 복구 시간 추정

현재 코드와 개발 컨테이너에서 측정한 값:

- engine 생성: 보통 수십 ms
- sample game replay: `121 step ~= 0.36초`
- 20판 random legal rollout:
  - 평균 `331.6 step ~= 0.375초`
  - 최대 `480 step ~= 0.51초`

이 값은 개발 머신이라 free tier보다 훨씬 빠르다.

14라운드급 게임에 대한 실전 추정:

- 대략 `200~230 step`
- 개발 컨테이너 pure replay는 `0.2~0.4초` 예상
- Render free `0.1 CPU` 보수 계수를 적용하면 보통 `3~8초`
- 조금 긴 경우 `8~12초`
- 나쁜 경우 `10~15초+`

추가 주의:

- free tier cold start가 겹치면 플랫폼 기동 시간이 더 커서 수십 초 이상 걸릴 수 있다.
- 이 경우 문제는 replay 알고리즘보다 free tier lifecycle 자체에 더 가깝다.

따라서 설계 원칙:

- startup에서 모든 `PROGRESS` 게임을 eager recovery하지 않는다.
- 실제 접근이 들어온 게임만 lazy recovery한다.

## 9. 저사양 인스턴스 최적화 항목

이 항목은 recovery 설계의 성공 확률을 높이는 지원 작업이다.

### 9.1 backend 코드 최적화

- DB pool 축소
  - 현재 `pool_size=20`, `max_overflow=40`은 과하다.
  - free tier 기준 훨씬 작은 풀로 줄여야 한다.
- `/health` 경량화
  - liveness용과 deep health를 분리한다.
  - Render probe는 가능한 가벼운 경로를 사용한다.
- WS connect 직후 최신 state 즉시 전송
- active game 중 replay payload 전체 rewrite 최소화
  - 현재 `Replay.payload` 전체를 매턴 다시 읽고 다시 쓰는 구조는 비싸다.
- `deepcopy`와 JSON 직렬화 중복 축소
  - 현재 action당 `deepcopy`와 `json.dumps`가 여러 번 발생한다.

### 9.2 Dockerfile / runtime 최적화

- `torchvision` 제거 검토
  - 현재 서버 코드에서 직접 사용 흔적이 없다.
- `asyncpg`, `websockets` 등 미사용 의존성 제거 검토
- thread 수 고정
  - `OMP_NUM_THREADS=1`
  - `MKL_NUM_THREADS=1`
  - `OPENBLAS_NUM_THREADS=1`
  - 필요하면 PyTorch thread도 1로 고정
- `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`
- healthcheck에서 `curl` 제거 검토
  - Python stdlib 기반 check로 대체 가능

이 최적화는 recovery와 별도 PR로 분리할 수 있지만, free tier 안정성에는 강한 영향이 있다.

## 10. TDD 계획

이 설계는 구현 전에 failing test를 먼저 작성한다.

### 10.1 backend 테스트

1. `test_recovery_metadata_persisted_on_game_start`
- 새 게임 시작 시 `game_seed`, `governor_idx`, `recoverable=true`, `state_revision=0` 저장

2. `test_lazy_recovery_on_action_endpoint`
- 메모리 engine이 비어 있을 때 `/action` 진입이 journal replay로 engine을 복구

3. `test_lazy_recovery_on_ws_connect_sends_state_update`
- WS auth 직후 recovery가 일어나고 최신 `STATE_UPDATE` 1회 전송

4. `test_human_action_duplicate_intent_is_not_applied_twice`
- 같은 `action_intent_id` 재전송 시 step/revision이 두 번 증가하지 않음

5. `test_human_action_stale_revision_is_rejected`
- 오래된 `expected_state_revision`으로 보낸 action은 거절

6. `test_recovery_resumes_bot_turn_once`
- recovery 후 active player가 bot이면 task 하나만 스케줄링

7. `test_recovery_for_prepatch_game_without_seed_is_blocked`
- metadata 없는 old `PROGRESS` game은 exact recovery하지 않고 blocked 처리

8. `test_replay_replayer_has_no_side_effect_duplication`
- recovery replay가 replay logger / ML logger / WS publish를 중복 실행하지 않음

### 10.2 frontend 테스트

1. `useGameWebSocket` recovery message handling
- `RECOVERY_STARTED` 수신 시 overlay 표시
- 이어서 `STATE_UPDATE` 수신 시 overlay 해제

2. duplicate human submit guard
- 같은 intent를 재사용하지 않도록 action helper가 새 intent를 생성

3. stale revision resync
- `stale_state` 응답 시 최신 state fetch 또는 WS state를 기다리도록 UI 상태 전환

### 10.3 검증 환경

테스트는 Docker 기준으로 수행한다.

- backend: `docker compose exec backend pytest ...`
- frontend: `docker compose exec frontend npm run test -- ...`

## 11. 구현 순서

1. recovery metadata schema 추가
2. action journal schema 추가
3. `state_revision` outbound contract 추가
4. 사람 액션 payload에 `action_intent_id`, `expected_state_revision` 추가
5. `ensure_engine_loaded(game_id)` 구현
6. side-effect 없는 recovery replay 구현
7. WS auth 직후 initial state sync 구현
8. bot resume 재개 규칙 구현
9. pre-patch `best-effort` / blocked 처리 구현
10. footprint 최적화 별도 묶음 적용

## 12. 위험과 대응

### 12.1 deterministic replay가 깨질 가능성

위험:

- engine 내부 randomness나 upstream 변경이 seed replay와 어긋날 수 있다.

대응:

- `engine_fingerprint` 저장
- replay 후 revision/step_count/active_player 검증
- mismatch 시 exact recovery 중단 후 blocked 처리

### 12.2 free tier 재시작이 너무 자주 발생할 가능성

위험:

- recovery는 되지만 사용자가 계속 몇 초씩 기다리게 될 수 있다.

대응:

- lazy recovery
- footprint reduction
- 필요 시 paid tier 승격 검토

### 12.3 recovery 중복 실행

위험:

- 동시 WS connect와 REST action이 같은 게임 복구를 동시에 시도할 수 있다.

대응:

- per-game lock
- single-flight rehydration

## 13. 이번 설계의 결론

이 문제의 본질은 free tier 자체보다, 재시작 가능한 플랫폼 위에서 게임 엔진을 메모리에만 둔 현재 구조다.

따라서 해법은:

- 메모리 엔진을 cache로 격하하고
- seed + action journal을 durable source of truth로 올리고
- 사람 액션에 `at-most-once` 안전장치를 붙이고
- recovery를 lazy per-game으로 수행하는 것

이 방향이면 다음을 동시에 만족할 수 있다.

- 봇전이 재시작 후 멈추지 않음
- 사람 턴에서 사용자가 선택하지 않은 플레이가 임의 진행되지 않음
- free tier에서도 현실적인 복구 시간을 유지
