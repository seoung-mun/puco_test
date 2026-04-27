# Action Index Contract Fix — 설계 명세

작성일: 2026-04-27
저자: Claude (Seoung-mun 협업)
상위 문서: `docs/2026-04-21-error-log-contract-design-report.md`, `docs/error_report/04_23_증상형.Md`
관련 메모리: `feedback_testing.md` (도커에서만 테스트), `project_model_files_pre_refactor.md`

## 1. 배경

`error_logs.md` (2026-04-27 캡처) 기준 사용자 직접 플레이 환경에서 다음 두 가지가 동시에 보고되었다.

- "옥수수를 골랐지만 UI에는 커피로 표시되어 농지에 커피가 저장됨"
- "시장 페이즈에서도 누른 위치와 다른 블록이 선택됨"

또한 동일 로그에서 `POST /api/puco/game/{id}/action` → `400 Bad Request`가 반복되고, 이전 04-21 보고서에서 닫은 replay/commentary 500과는 결이 다르다.

이 명세는 **사람 settler/mayor 액션 매핑이 깨진 원인을 contract 수준에서 고정**하는 범위만 다룬다. PPO bundle obs_dim mismatch, WS/auth 401, COOP 경고는 별도 workstream이다.

## 2. 진단 (코드 근거)

세 계층의 매핑이 서로 다르다.

| 계층 | 위치 | 매핑 의미 |
| --- | --- | --- |
| Frontend 전송 | `frontend/src/App.tsx:777-778`, `frontend/src/components/MayorSequentialPanel.tsx:70,95` | backend가 보낸 `action_index`를 그대로 channel API로 송신 |
| Backend serializer | `backend/app/services/state_serializer_support.py:160`, `backend/app/services/state_serializer.py:_build_mayor_meta` | **위치 기반 (positional)** `8 + i`, `legal_island_slots`에 raw island position(0–11) |
| Engine | `PuCo_RL/env/pr_env.py:285,335,347`, mask: `mask[8+tile.value]`, `mask[120+tile.value]`, `mask[140+building.value]` | **의미 기반 (semantic)** Good/TileType/BuildingType enum value |

증상별 매핑 차:

- Settler: face_up이 `[corn, coffee, indigo]`이면 corn 클릭 시 `action_index=8` 전송 → 엔진 `TileType(0)=COFFEE` 적용. (i=0 vs Good.COFFEE.value=0)
- Mayor Island: 사용자가 island slot idx=0(예: corn) 클릭 → `action_index=120` → 엔진 `TileType(0)=COFFEE` → 엔진은 `island_board`에서 첫 번째 미사용 coffee를 찾음.
- Mayor City: 사용자가 city slot engine_idx=2 클릭 → `action_index=142` → 엔진 `BuildingType(2)`로 해석.

400 Bad Request의 직접 원인은 mismatch된 `action_index`가 `mask`에 set되지 않아 `GameService.process_action` 검증에서 거절되는 것이다.

봇은 mask에서 직접 의미 인덱스를 고르므로 영향 없음. 사람 액션만 깨진다.

## 3. 채택 접근: explicit dual-field + ingress canonical guard

### 3.1 핵심 원칙

- Backend는 outbound rich state에 **표시용 위치(`display_position`)** 와 **엔진용 의미 인덱스(`engine_action_index`)** 를 함께 실어 보낸다.
- Frontend는 클릭 시 **`engine_action_index`만** 전송한다. `action_index` 단일 필드는 `engine_action_index`와 동일 값으로 둔다 (기존 호환).
- Frontend는 클릭한 의미 식별자(`canonical_id`)를 ingress payload에 함께 실어 보낸다.
- Backend ingress는 `canonical_id`와 `action_index`의 의미가 일치하지 않으면 **fail-closed로 422 거절** — 단, `canonical_id`는 옵셔널이며 미제공 시 검증을 건너뛴다 (기존 클라이언트 호환).
- 이 모든 결정은 transition envelope에 MLOps 로그로 남는다.

### 3.2 변경 대상

#### Backend

- `backend/app/services/state_serializer_support.py:155-163` (`face_up` 빌더)
  - `action_index = 8 + tile.value` (semantic)로 교체
  - `engine_action_index`, `display_position` 필드를 같이 추가 (둘 다 명시)
  - `canonical_id`(`settler:tile_type:{name}` 또는 `settler:quarry`) 추가
  - quarry는 `engine_action_index=13`로 정식화. 14 alias는 동봉하지 않는다 (사용자 승인됨, 2026-04-27).
