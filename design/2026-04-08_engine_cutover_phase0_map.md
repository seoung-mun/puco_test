# Engine Cutover Phase 0 Map

작성일: 2026-04-08  
기준 문서:
- `design/2026-04-08_engine_cutover_task_breakdown.md`
- `design/2026-04-08_error_log_driven_design_report.md`
- `contract.md`

## 1. 요약

- 현재 backend는 `PuCo_RL`에 runtime 기준으로 직접 import 또는 `sys.path` path coupling이 걸린 파일이 `backend/app` 14개, `backend/tests` 19개다.
- 이 중 실제로 남겨야 하는 canonical 경계는 사실상 `backend/app/engine_wrapper/wrapper.py` 하나뿐이고, 나머지는 serializer/bot/legacy API/테스트로 퍼져 있다.
- frontend는 `frontend/src/App.tsx`를 중심으로 human Mayor의 slot-by-slot planning state, `/mayor-distribute` 호출, `mayor_slot_idx`/`mayor_can_skip` meta를 모두 직접 전제로 사용한다.
- 컷오버 시 가장 먼저 깨질 확률이 높은 곳은 `state_serializer.py`, `game_service.py`, `bot_service.py`, `frontend/src/App.tsx`, `frontend/src/types/gameState.ts`, Mayor 관련 테스트 묶음이다.
- 따라서 P1 이후 작업은 "upstream 엔진 고정 -> serializer/contract 재정의 -> backend wrapper 컷오버 -> frontend Mayor UI 전환" 순서를 유지해야 한다.

## 2. P0-T1 — Backend Direct Import Inventory

### 2.1 `backend/app` inventory

| 파일 | 현재 upstream 결합 지점 | 현재 역할 | Phase 0 판단 |
|---|---|---|---|
| `backend/app/engine_wrapper/wrapper.py` | `env.pr_env.PuertoRicoEnv` | 엔진 생성/step canonical 진입점 | 유지 후보. 이후 gateway의 핵심 경계 |
| `backend/app/services/state_serializer.py` | `configs.constants.*`, type-check용 `env.engine.PuertoRicoGame` | `phase`, `action_index`, `slot_id`, `mayor_slot_idx`, `mayor_can_skip` 생성 | 최우선 위험. 프론트 계약 드리프트의 중심 |
| `backend/app/services/action_translator.py` | `configs.constants.Role/Good/BuildingType/TileType` | action range 의미를 하드코딩 | Mayor semantics 변경 시 즉시 영향 |
| `backend/app/services/mayor_orchestrator.py` | `configs.constants.BUILDING_DATA/BuildingType/Phase/TileType` | `/mayor-distribute` bulk sequential rollout | 제거 대상 후보 |
| `backend/app/services/mayor_strategy_adapter.py` | `configs.constants.MayorStrategy` 포함 다수 상수 | bot strategy -> sequential action 변환 | 제거 대상 후보 |
| `backend/app/services/bot_service.py` | `utils.env_wrappers`, `env.pr_env`, `configs.constants.Phase` | observation flattening, Mayor 특수 처리, bot orchestration | human/bot Mayor 통일 시 고위험 |
| `backend/app/services/model_registry.py` | `env.pr_env`, `utils.env_wrappers`, `agents.ppo_agent.Agent` | bootstrap metadata, obs/action dim 추론 | fingerprint 작업 전 핵심 참조점 |
| `backend/app/services/agent_registry.py` | `agents.base.AgentWrapper`, `agents.wrappers.*` | bot type -> wrapper binding | serving 경계지만 upstream 클래스명에 종속 |
| `backend/app/services/agents/factory.py` | `agents.ppo_agent.Agent`, `PhasePPOAgent` | checkpoint 로드 및 wrapper 생성 | serving 전용 경계로 축소 필요 |
| `backend/app/services/agents/wrappers.py` | `agents.base.AgentWrapper` | wrapper 인터페이스, empty-mask fallback | Mayor fallback이 `72` 기준이라 drift 위험 |
| `backend/app/services/replay_logger.py` | `configs.constants.*` | phase/good/building naming, replay commentary | gameplay보다는 logging 영향, 중위험 |
| `backend/app/services/building_names.py` | `configs.constants.BuildingType` | enum -> snake_case canonical name | 공용 매핑. 영향 범위는 넓지만 수정량은 작음 |
| `backend/app/api/legacy/deps.py` | `configs.constants.Role/Good/BuildingType/Phase` | legacy history/action helper, bot loop | legacy API 삭제와 함께 정리 대상 |
| `backend/app/api/legacy/actions.py` | 함수 내부 `configs.constants.*` + `sys.path` | legacy Mayor/role/action route | public legacy surface. 제거 대상 |

