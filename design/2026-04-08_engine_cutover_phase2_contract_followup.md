# Engine Cutover Phase 2 Contract Follow-up

작성일: 2026-04-08  
연결 backlog: `design/2026-04-08_engine_cutover_task_breakdown.md`  
대상 task: `P2-T3`, `P2-T4`

## 1. 목적

Phase 2에서 문서로 먼저 고정해야 했던 두 가지를 정리한다.

- frontend가 실제로 의존해도 되는 serializer/meta 최소 필드
- sequential Mayor 전제 테스트를 어떤 테스트로 치환했는지

이 문서는 `contract.md`의 보조 잠금 문서다. 구현 충돌 시 `contract.md`와 현재 serializer 출력이 우선한다.

## 2. Serializer / Meta 최소 계약

현재 frontend가 의존해도 되는 `GameState.meta` 필드는 아래만 지원한다.

| 필드 | 타입 | 의미 | 프론트 사용처 |
|---|---|---|---|
| `game_id` | `string` | 현재 게임 식별자 | channel state 식별 |
| `round` | `number` | 현재 라운드(1-based) | 메타 표시 |
| `step_count` | `number` | 누적 action step | 디버깅/로그 |
| `num_players` | `number` | 플레이어 수 | 보드/패널 구성 |
| `player_order` | `string[]` | `player_0..n` 순서 | 패널 렌더 순서 |
| `governor` | `string` | 현재 governor player key | 메타 표시 |
| `phase` | `string` | serializer phase string | 화면 분기 |
| `phase_id` | `number` | canonical engine phase enum int | bot/debug/telemetry |
| `active_role` | `string \| null` | 현재 활성 role | privilege 배지 |
| `active_player` | `string` | 현재 차례 player key | turn/orchestration |
| `end_game_triggered` | `boolean` | 게임 종료 여부 | end-game panel |
| `vp_supply_remaining` | `number` | 남은 VP chip | common board |
| `captain_consecutive_passes` | `number` | Captain pass 카운트 | captain UI |
| `bot_thinking` | `boolean` | bot thinking overlay | 입력 block |
| `pass_action_index` | `number` | 현재 pass action | generic next/pass |
| `hacienda_action_index` | `number` | Hacienda draw action | settler privilege |

추가로 frontend가 Mayor strategy UI를 위해 의존하는 필드는 아래다.

- `action_mask[69:72]`
- `players[*].city.buildings[*].name`
- `players[*].city.buildings[*].current_colonists`
- `players[*].city.buildings[*].max_colonists`
- `players[*].city.buildings[*].empty_slots`
- `players[*].city.buildings[*].is_active`
- `players[*].city.buildings[*].slot_id`
- `players[*].city.buildings[*].capacity`
- `players[*].island.plantations[*].type`
- `players[*].island.plantations[*].colonized`
- `players[*].island.plantations[*].slot_id`
- `players[*].island.plantations[*].capacity`

## 3. 명시적 비지원 필드

아래 항목은 supported serializer/meta 계약이 아니다.

- `meta.mayor_slot_idx`
- `meta.mayor_can_skip`
- `phase === "mayor_distribution"`
- human Mayor pending toggle 배열
- slot-by-slot Mayor 제출 payload

즉, 프론트는 Mayor를 `69-71` strategy action 하나로만 제출해야 한다.

## 4. 테스트 정리 / 치환 계획

### 4.1 제거된 legacy 테스트

아래 테스트는 sequential Mayor나 삭제된 adapter/orchestrator를 전제로 했으므로 제거했다.

- `backend/tests/test_bot_mayor_adapter_integration.py`
- `backend/tests/test_mayor_strategy_adapter.py`
- `backend/tests/test_mayor_orchestrator.py`
- `backend/tests/test_todo_priority1_task1_mayor_contract.py`
- `backend/tests/test_channel_mayor_distribute.py`
- `backend/tests/test_agent_compatibility.py`
- `backend/tests/test_legacy_ppo_wrapper.py`

### 4.2 대체 / 보강된 테스트

아래 테스트가 현재 contract를 직접 지킨다.

- `backend/tests/test_mayor_strategy_contract.py`
  - human/bot 공통 Mayor strategy band 검증
  - `mayor-distribute` public route 비노출 검증
- `backend/tests/test_phase_action_edge_cases.py`
  - Mayor phase mask/action band edge case 검증
- `backend/tests/test_engine_gateway_import_guard.py`
  - non-gateway direct import 금지 검증
- `backend/tests/test_scenario_regression_harness.py`
  - Trader / high-doubloon role / Mayor scenario regression 검증
- `frontend/src/components/__tests__/MayorStrategyPanel.test.tsx`
  - human Mayor 전략 UI 렌더/선택 검증
- `frontend/src/__tests__/App.mayor-flow.test.tsx`
  - App integration에서 Mayor strategy panel 노출 검증
- `frontend/src/__tests__/App.auth-flow.test.tsx`
  - auth bootstrap split 이후 초기 진입 flow 검증

## 5. 구현 기준 요약

- serializer는 strategy-first Mayor만 노출한다.
- frontend는 `GameScreen`에서 Mayor UI를 렌더하며 `App.tsx`는 orchestration을 담당한다.
- backend는 `engine_gateway` 경계 밖에서 `PuCo_RL` 내부 모듈을 직접 import하지 않는다.
