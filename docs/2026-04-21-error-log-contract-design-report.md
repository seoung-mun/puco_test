# 에러 로그 기반 계약 설계 보고서

작성일: 2026-04-21
최종 구현 반영일: 2026-04-23

범위:
- [error_logs.md](/Users/seoungmun/Documents/agent_dev/castest/castone/error_logs.md)에 기록된 실패 로그 분석
- 현재 프론트엔드-백엔드-모델 계약 중 실제로 어디가 깨졌는지 구조적으로 정리
- 구현이 아닌 설계 차원의 해결 방향 제안
- MLOps 관점에서 데이터 정합성 추적 로그를 어떻게 설계해야 하는지 정리

주의:
- 본 문서의 본문 진단은 2026-04-21 시점의 장애 분석을 보존한다.
- 2026-04-23에 실제 반영된 구현은 아래 `구현 반영 현황` 및 각 Task 상태 업데이트에 별도로 기록한다.

## 이해 요약

- 사용자 관점의 증상은 사람 액션과 봇 액션 모두에서 `500 Internal Server Error`가 발생하는 것이다.
- 하지만 로그를 보면 액션 자체는 엔진에 정상 반영된 뒤에 실패한다.
- 즉, 첫 번째 실패 지점은 프론트 요청 파싱이나 모델 추론이 아니라 replay/commentary 생성 경로다.
- 더 깊은 원인은 세 가지 상태 표현이 섞여 있기 때문이다.
  - 모델 입력용 observation state
  - 프론트 출력용 rich game state
  - 리플레이/commentary용 summary state
- 현재 API 경계의 입력 검증은 너무 느슨하고, 후처리 로직은 반대로 특정 타입을 지나치게 낙관적으로 가정한다.
- 결과적으로 “계약 위반을 초기에 잡지 못하고, 뒤쪽 부가 기능에서 500으로 터지는” 구조가 되어 있다.

## 전제

- 목표는 현재 게임 아키텍처를 전면 교체하는 것이 아니라, 계약 경계를 분리하고 오류 전파 범위를 줄이는 것이다.
- `POST /api/puco/game/{game_id}/action`는 계속 메인 액션 진입점으로 유지한다고 가정한다.
- `pr_env.py`는 PPO 계열 모델이 따르는 관측 계약의 기준으로 본다.
- replay/commentary와 ML logging은 중요하지만, 게임 플레이보다 우선해서 요청을 실패시키면 안 된다.
- 최종적으로는 프론트, 백엔드, replay, 모델 서빙 각각이 명시적인 스키마와 버전 정보를 가져야 한다.

## 2026-04-23 구현 반영 현황

이번 작업에서 실제로 반영된 변경은 다음과 같다.

- 액션 ingress 계약을 `payload: Dict[str, Any]`에서 `ActionRequestPayload`로 좁혔다.
  - `schema_version=action-request.v1`
  - `action_index: int`
  - 예상하지 못한 필드는 `extra="forbid"`로 차단
  - 관련 코드: [backend/app/schemas/game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/schemas/game.py), [backend/app/api/channel/game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/game.py)
- 모델 observation, rich game state, replay summary, transition log에 semantic label과 schema version을 붙였다.
  - `model-observation.v1`
  - `rich-game-state.v1`
  - `replay-summary.v1`
  - `transition-envelope.v1`
  - 관련 코드: [backend/app/services/contracts.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/contracts.py), [backend/app/engine_wrapper/wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py), [backend/app/services/state_serializer.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/state_serializer.py), [backend/app/services/ml_logger.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ml_logger.py)
- replay summary 정규화 계층을 보강했다.
  - singleton list인 `[2.0]`, `[8]` 같은 값은 scalar로 정규화
  - goods / island_tiles / city_buildings 같은 list 필드는 summary 전용으로 안전하게 축약
  - commentary는 숫자 scalar가 아니면 산술 diff 대신 안전한 문자열 비교로 degrade
  - 관련 코드: [backend/app/services/replay_logger.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/replay_logger.py)
- replay/commentary가 실패해도 gameplay 요청이 500으로 죽지 않도록 fail-open으로 전환했다.
  - `build_replay_entry()` 실패 시 degraded replay entry로 대체
  - `ReplayLogger.append_entry()` 실패 시 warning만 남기고 응답 유지
  - `commentary_status`, `summary_validation_status`, `degraded_replay_used` 필드를 replay entry에 추가
  - 관련 코드: [backend/app/services/game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py), [backend/app/services/replay_logger.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/replay_logger.py)
- ML logging도 fail-open으로 감쌌다.
  - `trace_id`를 transition info에 연결
  - `state_before_kind`, `state_after_kind`, schema version을 함께 기록
  - async sink 예외가 gameplay를 실패시키지 않도록 safe wrapper 추가
  - 관련 코드: [backend/app/services/game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py), [backend/app/services/ml_logger.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ml_logger.py)
- bot input snapshot의 phase 추출도 observation shape에 맞게 보강했다.
  - `global_state.current_phase`
  - `global_state.current_phase_onehot`
  - 둘 다 안전하게 해석
  - 관련 코드: [backend/app/services/bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)

## 2026-04-23 검증 결과

다음 회귀 테스트를 Docker에서 실행해 통과를 확인했다.

1. 직접 장애 경로와 fail-open 회귀

```bash
docker compose exec backend pytest \
  tests/test_replay_logger.py \
  tests/test_ml_logger.py \
  tests/test_game_action.py \
  tests/test_game_service_side_effect_fail_open.py \
  -q
```

결과:
- `18 passed`

2. serializer / websocket / turn validation / bot snapshot 인접 회귀

```bash
docker compose exec backend pytest \
  tests/test_priority2_bot_input_snapshot.py \
  tests/test_replay_logging_integration.py \
  tests/test_replay_logger_rich_state.py \
  tests/test_game_service_turn_validation.py \
  tests/test_priority2_ws_delivery_contract.py \
  tests/test_state_serializer_action_index.py \
  tests/test_mayor_serializer_contract.py \
  -q
```

결과:
- `37 passed`

비고:
- FastAPI `on_event` deprecation warning은 기존 경고로 남아 있다.
- Redis asyncio teardown warning도 테스트 종료 시점에 남지만, 이번 계약 수정의 기능 실패와는 별개다.