정리:
- `backend/app`에서 `PuCo_RL` 경로를 직접 추가하는 파일은 14개다.
- 이 중 `engine_wrapper/wrapper.py`만 의도된 boundary이고, 나머지 13개는 서비스/serializer/legacy 레이어로 결합이 퍼진 상태다.

### 2.2 `backend/tests` inventory

직접 upstream 모듈을 import하는 테스트는 아래 11개다.

| 파일 | 현재 upstream 결합 지점 | 현재 검증 포인트 |
|---|---|---|
| `backend/tests/test_mayor_serializer_contract.py` | `configs.constants.BuildingType/Phase/TileType` | `slot_id`, `capacity` serializer 계약 |
| `backend/tests/test_hacienda_turn_flow.py` | `env.components.CityBuilding`, `configs.constants.BuildingType` | Settler/Hacienda edge case |
| `backend/tests/test_mayor_orchestrator.py` | `configs.constants.BuildingType/Phase/TileType` | bulk Mayor slot validation |
| `backend/tests/test_priority2_bot_input_snapshot.py` | `configs.constants.Phase` | bot snapshot phase contract |
| `backend/tests/test_bot_mayor_adapter_integration.py` | `configs.constants.BuildingType/ControlMode/Phase/TileType` | bot strategy vs human sequential Mayor 차이 |
| `backend/tests/test_serving_ppo_wrapper.py` | `agents.ppo_agent.Agent`, `agents.wrappers.PPOWrapper` | serving wrapper parity |
| `backend/tests/test_mayor_strategy_adapter.py` | `configs.constants.MayorStrategy` 포함 다수 상수 | adapter의 sequential expansion |
| `backend/tests/test_todo_priority1_task1_mayor_contract.py` | `configs.constants.BuildingType/Phase/TileType` | `mayor_slot_idx`/cursor 기반 계약 |
| `backend/tests/test_bot_service_safety.py` | `configs.constants.Phase` | Mayor phase bot fallback safety |
| `backend/tests/test_state_serializer_action_index.py` | `configs.constants.BuildingType/Role` | action index 범위 계약 |
| `backend/tests/test_model_registry_bootstrap.py` | `agents.ppo_agent.Agent` | bootstrap metadata/architecture |

직접 import 또는 `sys.path` path coupling을 합치면 영향권 테스트는 총 19개다. 이 중 `sys.path`만 직접 열어두는 추가 테스트는 아래 8개다.

- `backend/tests/test_legacy_features.py`
- `backend/tests/test_channel_mayor_distribute.py`
- `backend/tests/test_event_bus.py`
- `backend/tests/test_multiplayer.py`
- `backend/tests/test_sse_stream.py`
- `backend/tests/test_terminal_result_summary.py`
- `backend/tests/test_gamelog_vp_doubloon.py`
- `backend/tests/test_agent_compatibility.py`

정리:
- Mayor 컷오버가 시작되면 가장 먼저 재작성/삭제 대상이 되는 테스트 묶음은 `test_mayor_*`, `test_todo_priority1_task1_mayor_contract.py`, `test_channel_mayor_distribute.py`, `test_legacy_features.py`다.
- model serving 관련해서는 `test_serving_ppo_wrapper.py`, `test_model_registry_bootstrap.py`, `test_priority2_bot_input_snapshot.py`가 upstream fingerprint 작업의 영향권이다.

## 3. P0-T2 — Frontend Action/Phase Coupling Inventory

