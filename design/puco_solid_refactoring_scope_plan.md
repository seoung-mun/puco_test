# PuCo_RL 결합 축소 1차 리팩토링 계획서

> Deprecated: 초기 integration/dual-mode scope 문서다.
> 현재는 `design/2026-04-08_engine_cutover_task_breakdown.md`,
> `design/2026-04-08_engine_cutover_batch_f_cleanup.md`, `contract.md` 를 기준으로 본다.

## Summary

- 작성 대상 문서: `design/puco_solid_refactoring_scope_plan.md`
- 목표: `PuCo_RL` 변경이 `backend` 내부 경계층에서 흡수되도록 만들어, 엔진/모델/action-space 변경이 서비스 계층과 프론트까지 연쇄 수정되지 않게 한다.
- 1차 범위: `backend` 경계 분리 우선. 프론트는 기존 계약을 깨지 않되, 이후 서버 주도 계약으로 옮길 수 있도록 백엔드가 의미 기반 인터페이스를 추가 제공한다.
- 비범위: `PuCo_RL` 엔진 규칙 자체 재작성, 프론트 전면 개편, 학습 파이프라인 재설계.

## Key Changes

### 1. 경계 규칙 고정

- `PuCo_RL` 직접 import와 `sys.path` 조작은 신규 통합 경계 패키지로만 제한한다.
- 허용 위치는 `backend/app/integrations/puco/`와 기존 `backend/app/engine_wrapper/wrapper.py`로 고정한다.
- `backend/app/services/`, `backend/app/api/`, `backend/app/schemas/`에서는 `configs.constants`, `env.*`, `agents.*`, `utils.*`를 직접 참조하지 않게 한다.

### 2. Anti-Corruption Layer 도입

- `backend/app/integrations/puco/`에 백엔드 전용 적응 계층을 만든다.
- 이 계층이 담당할 책임:
  - 엔진 상수/enum/action index를 백엔드 의미 객체로 변환
  - `PuertoRicoEnv`/모델 wrapper/Mayor 전략 확장을 PuCo 전용 구현으로 캡슐화
  - 엔진 상태를 백엔드 소유 `GameSnapshot`으로 변환
  - semantic action 목록과 legacy `action_mask`를 동시에 생산
- 서비스 계층은 엔진이 아니라 `GameEnginePort`, `GameSnapshot`, `ActionCatalog`, `BotPolicyPort`만 사용한다.

### 3. 서비스 분리 기준

- `state_serializer`는 두 단계로 분리한다.
  - integration mapper: 엔진 객체 -> `GameSnapshot`
  - presenter: `GameSnapshot` -> API/WS용 `GameState`
- `action_translator`는 raw index 계산기가 아니라 `ActionCatalog` 조회기로 바꾼다.
- `mayor_orchestrator`와 `mayor_strategy_adapter`는 semantic slot 계획을 다루고, `72-75` 변환은 PuCo adapter 내부에서만 수행한다.
- `bot_service`, `agent_registry`, `model_registry`는 generic service + PuCo 구현으로 분리한다. 모델 아키텍처/obs_dim/action_dim 지식은 integration layer에 남긴다.
- legacy API는 유지하되 신규 로직을 직접 갖지 않고 presenter/adapter를 경유하는 thin compatibility layer로 축소한다.

### 4. 프론트와의 계약 방향

- 1차에서는 기존 `GameState`, `action_mask`, `action_index`를 유지한다.
- 동시에 additive contract로 `available_actions`를 `/start`, `/action`, WebSocket `STATE_UPDATE` 응답에 추가한다.
- `available_actions`의 표준 shape는 아래로 고정한다.
  - `type`: stable semantic action 이름
  - `engine_action_index`: 현재 엔진 index
  - `enabled`: 현재 가능 여부
  - `target`: role/good/building/ship 등의 의미 값
  - `slot_id`: Mayor 등 슬롯 기반 액션 식별자
  - `amount`: 수량 기반 액션 값
- 프론트 1차 목표는 현행 유지다. 다만 2차에서 `frontend/src/App.tsx`의 `channelActionIndex` 제거가 가능하도록 서버 데이터가 완전해야 한다.

## Public APIs / Interfaces / Types

- 신규 내부 포트:
  - `GameEnginePort`
  - `BotPolicyPort`
  - `ActionCatalogProvider`
- 신규 내부 DTO:
  - `GameSnapshot`
  - `ActionOption`
  - `MayorPlacementPlan`
- 기존 외부 API 변경:
  - breaking change 없음
  - `state.action_mask` 유지
  - top-level `action_mask` 유지
  - `available_actions: ActionOption[]` 추가
- 안정성 규칙:
  - 프론트는 index 의미를 신뢰하지 않고, 장기적으로는 `available_actions`와 서버가 내려준 `action_index`만 사용한다.
  - action index 재배치는 integration layer와 해당 계약 테스트 수정만으로 끝나야 한다.

## Test Plan

- 구조 테스트:
  - `backend/app/services/`와 `backend/app/api/`에 `PuCo_RL` 직접 import가 없는지 검사하는 import-guard 테스트 추가
  - `sys.path` 조작 금지 위치 검사
- 계약 테스트:
  - `action_mask`와 `available_actions.engine_action_index`가 같은 가능 집합을 표현하는지 검증
  - `/start`, `/action`, `/mayor-distribute`, WS `STATE_UPDATE`가 기존 shape를 유지하는지 검증
  - legacy API 응답도 동일 presenter를 타는지 검증
- 기능 테스트:
  - role selection, settler, mayor, craftsman, captain, discard phase별 semantic action catalog 스냅샷 테스트
  - Mayor slot catalog와 sequential action 변환 테스트
  - bot 추론 경로에서 obs_dim/action_dim/phase handling이 기존과 동일하게 동작하는지 테스트
- 회귀 기준:
  - `PuCo_RL` action index 변경 시 수정 파일이 integration layer와 그 테스트에 국한되는지 확인
  - 프론트 smoke test는 기존 렌더링이 additive field 때문에 깨지지 않음을 확인

## Assumptions And Defaults

- 1차는 `backend` 경계 분리에 집중하고 프론트 대수술은 하지 않는다.
- `frontend`는 당장 `available_actions`를 소비하지 않아도 되며, 기존 `GameState` 기반 렌더링을 유지한다.
- legacy API는 폐기하지 않고 동작만 보존한다. 신규 기능은 channel API 기준으로만 확장한다.
- `PuCo_RL` 내부 엔진/학습 코드 수정은 이 문서의 직접 범위가 아니다. 필요한 경우 integration layer 요구사항에 맞춘 최소 변경만 별도 작업으로 분리한다.
- 현재 진행 중인 Mayor 관련 변경 사항은 유지한 채, 그 주변 결합만 줄이는 방향으로 계획을 작성한다.