## 로그가 증명하는 사실

### 1. 엔진은 액션을 정상 처리했다

로그 근거:
- `engine_step_enter action=2 phase_before=8`
- `engine_step_exit action=2 phase_after=2 terminated=False truncated=False`

해석:
- 프론트 요청은 백엔드에 정상 도달했다.
- `action_index`는 정상 파싱되었다.
- 엔진은 실제로 액션을 적용했다.
- 따라서 이 로그만 놓고 보면, 첫 실패 지점은 HTTP 요청 계약 자체가 아니다.

관련 코드:
- [frontend/src/App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx:490)
- [backend/app/api/channel/game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/game.py:55)
- [backend/app/services/game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py:104)

### 2. 요청은 replay commentary 생성 중에 죽는다

관측된 예외:

```text
TypeError: unsupported operand type(s) for -: 'list' and 'list'
```

실패 호출 체인:
- `game.py -> GameService.process_action()`
- `build_replay_entry()`
- `_build_commentary()`
- `_describe_delta(before_value, after_value, label)`

관련 코드:
- [backend/app/services/game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py:177)
- [backend/app/services/replay_logger.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/replay_logger.py:124)

### 3. 본질은 “잘못된 로그 함수” 하나가 아니라 상태 의미의 혼선이다

`EngineWrapper.get_state()`는 `self.last_obs`를 반환한다.

관련 코드:
- [backend/app/engine_wrapper/wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py:103)

그런데 `self.last_obs`는 `env.observe()`에서 온 모델 입력용 observation이다.

관련 코드:
- [backend/app/engine_wrapper/wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py:182)
- [PuCo_RL/env/pr_env.py](/Users/seoungmun/Documents/agent_dev/castest/castone/PuCo_RL/env/pr_env.py:158)

반면 `replay_logger.summarize_transition_state()`와 `_build_commentary()`는 그 입력을 사람 읽기 좋은 scalar 중심 상태라고 가정한다.

관련 코드:
- [backend/app/services/replay_logger.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/replay_logger.py:76)
- [backend/app/services/replay_logger.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/replay_logger.py:135)

즉, 현재 로그가 보여주는 1차 계약 파손은 다음이다.

- 모델 관측 상태를
- 리플레이 요약 상태처럼 사용하고 있다

## 진단

### 직접 원인

`_describe_delta()`는 두 값이 숫자 스칼라라고 가정하고 `after - before`를 수행한다.

하지만 이 가정은 깨진다.

이유:
- `state_before`, `state_after`는 `EngineWrapper.get_state()`에서 온다
- `EngineWrapper.get_state()`는 모델 observation을 반환한다
- observation 내부에는 `(1,)` 배열, one-hot 벡터, 카운트 리스트가 다수 포함된다

즉, 이 오류는 우연이 아니라 상태 의미가 잘못 연결되어 생긴 결정적 오류다.

### 사람 액션과 봇 액션이 둘 다 죽는 이유

사람과 봇 모두 결국 같은 액션 처리 경로를 지난다.

- 턴 검증
- action mask 검증
- 엔진 step
- replay entry 생성
- ML logging 비동기 기록

그래서 replay entry 생성이 죽으면 사람 액션과 봇 액션 모두 같은 500으로 보인다.

### 왜 “프론트-백엔드-모델 계약이 다 깨진 것 같다”는 느낌이 드는가

그 감각 자체는 자연스럽다. 다만 이 로그가 직접 증명하는 건 조금 더 좁다.

- 프론트 -> 백엔드 액션 요청 계약:
  - 이번 로그만 보면 통과했다
- 백엔드 -> replay/commentary 계약:
  - 깨져 있다
- 백엔드 -> 모델 계약:
  - 별도 검증 필요하지만, 이번 로그의 직접 원인은 아니다
- 프론트 -> 백엔드 상태 출력 계약:
  - 여기도 검증 필요하지만, 이번 예외의 직접 원인은 아니다

정리하면, 지금 보이는 핵심 문제는 “프론트 요청 계약”보다 “모델용 observation 계약과 replay용 summary 계약의 혼선”이다.

## 현재 계약 지도

아래 내용은 2026-04-21 진단 시점의 상태를 설명한다. 2026-04-23 현재 반영 상태는 위 `구현 반영 현황`을 기준으로 본다.

현재 시스템에는 최소 다섯 개의 서로 다른 계약이 있다.

### 1. ActionRequest 계약

- 출발: 프론트
- 도착: channel API
- 현재 형태: `payload: Dict[str, Any]`
- 문제: 너무 느슨하다

관련 코드:
- [backend/app/schemas/game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/schemas/game.py:7)

### 2. RichGameState 계약

- 출발: backend serializer
- 도착: 프론트 UI, websocket 소비자
- 현재 형태: `serialize_game_state_from_engine(...)`
- 문제: 구조는 풍부하지만 outbound validation이 명시적이지 않다

### 3. ModelObservation 계약

- 출발: `env.observe()`
- 도착: PPO 학습, adapter/runtime
- 현재 형태: semantic observation dict + action mask
- 문제: 자기 영역 밖에서 재사용되고 있다

### 4. ReplaySummaryState 계약

- 출발: replay/logger 전용 정규화 결과여야 함
- 도착: replay JSON, commentary 생성
- 현재 문제: 명시적으로 정의되어 있지 않다

### 5. TransitionLogRecord 계약

- 출발: game service
- 도착: ML logger / replay logger
- 현재 문제: 내부 dict가 상태 의미를 공유하지 않고, schema identity가 없다

## 핵심 발견사항

### 발견 1. replay logger가 fail-closed로 동작한다

심각도: 높음

게임 액션과 직접 무관한 부가 기능이 현재는 요청 자체를 실패시킬 수 있다.

이건 운영 원칙 위반이다.

- 게임플레이 경로는 fail-safe여야 한다
- replay/commentary는 fail-open이어야 한다

### 발견 2. observation state와 presentation state가 섞여 있다

심각도: 높음

이게 이번 문제의 중심 설계 결함이다.

현재 구조:
- `EngineWrapper.get_state()`는 observation을 반환한다
- replay/commentary는 요약 도메인 상태를 기대한다