- `backend/app/services/state_serializer.py:_build_mayor_meta`
  - `mayor_legal_island_slots`, `mayor_legal_city_slots`는 **UI 표시용**으로 유지
  - 새 필드: `mayor_island_actions` (각 항목에 `display_position`, `engine_action_index=120+tile.value`, `canonical_id`, `tile_name`)
  - 새 필드: `mayor_city_actions` (각 항목에 `display_position`, `engine_action_index=140+building.value`, `canonical_id`, `building_name`)
  - **주의**: 같은 tile_type/building_type에 슬롯이 두 개 이상이면 의미적으로는 같은 액션이다. 이 경우 frontend는 사용자에게 슬롯 두 개를 보여주되 둘 다 같은 `engine_action_index`로 매핑된다는 사실을 design level에서 수용한다 (엔진 자체가 첫 번째 미사용 슬롯을 선택; `pr_env.py:336-340`).
- `backend/app/schemas/game.py:9` (`ActionRequestPayload`)
  - 옵셔널 `canonical_id: Optional[str] = None` 추가 (기존 `extra="forbid"` 유지)
- `backend/app/api/channel/game.py:60-75` (perform_action)
  - `canonical_id`가 제공되면 `canonical_action.py._describe_action(action_int, state)`의 결과와 비교 → mismatch 시 `HTTPException(422, "canonical_id mismatch")`
  - `[ACTION_TRACE]` 로그에 `canonical_id`, `decoded_meaning`, `match` 필드 추가

#### Frontend

- `frontend/src/App.tsx:777-778` (`doSettlePlantation`)
  - `entry.action_index` 대신 `entry.engine_action_index` 사용. 동시에 `entry.canonical_id`를 ingress payload에 동봉.
- `frontend/src/App.tsx:485-499` (`channelAction`)
  - signature 확장: `channelAction(actionIndex: number, canonicalId?: string)` — payload에 `canonical_id` 동봉
- `frontend/src/components/MayorSequentialPanel.tsx:69-83, 88-112`
  - `meta.mayor_island_actions`, `meta.mayor_city_actions`에서 `engine_action_index`/`canonical_id`를 직접 사용
  - 기존 `mayor_legal_island_slots`/`mayor_legal_city_slots`는 표시 위치(`display_position`) 비교용으로만 사용
- `frontend/src/types/gameState.ts`: 새 필드 타입 추가
- `frontend/src/components/AvailablePlantations.tsx`: tile 객체 type 확장 (현재는 `string | {type, action_index}` 양쪽 지원하므로 추가는 type-safe하게 가능)

### 3.3 Backwards compatibility

- 기존 `action_index` 단일 필드는 **`engine_action_index`와 동일 값**으로 outbound에 그대로 둔다. 신규 frontend가 배포되기 전 캐시된 client가 있어도 의미적으로 맞는 인덱스를 받게 된다.
- 즉 이 변경 자체로 frontend 변경 없이도 settler/mayor 의미 mismatch가 사라진다. frontend 변경은 canonical_id guard와 명세 통일 목적.

## 4. MLOps observability 필드

### 4.1 transition envelope 추가 필드 (`backend/app/services/ml_logger.py`)

기존 `transition-envelope.v1` 스키마에 다음을 추가한다.

- `submitted_action_index: int`
- `submitted_canonical_id: Optional[str]` — frontend가 보낸 값
- `decoded_canonical_id: str` — `_describe_action(submitted_action_index, state).canonical_id`
- `canonical_id_match: Optional[bool]` — None when not provided, True/False otherwise
- `state_before_phase_id: int`
- `actor_kind: Literal["human", "bot"]`

### 4.2 ingress structured log (`backend/app/api/channel/game.py`)

`[ACTION_TRACE] channel_action_request`에 다음을 추가한다.

- `submitted_canonical_id`
- `decoded_canonical_id`
- `match` (true/false/missing)
- `request_schema_version`

### 4.3 mismatch 정책

- `canonical_id` 미제공 → match 필드는 `missing`. 그대로 처리, replay/log에는 기록.
- `canonical_id` 제공 + 일치 → 처리.
- `canonical_id` 제공 + 불일치 → **fail-closed 422**, body에 `decoded_canonical_id`와 `submitted_canonical_id` 포함. 이 경우는 frontend 버전 mismatch이거나 race이므로 즉시 차단해야 한다.

## 5. TDD 계획 (Docker pytest)

선행 failing test (코드 변경 전):

1. `backend/tests/test_state_serializer_action_index.py`에 추가:
   - `test_face_up_action_index_uses_tile_type_value` — face_up이 `[CORN, COFFEE]`일 때 corn entry의 `engine_action_index == 10` (8 + Good.CORN.value=2)
2. `backend/tests/` 신규 `test_mayor_meta_action_index.py`:
   - `test_mayor_island_actions_use_tile_type_value` — `mayor_island_actions`의 entry가 `120 + tile.value`
   - `test_mayor_city_actions_use_building_type_value` — `mayor_city_actions`의 entry가 `140 + building.value`