| 파일 | 현재 결합 내용 | Phase 0 판단 |
|---|---|---|
| `frontend/src/App.tsx` | `mayorPending[24]`, `lastMayorDistRef`, `buildMayorPlacements()`, `/api/puco/game/{id}/mayor-distribute`, `state.meta.mayor_slot_idx`, `state.meta.mayor_can_skip`, `phase === 'mayor_action'` 분기, hardcoded `channelActionIndex` | 프론트 컷오버 중심 파일. Human Mayor legacy 상태를 가장 많이 들고 있음 |
| `frontend/src/types/gameState.ts` | `PhaseType`에 `mayor_distribution` 포함, `Meta.mayor_slot_idx`, `Meta.mayor_can_skip`, `slot_id`, `capacity`, `action_mask` 정의 | contract drift의 타입 레벨 반영 지점 |
| `frontend/src/components/PlayerPanel.tsx` | toggle mode(`mayorPending`)와 sequential mode(`mayorSlotIdx`, `onMayorPlace`) 동시 지원 | dual-mode Mayor UI 경계 |
| `frontend/src/components/IslandGrid.tsx` | island slot별 pending count, `currentMayorSlot` 기반 sequential highlight/click 처리 | slot cursor 계약에 직접 의존 |
| `frontend/src/components/CityGrid.tsx` | building index별 pending count, `currentMayorSlot`, `empty_slots` 기반 sequential placement | slot cursor + building capacity 계약에 직접 의존 |
| `frontend/src/components/HistoryPanel.tsx` | `mayor_toggle_island`/`mayor_toggle_city`를 `mayor_place_done`으로 합침 | legacy Mayor history semantics 잔존 |
| `frontend/src/components/CommonBoardPanel.tsx` | `mayor_distribution`와 `mayor_action`을 둘 다 Mayor 구간으로 하이라이트 | stale phase enum 흔적 |
| `frontend/src/hooks/useGameWebSocket.ts` | WS payload에서 top-level `action_mask` 또는 embedded `state.action_mask` 둘 다 허용 | 전환기 호환성 경계 |

추가 관찰:
- `App.tsx`의 `channelActionIndex`에는 `mayorIsland: 69 + slotIndex`, `mayorCity: 81 + slotIndex`가 남아 있다. 현재 채널 REST 경로에서는 실사용되지 않더라도, 프론트 코드 안에 obsolete Mayor action range 지식이 남아 있다는 뜻이다.
- `CommonBoardPanel.tsx`와 `types/gameState.ts`는 `mayor_distribution` phase를 여전히 타입/렌더링에 남겨 두고 있지만, 현재 serializer의 주계약은 `mayor_action` 중심이다.
- `PlayerPanel.tsx`, `IslandGrid.tsx`, `CityGrid.tsx`는 "human toggle mode"와 "sequential cursor mode"를 동시에 표현할 수 있게 설계되어 있어, 전략 선택 UI로 바꾸려면 이 양분 구조부터 제거해야 한다.

## 4. P0-T3 — Breakage Matrix

upstream를 canonical engine으로 교체하고 human Mayor도 strategy-first로 통일할 때 깨질 가능성이 높은 순서대로 정리한다.

| 우선순위 | 파일/영역 | 깨지는 이유 | 다음 phase 메모 |
|---|---|---|---|
| P0 | `backend/app/services/state_serializer.py` | `mayor_slot_idx`, `mayor_can_skip`, slot metadata, phase 문자열이 현재 프론트 계약의 핵심 | P2 serializer/meta 재정의 최우선 |
| P0 | `frontend/src/App.tsx` | human Mayor local planner, `/mayor-distribute`, sequential fallback UI가 모두 여기에 있음 | P4 전환의 중심 |
| P0 | `frontend/src/types/gameState.ts` | 제거될 meta/phase 필드가 타입에 박혀 있음 | P2/P4 동시에 수정 필요 |
| P0 | `backend/app/services/game_service.py` + `backend/app/api/channel/game.py` | public REST에서 `/mayor-distribute`를 제공하고 서비스가 이를 처리함 | P3에서 public contract 축소 필요 |
| P0 | `backend/app/services/bot_service.py` | bot만 strategy action을 쓰는 현재 special-case가 사라져야 함 | human/bot Mayor 단일 흐름으로 정리 |
| P0 | `backend/app/services/mayor_orchestrator.py` | human Mayor bulk sequential rollout 전용 파일 | 제거 후보 |
| P0 | `backend/app/services/mayor_strategy_adapter.py` | bot strategy -> sequential adapter 전용 파일 | 제거 후보 |
| P0 | Mayor 관련 테스트 묶음 | 현 계약이 "human sequential vs bot strategy" 전제를 강하게 검증 | RED부터 새 contract로 재작성 필요 |
| P1 | `backend/app/services/action_translator.py` | Mayor action space 의미를 정수 범위로 하드코딩 | strategy-only 범위로 재정의 필요 |
| P1 | `frontend/src/components/PlayerPanel.tsx` / `IslandGrid.tsx` / `CityGrid.tsx` | slot cursor, pending counts, per-slot interactivity에 의존 | 전략 패널로 교체 대상 |
| P1 | `backend/app/services/agents/wrappers.py` | Mayor empty-mask fallback이 action `72` 기준 | strategy-only semantics에 맞춰 보정 필요 |
| P1 | `backend/app/services/model_registry.py` / `agent_registry.py` / `agents/factory.py` | upstream 모델/obs/action metadata를 직접 읽음 | P5 fingerprint에서 오히려 활용 가능 |
| P2 | `backend/app/services/replay_logger.py` | commentary와 metadata naming은 바뀌지만 gameplay blocker는 아님 | P5에서 fingerprint 필드 추가 |
| P2 | `backend/app/services/building_names.py` | 건물 enum mapping 자체는 유지 가능 | low-risk shared helper |
| P2 | legacy API (`backend/app/api/legacy/*`) | 이미 deprecated 경로라 main flow blocker는 아님 | P6 cleanup에서 제거 |