즉, downstream 입장에서는 “이 dict가 모델용 상태인지, UI용 상태인지, replay용 상태인지”를 shape를 보고 추측해야 한다.

### 발견 3. API 경계 입력 검증이 너무 약하다

심각도: 중간

`GameAction`이 다음처럼 되어 있다.

```python
payload: Dict[str, Any]
```

이 구조는 초기 개발 속도에는 유리하지만, 계약 위반을 너무 늦게 잡게 만든다.

관련 코드:
- [backend/app/schemas/game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/schemas/game.py:7)

### 발견 4. transition 객체에 semantic label이 없다

심각도: 높음

현재 replay logger와 ML logger 모두 “이 상태가 어떤 종류의 상태인지”를 명시적으로 싣지 않는다.

예:
- `model-observation.v1`
- `rich-game-state.v1`
- `replay-summary.v1`

이런 semantic label이 없으니, 디버깅 시 shape를 보고 의미를 추정해야 한다.

### 발견 5. 관측성은 있으나 contract observability는 부족하다

심각도: 중간

현재도 유용한 로그는 있다.
- `ACTION_TRACE`
- `BOT_TRACE`

하지만 부족한 것:
- schema version
- state kind
- field type summary
- parity fingerprint
- validation result

즉, 값은 찍고 있지만 “무슨 계약의 값인지”는 충분히 찍지 않는다.

## 설계 대안

### 대안 A. `_describe_delta()`만 국소 패치

접근:
- 숫자 아닌 값은 delta 계산을 건너뛴다
- `isinstance(..., (int, float))`로 방어

장점:
- 가장 빠르다
- 변경 범위가 작다

단점:
- 증상만 가린다
- 상태 의미 혼선은 그대로 남는다
- 다른 logger나 summarizer에서 같은 류의 문제가 다시 난다

평가:
- 긴급 hotfix로는 가능
- 구조적 해결책으로는 불충분

### 대안 B. 경계 스키마 + 상태 정규화 + fail-open 부가 기능

접근:
- 현재 아키텍처 유지
- 상태 의미를 명시적 스키마로 분리
- replay summary 입력을 먼저 정규화
- replay/commentary/ML logging을 non-fatal로 처리
- 핵심 경계에 구조화된 계약 로그 추가

장점:
- 현재 오류 계열을 구조적으로 줄인다
- 디버깅이 쉬워진다
- 기존 제품 구조를 크게 깨지 않는다
- 투자 대비 효과가 좋다

단점:
- 스키마 소유권과 경계를 팀이 명확히 관리해야 한다

평가:
- 권장안

추가 결정:
- 본 문서는 대안 B를 채택한다.
- 추가 목표는 “이번 장애를 고치는 것”에서 끝나지 않고, 같은 종류의 계약 혼선이 다시 생겨도 프론트, 백엔드, 엔진, 모델, replay, logger 경계에서 더 빨리 탐지하고 더 좁은 범위에서 실패하게 만드는 것이다.

### 대안 C. 이벤트 소싱 기반 전체 재설계

접근:
- 모든 액션을 불변 이벤트로 기록
- replay, ML log, frontend state를 이벤트로부터 파생

장점:
- 장기적으로 가장 깔끔하다
- 감사 추적성이 매우 좋다

단점:
- 현재 문제를 해결하기엔 과하다
- 마이그레이션 비용이 크다

평가:
- 지금 당장 권장하지 않음

## 권장 설계

### 1. 상태 semantic type을 명시적으로 도입한다

다음 스키마를 문서와 코드 경계에 정의해야 한다.

- `ActionRequestV1`
- `ModelObservationV1`
- `RichGameStateV1`
- `ReplaySummaryStateV1`
- `TransitionEnvelopeV1`

각 envelope에는 최소 다음이 있어야 한다.

- `schema_version`
- `state_kind`
- `producer`
- `game_id`
- `actor_id`
- `phase_id`
- `step`
- `trace_id`

### 2. 검증은 내부 전체가 아니라 경계에서만 강하게 한다

권장 검증 지점:

- 프론트 요청 ingress
  - `action_index`
- 엔진 -> 서비스 transition 경계
  - 지금 넘기는 상태가 `model-observation`인지 `rich-game-state`인지 명시
- replay logger 입력 경계
  - `ReplaySummaryStateV1`만 허용
- ML logger 입력 경계
  - `TransitionEnvelopeV1`만 허용

여기서 Pydantic v2를 쓰는 것이 가장 자연스럽다.

이유:
- 초기 경계에서 좋은 에러 메시지를 준다
- coercion 여부를 기록하기 쉽다
- 모든 내부 함수에 과하게 validation을 넣을 필요가 없다

### 3. replay summary 정규화를 raw observation 저장과 분리한다

권장 분리:

- raw observation:
  - ML/debugging 용도
  - 사람 읽기 commentary에 직접 쓰지 않음
- replay summary:
  - scalar 위주, 도메인 친화적
  - commentary와 replay UI 전용

즉 replay path는 먼저 `ReplaySummaryStateV1`를 만들어야 하고, commentary는 그 위에서만 돌게 해야 한다.

### 4. 부가 기능은 반드시 fail-open으로 만든다

액션 처리의 권위는 엔진이다.

권장 정책:
- 엔진 step 성공 -> 기본 gameplay 응답은 성공
- replay logging 실패 -> 에러 로그만 남기고 degraded replay로 계속 진행
- commentary 실패 -> `commentary=null` 또는 fallback 문자열로 계속 진행
- ML logging 실패 -> 구조화된 에러 로그만 남기고 계속 진행

이 정책은 우발적으로 생기면 안 되고, 설계 원칙으로 문서화되어야 한다.

### 5. contract observability 로그를 추가한다

매 transition마다 다음 정보를 구조화 로그로 남기는 것을 권장한다.

- `trace_id`
- `game_id`
- `actor_id`
- `phase_id`
- `action_index`
- `request_schema_version`
- `state_before_kind`
- `state_after_kind`
- `model_bundle_id`
- `artifact_fingerprint`
- `obs_dim`
- `action_mask_len`
- `summary_validation_status`
- `commentary_status`
- `ml_log_status`

MLOps 관점의 핵심은 이것이다.