3. `backend/tests/test_game_action.py`에 추가:
   - `test_action_request_canonical_id_mismatch_returns_422` — payload에 mismatched canonical_id 보내면 422 + body에 양쪽 값 포함
   - `test_action_request_canonical_id_match_succeeds` — 일치 시 정상 처리
   - `test_action_request_canonical_id_omitted_succeeds` — 미제공 시 정상 처리
4. `backend/tests/test_ml_logger.py`에 추가:
   - `test_transition_envelope_includes_canonical_decoded` — ml log에 `decoded_canonical_id`, `canonical_id_match` 기록 확인
5. `frontend/src/__tests__/App.settler-corn.test.tsx` (신규):
   - corn 클릭 시 `channelAction`이 받는 `actionIndex`가 `engine_action_index` 값과 같음
   - payload에 `canonical_id`가 동봉됨

각 테스트가 RED 상태임을 먼저 Docker에서 확인 후 구현 진행.

## 6. 검증 (Docker)

구현 완료 후 다음 묶음을 통과해야 한다.

```bash
docker compose exec backend pytest \
  tests/test_state_serializer_action_index.py \
  tests/test_mayor_meta_action_index.py \
  tests/test_game_action.py \
  tests/test_ml_logger.py \
  tests/test_replay_logger.py \
  tests/test_priority2_ws_delivery_contract.py \
  tests/test_phase_action_edge_cases.py \
  -q

docker compose exec frontend npx vitest run \
  src/__tests__/App.settler-corn.test.tsx \
  src/components/__tests__/MayorSequentialPanel.test.tsx
```

추가로 04-23 메모의 1차 회귀 묶음도 함께 재실행한다 (`tests/test_game_ws_auth_contract.py`, `tests/test_priority2_ws_delivery_contract.py`).

## 7. 범위 외

- PPO bundle obs_dim mismatch (210 vs 293) — 04-21 Task 7, 04-23 Task E. 별도 PR.
- `/api/puco/auth/me` 401 + COOP 경고. 별도 triage.
- WS reconnect loop 자체 — canonical guard 도입 후 액션이 통과하기 시작하면 재현 빈도가 낮아질 가능성이 있으나, root cause는 별도 추적.
- Mayor 페이즈에서 같은 tile_type 슬롯이 둘 이상일 때 사용자 의도한 슬롯을 정확히 지정하는 기능. 엔진이 의미 단위로만 받도록 설계되어 있어 상위 변경. 차후 별도 design.
- 이벤트 소싱 / 전체 스키마 재설계.

## 8. 결정 로그

- **Outbound 호환을 위해 `action_index` 필드 유지**: 신구 클라이언트 모두 의미적으로 맞는 값을 받게 된다. 단, 신규 클라이언트는 `engine_action_index`를 명시적으로 사용하도록 마이그레이션.
- **canonical_id를 옵셔널로**: 기존 클라이언트와 e2e 테스트가 즉시 깨지지 않게 하기 위함. 단, 신규 클라이언트는 항상 동봉하도록 권장.
- **mismatch는 422 fail-closed**: 04-21 보고서의 "API ingress 경계는 fail-closed" 원칙과 일치.
- **Mayor 슬롯 disambiguation은 범위 외**: 엔진 자체 한계라 contract layer에서 풀 수 없음. 이번 fix는 "타입 일치 보장"까지만.

## 9. 작업 분해 (writing-plans 단계에서 상세화)

대략의 순서. 실제 plan은 `docs/superpowers/plans/`에 별도 작성.

1. failing tests 추가 (backend 4개 파일, frontend 1개 파일) — Docker에서 RED 확인
2. `contracts.py`에 `CANONICAL_ID_REQUEST_FIELD` 등 상수 추가 (필요 시)
3. backend serializer 수정 (`state_serializer_support.py`, `state_serializer.py`)
4. backend ingress validator + 422 거절 로직 (`game.py`, `schemas/game.py`)
5. ML logger 필드 확장 (`ml_logger.py`)
6. frontend types + `App.tsx` + `MayorSequentialPanel.tsx`
7. Docker pytest + vitest 통과 확인
8. 04-23 1차 회귀 묶음 재실행

## 10. 결정된 사항 (2026-04-27)

- **Quarry는 `engine_action_index=13` 단독.** 기존 14 호출은 `App.tsx:773-775`에서 14 → 13으로 교체. 14 alias는 outbound state에 포함하지 않는다.
- **개발 브랜치는 `refactor/adapter`.** 본 spec과 후속 구현은 이 브랜치에서 commit한다. push 및 다른 브랜치로의 머지는 사용자 검증 후에만 수행.
- **테스트는 Docker에서만 실행.** `docker compose exec backend pytest …`, `docker compose exec frontend npx vitest …` 외 경로는 사용하지 않는다.

## 11. 남은 질문

- `display_position` 필드명: 기존 frontend 코드가 `action_index`를 위치 의미로 의존한 부분이 있는지 마이그레이션 시 확인 필요.