## 5. P0-T4 — Cutover Contract Freeze

### 5.1 migration 동안 유지해야 하는 계약

아래는 P1~P3 동안 임시로라도 깨지면 안 되는 계약이다.

- canonical engine truth는 `PuCo_RL/env/engine.py`, `PuCo_RL/env/pr_env.py`다.
- 채널 일반 액션 계약은 계속 `POST /api/puco/game/{game_id}/action` + `{ "payload": { "action_index": number } }`다.
- WS `STATE_UPDATE`는 프론트가 바로 렌더 가능한 `GameState`를 계속 보내야 한다.
- `GameState` top-level 구조는 유지한다.
  - `meta`
  - `common_board`
  - `players`
  - `decision`
  - `history`
  - `bot_players`
  - `model_versions`
  - `result_summary`
  - `action_mask`
- Mayor 외 action index 의미는 유지한다.
  - role select `0-7`
  - settler `8-14`
  - pass `15`
  - builder `16-38`
  - trader `39-43`
  - captain `44-68`, `106-110`
  - craftsman privilege `93-97`
  - hacienda `105`
- canonical naming은 유지한다.
  - building name: snake_case
  - `slot_id`: `city:<building_name>:<idx>`, `island:<tile_name>:<idx>`
- `pass_action_index=15`, `hacienda_action_index=105`는 유지한다.

### 5.2 의도적으로 바꿔야 하는 계약

아래는 이번 컷오버에서 명시적으로 제거/변경해야 하는 계약이다.

- human Mayor의 supported public contract에서 `/mayor-distribute`를 제거한다.
- Mayor는 사람/봇 모두 single strategy action으로 통일한다.
- `meta.mayor_slot_idx`는 supported contract에서 제거한다.
- `meta.mayor_can_skip`는 supported contract에서 제거한다.
- `PhaseType`의 `mayor_distribution`은 supported 프론트 계약에서 제거한다.
- 프론트 로컬 상태의 `mayorPending`, `lastMayorDistRef`, slot toggle UI는 제거한다.
- `MayorStrategyAdapter`, `mayor_orchestrator`, legacy Mayor toggle history/route는 남기지 않는다.
- non-gateway 위치에서의 `PuCo_RL` direct import는 최종적으로 허용하지 않는다.

### 5.3 cutover 후 최소 Mayor 계약

컷오버 이후 supported Mayor 계약은 아래 최소선으로 고정한다.

- phase 이름은 계속 `mayor_action`을 사용한다.
- human/bot 모두 Mayor phase에서 action `69-71` 중 하나만 보낸다.
- 프론트는 slot cursor가 아니라 strategy choice UI를 렌더한다.
- 프론트가 Mayor UI를 띄우는 근거는 `phase === "mayor_action"` + Mayor strategy action availability여야 한다.
- serializer는 slot cursor meta 대신 strategy-first UI에 필요한 최소 정보만 남긴다.

## 6. 다음 phase 입력

이 문서를 기준으로 바로 이어서 해야 할 일은 아래다.

1. P1에서 upstream 기준 `PuCo_RL` fingerprint와 read-only 원칙을 고정한다.
2. P2에서 `contract.md`를 strategy-first Mayor 기준으로 다시 쓴다.
3. P3에서 `engine_gateway`를 만들고 `state_serializer.py`, `game_service.py`, `bot_service.py`를 gateway 기준으로 재배치한다.
4. P4에서 `App.tsx`의 human Mayor local planner를 걷어내고 전략 선택 UI로 교체한다.

## 7. Phase 0 완료 판정

- P0-T1 완료: backend/app, backend/tests의 direct import/path coupling 파일 목록을 문서화했다.
- P0-T2 완료: 프론트가 기대하는 action index / phase / meta / Mayor UI coupling을 정리했다.
- P0-T3 완료: 컷오버 시 breakage 우선순위를 정리했다.
- P0-T4 완료: migration 동안 유지할 계약과 의도적으로 바꿀 계약을 분리했다.