- 값만 찍지 말고
- 그 값이 어떤 계약에 속하는지도 찍어야 한다

### 6. backend-model parity 로그를 운영 수준으로 끌어올린다

이미 `model_registry`에는 fingerprint 개념이 있다.

관련 코드:
- [backend/app/services/model_registry.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/model_registry.py:12)

이 개념을 운영 로그로 확장해야 한다.

기록해야 할 것:
- 기대하는 backend contract fingerprint
- 실제 model bundle fingerprint
- 실제 state semantic version
- mismatch 수준
  - `info`
  - `warning`
  - `error`

이렇게 해야 빨리 답할 수 있다.

- 백엔드가 잘못된 shape를 보냈는가?
- 모델 번들이 다른 env fingerprint를 기대하는가?
- replay가 잘못된 state kind를 먹었는가?

### 7. commentary delta 정책을 필드 타입별로 분리한다

commentary는 그냥 아무 값이나 빼는 함수가 아니다.

권장 delta 정책:

- 숫자 scalar:
  - 산술 delta
- 문자열 / enum:
  - `A -> B`
- list:
  - 길이 변화 또는 집합 차이
- counter dict:
  - key별 diff
- vector / tensor 유사 입력:
  - 사람용 commentary에서 직접 계산하지 않음
  - shape / 요약 통계만 사용

즉 commentary는 presentation layer여야지 raw numeric diff engine이면 안 된다.

## 경계별 검증 포인트

이 섹션은 “검증 로직을 프론트부터 백엔드, 엔진, 모델, logger까지 어디에 두어야 하는가?”에 대한 실행 기준이다.

원칙:
- 검증은 내부 모든 함수에 깔지 않는다.
- 대신 계약이 바뀌는 경계와 의미가 바뀌는 경계에 둔다.
- 각 경계마다 무엇을 검증할지, 무엇을 로그로 남길지, 실패 시 요청을 막을지 또는 degrade할지를 명시한다.

### 1. 프론트 액션 제출 직전 경계

목적:
- 명백히 잘못된 액션을 네트워크로 보내기 전에 차단한다.

검증 항목:
- `action_index`가 숫자이며 정수로 해석 가능한지
- 현재 화면이 들고 있는 `legal_actions` 또는 `action_mask`에서 허용된 액션인지
- 현재 플레이어 턴인지
- 현재 phase에서 버튼/입력 UI가 허용되는 액션군과 실제 제출 액션이 일치하는지

로그 항목:
- `trace_id`
- `game_id`
- `actor_id`
- `phase_id`
- `action_index`
- `frontend_state_version`
- `frontend_action_validation_status`

실패 정책:
- fail-closed
- 이 경계는 사용자 입력 오류를 조기에 막는 것이 목적이므로, 잘못된 액션은 제출하지 않는다.

### 2. API ingress 경계

목적:
- 프론트 payload를 `ActionRequestV1`로 고정한다.

검증 항목:
- 필수 필드 존재 여부
- 타입 일치 여부
- 허용 범위 여부
- 스키마 버전 존재 여부
- 예상하지 못한 필드 유입 여부

로그 항목:
- `trace_id`
- `request_schema_version`
- `validation_passed`
- `missing_fields`
- `unexpected_fields`
- `type_mismatch_fields`

실패 정책:
- fail-closed
- 액션 요청 자체가 계약을 만족하지 못하면 엔진까지 보내지 않는다.

### 3. GameService 사전 검증 경계

목적:
- 네트워크 payload가 맞더라도 현재 게임 문맥에서 불가능한 요청을 엔진으로 보내지 않는다.

검증 항목:
- 현재 actor가 실제 턴 주체인지
- 방 상태가 액션 허용 상태인지
- 액션이 현재 legal action set 안에 있는지
- control mode와 호출 경로가 일치하는지
- 사람 액션과 봇 액션이 같은 핵심 검증 규칙을 공유하는지

로그 항목:
- `trace_id`
- `game_id`
- `actor_id`
- `phase_id`
- `action_index`
- `legal_action_count`
- `turn_validation_status`
- `control_mode`

실패 정책:
- fail-closed
- 비즈니스 규칙 위반은 여기서 명시적으로 거절한다.

### 4. 엔진 step 반환 경계

목적:
- 엔진이 반환한 상태가 어떤 의미의 상태인지 즉시 확정한다.

검증 항목:
- 반환 상태의 `state_kind`
- `schema_version`
- `phase_id`, `current_player`, `terminated`, `truncated`의 최소 존재 여부
- `EngineWrapper.get_state()`가 `model-observation`인지 `rich-game-state`인지 명시적 라벨을 동반하는지

로그 항목:
- `trace_id`
- `state_before_kind`
- `state_after_kind`
- `phase_before`
- `phase_after`
- `terminated`
- `truncated`

실패 정책:
- fail-closed
- 이 경계가 모호하면 뒤의 모든 부가 기능이 잘못된 상태를 소비한다.

### 5. serializer / 프론트 outbound 경계

목적:
- 프론트로 나가는 상태는 반드시 `RichGameStateV1`로 고정한다.

검증 항목:
- 프론트가 렌더링에 기대하는 필수 필드 존재 여부
- observation 전용 필드가 UI state로 새어 나가지 않는지
- websocket과 HTTP 응답이 동일한 outbound contract를 따르는지
- `schema_version`, `state_kind`가 항상 포함되는지

로그 항목:
- `trace_id`
- `outbound_state_kind`
- `outbound_schema_version`
- `serializer_validation_status`
- `ws_delivery_status`

실패 정책:
- fail-closed
- UI를 깨뜨리는 잘못된 상태를 조용히 전송하지 않는다.

### 6. replay summary 정규화 경계

목적:
- replay/commentary는 raw observation이 아니라 `ReplaySummaryStateV1`만 소비하게 만든다.

검증 항목:
- 입력 `state_kind`가 `replay-summary`인지
- summary builder가 숫자, 문자열, 리스트, 카운터형 필드를 구분하는지
- one-hot, 벡터, `(1,)` 배열, 리스트형 카운트를 직접 산술 diff하지 않는지
- 사람 읽기 commentary에 필요한 최소 필드만 남겼는지

로그 항목:
- `trace_id`
- `summary_state_kind`
- `summary_validation_status`
- `commentary_status`
- `degraded_replay_used`

실패 정책:
- fail-open
- replay/commentary는 실패해도 gameplay 응답은 성공해야 한다.
- 단, 실패 원인과 degrade 여부는 반드시 구조화 로그로 남긴다.

### 7. ML logger 경계

목적:
- 학습/분석용 transition은 `TransitionEnvelopeV1`로 강제하고, gameplay와 분리한다.

검증 항목:
- `state_before_kind`, `state_after_kind`
- `schema_version`
- `trace_id`, `game_id`, `actor_id`
- `action_index`, `reward`, `done`의 존재 여부
- raw observation 사용 시 `obs_dim`, `action_mask_len`, fingerprint 존재 여부

로그 항목:
- `trace_id`
- `model_bundle_id`
- `artifact_fingerprint`
- `obs_dim`
- `action_mask_len`
- `ml_logging_status`
- `fallback_used`

실패 정책:
- fail-open
- ML logging sink 문제는 요청을 실패시키지 않는다.

### 8. 모델 runtime / bundle 로드 경계

목적:
- 백엔드가 기대하는 관측 계약과 모델 번들이 기대하는 계약이 같은지 실행 전에 확인한다.

검증 항목:
- `bundle_id`
- `artifact_fingerprint`
- `obs_dim`
- `action_dim`
- `schema_version`
- env fingerprint 또는 semantic contract fingerprint
- adapter가 기대하는 입력 key set과 실제 backend key set의 차이

로그 항목:
- `trace_id`
- `model_bundle_id`
- `artifact_fingerprint`
- `contract_fingerprint`
- `bundle_validation_status`
- `mismatch_level`

실패 정책:
- 로드 시점 mismatch는 fail-closed
- 단, runtime telemetry 기록 실패는 fail-open

### 9. websocket / 비동기 전파 경계

목적:
- HTTP 응답과 websocket broadcast가 서로 다른 state contract를 내보내지 않게 한다.

검증 항목:
- 동일 turn 결과에 대해 HTTP와 websocket payload의 `state_kind` 및 `schema_version`이 일치하는지
- suppress flag, callback 인자, broadcast 옵션이 현재 테스트 기대와 일치하는지
- 프론트가 특정 필드를 websocket 전용으로만 기대하지 않는지

로그 항목:
- `trace_id`
- `delivery_channel`
- `state_kind`
- `schema_version`
- `broadcast_status`

실패 정책:
- 핵심 상태 전달 실패는 fail-closed
- replay/commentary 부가 메시지 실패는 fail-open

## 구현 작업 분해

이 섹션의 목표는 “이 문서만 보고 바로 작업을 이어갈 수 있게 만드는 것”이다.

범위 포함:
- replay/commentary 500 제거
- 상태 semantic 계약 분리
- 경계 검증 도입
- Docker 기반 회귀 테스트 강화
- PPO 경로와 backend-model 계약 검증

범위 제외:
- 이벤트 소싱 기반 전체 재설계
- 프론트/백엔드 계약을 깨는 대규모 API 변경
- 기존 정상 기능 제거를 통한 단순화

### Task 1. 상태 의미 분류표와 envelope 계약을 먼저 고정한다

상태(2026-04-23):
- 부분 완료
- `contracts.py`에 공통 schema/state kind 상수를 추가했다.
- `EngineWrapper.get_state()`, `serialize_game_state_from_engine()`, `summarize_transition_state()`, `MLLogger.log_transition()`에 semantic label이 실제 반영되었다.
- 아직 `game_id`, `actor_id`, `phase_id`, `step`를 모든 envelope에 동일 규칙으로 강제하는 단일 모델 계층은 없다.

작업:
- `ActionRequestV1`, `ModelObservationV1`, `RichGameStateV1`, `ReplaySummaryStateV1`, `TransitionEnvelopeV1`의 필수 필드와 소유 경계를 문서/코드에 정의한다.
- 각 상태에 `schema_version`, `state_kind`, `trace_id`, `producer`를 붙이는 기준을 고정한다.

선행 테스트:
- 잘못된 `state_kind`가 replay 또는 ML logger에 들어갔을 때 명시적으로 거절되는 테스트를 먼저 작성한다.

완료 기준:
- 이후 구현자가 어떤 dict를 볼 때 “이건 무슨 상태인가?”를 shape가 아니라 label로 판단할 수 있다.

### Task 2. 액션 ingress와 GameService의 fail-closed 검증을 잠근다

상태(2026-04-23):
- 부분 완료
- API ingress는 `ActionRequestPayload`로 고정되었고 unexpected field는 fail-closed로 차단된다.
- turn validation과 legal action 검증은 기존 GameService 경로를 유지한다.
- `control_mode`, `request_schema_version`, `unexpected_fields` 등의 구조화 로그는 아직 부분적이다.

작업:
- API ingress에서 payload 계약을 고정한다.
- GameService에서 actor, 턴, legal action, control mode 검증을 명시화한다.

선행 테스트:
- 잘못된 `action_index`
- stale action mask
- 잘못된 actor의 액션 제출
- control mode 불일치

완료 기준:
- 비즈니스 규칙 위반은 엔진 이전에 일관되게 거절되고, replay/logger 쪽에서 뒤늦게 터지지 않는다.

### Task 3. 엔진 반환 상태와 UI 상태를 분리한다

상태(2026-04-23):
- 부분 완료
- `EngineWrapper.get_state()`는 이제 `model-observation` 라벨을 가진 상태를 반환한다.
- serializer outbound state는 `rich-game-state` 라벨을 가진다.
- 다만 잘못된 `state_kind`가 경계를 넘을 때 fail-closed validation을 강제하는 별도 모델 계층은 아직 없다.

작업:
- `EngineWrapper.get_state()`가 반환하는 상태 의미를 명시한다.
- UI serializer가 기대하는 상태와 model observation을 같은 경로로 재사용하지 않도록 경계를 세운다.

선행 테스트:
- observation state가 serializer나 replay summary로 직접 들어가면 실패하는 테스트
- rich state가 프론트 필수 필드를 유지하는 테스트

완료 기준:
- downstream 소비자는 `state_kind`를 보고 동작하며, shape 추측에 의존하지 않는다.

### Task 4. replay summary 정규화 계층을 도입한다

상태(2026-04-23):
- 완료
- replay summary는 `replay-summary.v1`로 정규화된다.
- singleton list, list 카운트, one-hot 기반 phase 표현이 summary/phase 계산에서 안전하게 해석된다.
- `TypeError: list - list`를 재현하던 회귀 테스트가 추가되었고 현재 통과한다.

작업:
- replay/commentary 입력은 반드시 `ReplaySummaryStateV1`만 받게 한다.
- raw observation을 사람용 summary로 직접 사용하지 않도록 정규화 계층을 둔다.
- commentary delta 정책을 타입별로 분리한다.

선행 테스트:
- `(1,)` 배열
- list 카운트
- one-hot 벡터
- scalar와 list가 섞인 transition
- summary builder가 벡터형 필드를 직접 `after - before` 하지 않는지 확인하는 회귀 테스트

완료 기준:
- 현재 `TypeError: list - list` 계열이 재발하지 않는다.

### Task 5. replay/commentary를 fail-open으로 전환한다

상태(2026-04-23):
- 완료
- replay entry 생성 실패, commentary 생성 실패, replay append 실패가 gameplay 응답을 더 이상 실패시키지 않는다.
- degraded replay 상태를 replay entry metadata와 warning 로그로 남긴다.

작업:
- replay write 실패
- commentary 생성 실패
- replay JSON 직렬화 실패

각 경우에 gameplay 응답은 유지하고, degraded 상태를 기록하는 정책을 적용한다.

선행 테스트:
- human action은 replay/commentary 실패가 있어도 성공 응답이어야 한다.
- bot action도 동일하게 성공 응답이어야 한다.

완료 기준:
- side effect 장애가 gameplay 500으로 번지지 않는다.

### Task 6. ML logger를 fail-open으로 전환하고 contract log를 표준화한다

상태(2026-04-23):
- 부분 완료
- ML logging sink 예외는 safe wrapper로 감싸서 gameplay를 막지 않게 했다.
- `transition-envelope.v1`, `trace_id`, `state_before_kind`, `state_after_kind`는 기록된다.
- fingerprint mismatch 수준을 `info/warning/error`로 표준화하는 운영 로그는 아직 남아 있다.

작업:
- ML logger 입력을 `TransitionEnvelopeV1`로 고정한다.
- validation 결과와 fingerprint 로그를 표준 필드로 남긴다.
- sink 실패가 gameplay를 막지 않게 한다.

선행 테스트:
- ML logger sink 예외
- validation 실패
- fingerprint mismatch warning

완료 기준:
- ML telemetry 문제는 관측 가능하지만 게임 진행은 유지된다.

### Task 7. 모델 bundle / adapter 계약 검증을 고정한다

상태(2026-04-23):
- 미완료
- canonical state / canonical action / adapter runtime 관련 기반 코드는 별도로 존재하지만, 이번 turn에서는 bundle parity를 gameplay trace와 직접 연결하지 않았다.

작업:
- backend가 기대하는 observation fingerprint와 bundle fingerprint를 비교한다.
- adapter runtime에 전달되는 key set, obs_dim, action_dim, bundle metadata를 검증한다.

선행 테스트:
- 잘못된 bundle fingerprint
- 잘못된 obs_dim
- legacy artifact가 새 adapter contract로 잘못 로드되는 경우

완료 기준:
- “모델이 깨졌는지”, “백엔드가 잘못 보내는지”, “bundle이 다른 환경 기준인지”를 로그 한 번으로 구분할 수 있다.

### Task 8. websocket / HTTP outbound contract를 일치시킨다

상태(2026-04-23):
- 부분 완료
- outbound rich state에 `schema_version`, `state_kind`가 추가되었다.
- websocket / serializer 인접 회귀 테스트는 통과했다.
- 채널별 contract equality를 구조화 로그 수준으로 강제하는 단계는 아직 남아 있다.

작업:
- 동일 턴 결과에 대해 websocket과 HTTP가 같은 `state_kind`와 `schema_version`을 갖도록 고정한다.
- callback 인자와 broadcast 옵션의 회귀를 잠근다.

선행 테스트:
- websocket delivery contract
- bot routing contract
- callback 옵션 회귀 케이스

완료 기준:
- 채널별로 다른 상태 계약이 흘러나가지 않는다.

### Task 9. 회귀 테스트를 현재 실패 지점 중심으로 묶는다

상태(2026-04-23):
- 부분 완료
- 직접 장애 경로와 serializer/ws 인접 회귀는 Docker에서 잠갔다.
- 새로 추가/확대한 대상:
  - `tests/test_replay_logger.py`
  - `tests/test_ml_logger.py`
  - `tests/test_game_action.py`
  - `tests/test_game_service_side_effect_fail_open.py`
- adapter/bundle 전체 묶음까지 이번 turn에서 재실행하지는 않았다.

작업:
- import 확인용 테스트가 아니라 실제 장애 경로를 재현하는 테스트를 우선 추가한다.
- 변경점이 걸친 모듈별로 targeted suite와 broader suite를 분리한다.

우선 대상 테스트 파일:
- `tests/test_replay_logger.py`
- `tests/test_replay_logging_integration.py`
- `tests/test_replay_logger_rich_state.py`
- `tests/test_ml_logger.py`
- `tests/test_game_service_turn_validation.py`
- `tests/test_priority2_bot_routing_contract.py`
- `tests/test_priority2_ws_delivery_contract.py`
- `tests/test_adapter_runtime.py`
- `tests/test_bundle_integration.py`
- `tests/test_serving_ppo_wrapper.py`

완료 기준:
- 현재 장애점, 변경점, 비즈니스 엣지 케이스가 모두 Docker 회귀 테스트로 잠긴다.

### Task 10. 넓히기 전에 작은 경계부터 닫는다

상태(2026-04-23):
- 진행 중
- 이번 turn에서 실제 완료한 순서:
  1. replay/commentary 장애 재현 테스트 추가
  2. summary 정규화 반영
  3. replay/commentary fail-open 반영
  4. ML logger fail-open 및 transition metadata 반영
  5. engine / serializer state semantic label 반영
  6. serializer / websocket 인접 회귀 재검증
- PPO bundle parity를 gameplay trace와 직접 연결하는 단계는 다음 작업으로 남는다.

작업 순서:
1. replay/commentary 현재 장애 재현 테스트 추가
2. summary 정규화 및 fail-open 반영
3. ML logger fail-open 반영
4. 엔진 상태 semantic label 추가
5. serializer / websocket outbound 계약 고정
6. PPO bundle parity 검증 연결
7. 전체 관련 suite 재실행

완료 기준:
- 한 번에 넓게 고치지 않고, 매 단계에서 회귀 위험을 줄이며 전진한다.

## Docker 기반 TDD 원칙

이 작업에서는 테스트를 “로컬 파이썬에서 대충 통과”시키는 것이 아니라, 운영과 가장 가까운 Docker 환경에서 잠가야 한다.

### 원칙 1. 코드보다 failing test를 먼저 만든다

- 현재 500을 재현하는 테스트가 먼저 있어야 한다.
- replay/commentary, ML logger, websocket delivery, bot routing, PPO adapter contract처럼 실제 장애 경로를 먼저 붉게 만든다.
- import 가능 여부나 단순 모듈 로드 성공만으로는 변경 타당성을 증명하지 못한다.

### 원칙 2. 테스트는 항상 Docker에서 실행한다

권장 방식:
- backend 관련 테스트는 `docker compose exec backend pytest ...`
- frontend 계약 회귀가 필요하면 `docker compose exec frontend ...`

이유:
- 패키지 버전, OS 차이, 런타임 의존성, 경로 해석 차이가 실제 장애를 가릴 수 있기 때문이다.

### 원칙 3. 테스트는 “변경점 + 현재 에러 지점 + 비즈니스 엣지 케이스”를 우선한다

필수 우선순위:
- 현재 `list - list` 500 재현
- replay/commentary 실패가 gameplay를 죽이지 않는지
- bot action도 같은 규칙으로 보호되는지
- observation/list/vector 필드가 섞여도 summary가 안전한지
- 잘못된 state kind가 replay/ML logger에 들어왔을 때 즉시 감지되는지
- websocket/HTTP outbound contract가 어긋나지 않는지
- PPO bundle parity와 adapter inference가 실제 계약을 유지하는지

### 원칙 4. 테스트 범위는 단계적으로 넓힌다

권장 순서:
1. 변경 대상 모듈의 targeted test를 Docker에서 먼저 실행
2. 관련 integration test 실행
3. bot / websocket / PPO contract regression 실행
4. 마지막에 broader suite 실행

### 원칙 5. 테스트 통과를 위해 정상 기능을 제거하지 않는다

- working path를 삭제하거나 bypass해서 녹색을 만드는 것은 금지한다.
- replay/commentary를 영구 비활성화하거나, validation 자체를 제거하거나, legal action 검증을 느슨하게 하는 방식은 허용하지 않는다.
- 수정은 기존 기능을 유지한 채 오류 전파만 줄이는 방향이어야 한다.

### 권장 Docker 테스트 묶음

현재 문서 기준의 우선 실행 예시는 다음과 같다.

1. 현재 장애 재현 및 직접 수정 대상

```bash
docker compose exec backend pytest \
  tests/test_replay_logger.py \
  tests/test_replay_logging_integration.py \
  tests/test_replay_logger_rich_state.py \
  tests/test_ml_logger.py \
  -q
```

2. 게임 서비스 / 채널 / 전파 회귀

```bash
docker compose exec backend pytest \
  tests/test_game_service_turn_validation.py \
  tests/test_priority2_bot_routing_contract.py \
  tests/test_priority2_ws_delivery_contract.py \
  tests/test_channel_bot_endpoint.py \
  -q
```

3. 모델 / adapter / bundle 계약 회귀

```bash
docker compose exec backend pytest \
  tests/test_adapter_runtime.py \
  tests/test_model_registry_bundle.py \
  tests/test_model_registry_bootstrap.py \
  tests/test_agent_registry_bundle.py \
  tests/test_bundle_integration.py \
  tests/test_serving_ppo_wrapper.py \
  tests/test_bot_service_adapter_routing.py \
  -q
```

4. 정리 단계의 broader contract suite

```bash
docker compose exec backend pytest \
  tests/test_canonical_state.py \
  tests/test_canonical_action.py \
  tests/test_replay_logger.py \
  tests/test_replay_logging_integration.py \
  tests/test_ml_logger.py \
  tests/test_adapter_runtime.py \
  tests/test_bundle_integration.py \
  tests/test_priority2_bot_routing_contract.py \
  tests/test_priority2_ws_delivery_contract.py \
  -q
```

## PPO 테스트 모델 적용 원칙

현재 `pr_env.py` 기준 PPO 계약 검증에서 우선 참조해야 하는 로컬 체크포인트는 다음 파일이다.

- [PPO_PR_Local_20260405_205030_step_81920.pth](/Users/seoungmun/Documents/agent_dev/castest/castone/models/ppo_checkpoints/PPO_PR_Local_20260405_205030_step_81920.pth:1)

원칙:
- PPO 관련 contract test, adapter test, bundle integration test는 가능하면 위 체크포인트를 기준으로 검증한다.
- 임시 smoke artifact나 다른 action-value 계열 모델이 아니라, 현재 `pr_env` 기준으로 학습된 PPO artifact를 기준선으로 삼는다.
- backend가 bundle 기반 경로를 기대한다면, 이 체크포인트에서 생성된 bundle을 `PPO_BUNDLE_DIR`로 주입하는 방식을 우선 채택한다.
- 테스트 harness는 위 체크포인트 또는 그로부터 생성된 bundle이 없을 경우, “테스트 환경 미구성”을 명시적으로 보고하고 조용히 다른 legacy artifact로 대체하지 않는다.
- `PuCo_RL/models/ppo_checkpoints/...` 아래의 smoke bundle은 빠른 부트스트랩이나 임시 검증에는 사용할 수 있지만, 제품 수준 계약 검증의 기준선과 혼용하지 않는다.

적용 이유:
- 사용자가 확인하고 싶은 것은 “새 서빙 경로가 현재 `pr_env` 기반 PPO 모델을 깨뜨리지 않는가”이지, “아무 모델 하나가 우연히 돌기만 하는가”가 아니다.

## 비파괴 수정 원칙

이번 작업의 목표는 기능 축소가 아니라, 현재 기능을 유지하면서 오류 전파를 없애는 것이다.

따라서 다음 원칙을 유지한다.

- 이미 정상 동작 중인 게임 규칙, 턴 검증, legal action 계산, websocket 전달, serializer 출력은 임의로 제거하지 않는다.
- 부가 기능이 문제를 일으킨다고 해서 해당 기능을 영구 비활성화하거나 삭제하지 않는다.
- `Any` 확대, validation 제거, blanket try/except로 의미를 숨기는 방식은 최후의 응급조치가 아니면 채택하지 않는다.
- 기존 호출 경로를 없애는 대신, 경계 검증, 상태 정규화, fail-open 분리를 추가하는 방향으로 수정한다.
- 회귀가 없는 것이 확인되기 전에는 legacy 경로를 섣불리 제거하지 않는다.
- “쉬운 길” 때문에 제품에서 이미 문제를 일으키지 않던 로직을 없애서 테스트를 통과시키는 방식은 금지한다.

## MLOps 관점에서 정합성 로그를 어떻게 찍어야 하는가

이 섹션은 질문

“백엔드는 로그를 찍어서 오류를 해결했는데, MLOps는 Pydantic이나 다른 걸로 데이터 정합성 추적 로그를 어떻게 찍는가?”

에 대한 직접 답이다.

### 기본 원칙

1. 경계에서 검증한다
- request ingress
- feature engineering output
- model input construction
- model output decoding
- artifact loading
- logging sink

2. 값보다 계약 판정을 로그로 남긴다
- `validation_passed`
- `validation_failed`
- `coerced_fields`
- `missing_fields`
- `unexpected_fields`
- `type_mismatch_fields`

3. 큰 payload는 signature만 남긴다
- top-level key 목록
- field count
- 배열 shape
- dtype
- hash
- min/max

4. lineage를 함께 남긴다
- model artifact
- bundle id
- schema version
- env fingerprint
- trace id

5. redaction 정책을 명시한다
- raw payload 전체 dump는 지양
- 샘플 필드 또는 해시된 snapshot 사용

### Pydantic을 어디에 쓰는 게 맞는가

Pydantic은 다음 용도에 가장 잘 맞는다.

- 선언적 계약 정의
- coercion 감지
- 좋은 에러 메시지
- 경계에서의 구조 검증

반대로 Pydantic을 이렇게 쓰면 안 된다.

- 모든 내부 객체를 무조건 감싸는 용도
- state semantic 설계를 대신하는 용도

즉, Pydantic은 “계약 실행기”이지 “설계 대체물”이 아니다.

### transition당 최소 권장 MLOps 로그 필드

다음 정도는 최소 권장 세트다.

```text
trace_id
game_id
actor_id
phase_id
action_index
request_schema_version
state_before_kind
state_before_schema_version
state_after_kind
state_after_schema_version
model_bundle_id
artifact_fingerprint
obs_dim
action_mask_len
validation_status
validation_errors
fallback_used
replay_logging_status
ml_logging_status
```

## 검증 계획

### 1단계. 폭발 반경 차단

- replay/commentary 실패가 gameplay 응답을 실패시키지 않게 한다
- degraded mode 로그를 명시적으로 남긴다

### 2단계. state kind mismatch 계측

- replay와 ML logger 입력에 `state_kind`를 붙인다
- replay가 `model-observation`을 직접 받는 케이스를 카운트한다

### 3단계. 경계 계약 고정

- `ActionRequestV1`
- `ReplaySummaryStateV1`
- `TransitionEnvelopeV1`

이 세 경계를 엄격히 정의한다.

### 4단계. 회귀 테스트 추가

- commentary 생성이 실패해도 human action request는 성공해야 한다
- replay write가 실패해도 bot action request는 성공해야 한다
- replay logger는 observation payload를 summary payload 대신 받으면 명시적으로 거절해야 한다
- schema mismatch 로그에 trace id와 state kind가 반드시 찍혀야 한다

## 즉시 트리아지 권고

가장 빠르고 안전한 대응 순서는 다음이다.

1. 이번 500을 “프론트 액션 요청 실패”가 아니라 “replay/commentary 계약 실패”로 분류한다.
2. model observation과 replay summary를 분리한다.
3. replay/commentary와 ML logging을 non-fatal로 만든다.
4. request와 transition 경계에 스키마를 둔다.
5. semantic label과 fingerprint가 포함된 contract log를 추가한다.

## 결정 로그

결정:
- 현재 500의 1차 원인은 replay/commentary 경로로 본다.
이유:
- 엔진 step이 완료된 뒤 예외가 발생했다.

결정:
- 단순 arithmetic patch보다 boundary schema 설계를 권장한다.
이유:
- 이번 오류는 상태 의미 혼선을 드러내는 구조적 문제다.

결정:
- side effect는 fail-open 정책으로 가야 한다.
이유:
- replay와 ML logging이 gameplay를 죽이면 안 된다.

결정:
- Pydantic은 경계에서만 강하게 쓰는 것이 적절하다.
이유:
- 엄격함과 실행 비용의 균형이 가장 좋다.

## 남은 질문

- replay commentary는 observation 기반이 아니라 엔진 도메인 상태 기반으로 다시 설계해야 하는가?
- replay와 ML logging이 같은 transition envelope를 공유할 것인가, 분리할 것인가?
- 프론트 outbound state에도 schema version을 항상 실어야 하는가?
- 어떤 mismatch가 즉시 알람 대상이어야 하는가?
  - gameplay failure
  - replay degraded
  - ML log degraded
  - parity mismatch

## 최종 제안

이번 로그가 직접 보여주는 것은 “프론트 요청 계약이 깨졌다”가 아니다.

더 정확히는 다음 경계가 깨진 것이다.

- 모델 observation 의미
- replay summary 의미

따라서 가장 적절한 다음 설계는 아래와 같다.

- 계약 경계를 스키마로 고정
- payload에 semantic label 부여
- replay 입력 정규화
- side effect fail-open
- lineage와 fingerprint를 포함한 MLOps형 contract log 도입
