# Mayor Direction B Patch Plan

## 목표

- 인간 Mayor 입력 UX는 현재의 토글 방식과 최종 확정 흐름을 유지한다.
- 엔진의 순차 action contract는 백엔드가 흡수한다.
- 봇은 기존 순차 action/mask 경로를 그대로 유지한다.
- channel API와 legacy API의 Mayor 책임을 다시 분리한다.

핵심 구조:

```text
Frontend toggle UI
  -> final placement plan
  -> backend mayor orchestrator
  -> sequential engine steps (69~72)
  -> updated GameState
```

## 결론 먼저

`방향 B`에서 실제로 바꿔야 할 핵심은 다음이다.

1. 프론트는 더 이상 `69+slot`, `81+slot` 같은 Mayor action index를 직접 만들지 않는다.
2. 백엔드에 `mayor_orchestrator`를 신설해 plan을 순차 engine action으로 변환한다.
3. serializer가 프론트에 stable `slot_id`와 slot metadata를 내려준다.
4. `mayor-distribute`를 사람 Mayor 입력의 표준 경로로 승격한다.
5. slot-toggle 의미를 가진 legacy endpoint는 deprecated 처리하거나 orchestrator 내부 전용으로 축소한다.

## 변경 파일 개요

## TDD First List

구현 전에 먼저 고정해야 할 테스트 목록이다.

원칙:

- 사람 Mayor의 표준 입력 경로는 legacy보다 channel API를 먼저 기준으로 잡는다.
- legacy Mayor 경로는 shared orchestrator를 재사용하는 호환층으로만 검증한다.
- 테스트 추가 순서는 `serializer contract -> orchestrator unit -> channel endpoint -> frontend payload -> legacy compatibility` 순서로 간다.

### 1. Serializer Contract Tests

대상 파일:

- `backend/tests/test_todo_priority1_task1_mayor_contract.py`
- 필요 시 신규 `backend/tests/test_mayor_serializer_contract.py`

먼저 추가할 테스트:

- `test_mayor_serializer_exposes_slot_ids_for_island_slots`
- `test_mayor_serializer_exposes_slot_ids_for_city_slots`
- `test_mayor_serializer_slot_ids_follow_engine_order`
- `test_mayor_serializer_exposes_capacity_metadata_for_toggle_ui`
- `test_mayor_serializer_keeps_mayor_slot_idx_for_debug_reconciliation`

고정하려는 계약:

- 프론트가 slot identity를 자체 생성하지 않는다.
- slot order의 진실 소스는 serializer/engine이다.

### 2. Orchestrator Unit Tests

대상 파일:

- 신규 `backend/tests/test_mayor_orchestrator.py`

먼저 추가할 테스트:

- `test_build_slot_catalog_matches_engine_island_then_city_order`
- `test_translate_plan_to_actions_maps_slot_ids_to_sequential_amount_actions`
- `test_translate_plan_to_actions_fills_unmentioned_slots_with_zero`
- `test_validate_distribution_rejects_unknown_slot_id`
- `test_validate_distribution_rejects_over_capacity_count`
- `test_validate_distribution_rejects_total_over_available_colonists`
- `test_apply_distribution_plan_executes_until_players_turn_advances`

고정하려는 계약:

- 방향 B의 핵심인 `plan -> sequential actions` 책임을 백엔드 한 곳에 모은다.

### 3. Channel Endpoint Tests

대상 파일:

- 신규 `backend/tests/test_channel_mayor_distribute.py`

먼저 추가할 테스트:

- `test_channel_mayor_distribute_accepts_placements_payload`
- `test_channel_mayor_distribute_returns_updated_state_on_success`
- `test_channel_mayor_distribute_rejects_invalid_slot_id`
- `test_channel_mayor_distribute_rejects_over_capacity_plan`
- `test_channel_mayor_distribute_rejects_when_not_active_players_turn`

고정하려는 계약:

- 사람 Mayor의 표준 공개 경로는 channel endpoint다.

### 4. Frontend Payload Builder Tests

대상 파일:

- 신규 `frontend/src/components/__tests__/mayorPlanBuilder.test.ts`
- 또는 `frontend/src/App.mayor.test.tsx`

먼저 추가할 테스트:

- `test_build_mayor_placements_uses_slot_ids_from_server_state`
- `test_build_mayor_placements_omits_zero_count_slots`
- `test_build_mayor_placements_keeps_island_and_city_slots_distinct`
- `test_confirm_mayor_distribution_posts_to_channel_endpoint`

고정하려는 계약:

- 프론트는 action index가 아니라 최종 placements payload만 제출한다.

### 5. Legacy Compatibility Tests

대상 파일:

- `backend/tests/test_legacy_features.py`

나중에 추가할 테스트:

- `test_legacy_mayor_distribute_delegates_to_shared_orchestrator`
- `test_legacy_mayor_distribute_uses_same_slot_id_contract_as_channel`

고정하려는 계약:

- legacy는 진실 소스가 아니라 channel/shared service를 재사용하는 호환층이다.

### 6. History / UX Regression Tests

대상 파일:

- `frontend/src/components/HistoryPanel.tsx`
- locale 관련 render/snapshot test

나중에 추가할 테스트:

- `test_human_mayor_submission_shows_single_mayor_distribute_entry`
- `test_human_mayor_history_does_not_depend_on_toggle_spam`

### 구현 착수 순서

1. Serializer contract tests
2. Orchestrator unit tests
3. Channel endpoint tests
4. Frontend payload tests
5. Legacy compatibility tests
6. 실제 구현

### 완료 기준

- 프론트가 Mayor action index를 직접 생성하지 않는다.
- channel에서 사람 Mayor plan 제출이 가능하다.
- orchestrator가 plan -> sequential actions의 단일 책임을 가진다.
- legacy는 호환층으로만 남는다.

필수 변경:

- `backend/app/services/mayor_orchestrator.py` 신규
- `backend/app/services/state_serializer.py`
- `backend/app/api/channel/game.py`
- `frontend/src/App.tsx`
- `frontend/src/types/gameState.ts`

권장 변경:

- `frontend/src/components/IslandGrid.tsx`
- `frontend/src/components/CityGrid.tsx`
- `frontend/src/components/PlayerPanel.tsx`
- `backend/app/api/legacy/actions.py`
- `backend/app/api/legacy/schemas.py`
- `backend/tests/test_legacy_features.py`
- `backend/tests/test_todo_priority1_task1_mayor_contract.py`
- 신규 테스트 파일: `backend/tests/test_mayor_orchestrator.py`

정리 대상:

- `backend/app/services/action_translator.py`
- `backend/app/api/legacy/deps.py`
- `frontend/src/components/HistoryPanel.tsx`
- `frontend/src/locales/*.json`

## Patch Plan

### Patch 1. Mayor Orchestrator 신설

대상 파일:

- `backend/app/services/mayor_orchestrator.py`

목적:

- 사람이 제출한 최종 배치 계획을 엔진 순차 action으로 바꾸는 단일 책임 계층 생성

핵심 함수 제안:

```py
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class MayorPlacement:
    slot_id: str
    count: int


def validate_distribution_plan(game, player_idx: int, placements: List[MayorPlacement]) -> None:
    ...


def build_slot_catalog(game, player_idx: int) -> List[dict]:
    ...


def translate_plan_to_actions(game, player_idx: int, placements: List[MayorPlacement]) -> List[int]:
    ...


def apply_distribution_plan(engine, player_idx: int, placements: List[MayorPlacement]) -> None:
    ...
```

변환 핵심 로직 예시:

```py
def translate_plan_to_actions(game, player_idx: int, placements: List[MayorPlacement]) -> List[int]:
    plan_map: Dict[str, int] = {p.slot_id: p.count for p in placements}
    actions: List[int] = []

    for slot in build_slot_catalog(game, player_idx):
        slot_id = slot["slot_id"]
        amount = plan_map.get(slot_id, 0)
        actions.append(69 + amount)

    return actions
```

실제 구현 시 중요한 점:

- `build_slot_catalog()`는 엔진 현재 board 상태 기준으로 slot 순서를 생성해야 한다.
- island 0~11, city 12~23 순서를 그대로 따라야 한다.
- empty slot도 catalog에는 포함하되 capacity가 0이면 plan에서는 count 0만 허용해야 한다.

영향 범위:

- 사람 Mayor 요청 처리 경로 전부
- `mayor-distribute`
- serializer와 테스트가 slot id 체계를 공유해야 함

리스크:

- slot_id 설계가 바뀌면 프론트와 테스트가 같이 깨짐
- 엔진 슬롯 순서와 catalog 순서가 다르면 배치가 엇갈림

롤백 방법:

1. `backend/app/services/mayor_orchestrator.py` 제거
2. `legacy/actions.py`를 기존 distribution loop 구현으로 복귀
3. serializer의 slot_id 필드 제거
4. 프론트에서 기존 `confirmMayorDistribution()` 직접 전송 방식 복귀

## Patch 2. Serializer에 stable slot metadata 추가

대상 파일:

- `backend/app/services/state_serializer.py`
- 필요 시 `frontend/src/types/gameState.ts`

목적:

- 프론트가 자체 규칙으로 slot을 조합하지 않게 하고, 백엔드가 정의한 slot identity를 그대로 사용하게 한다.

추가 제안 필드:

```json
{
  "meta": {
    "mayor_slot_idx": 12,
    "mayor_can_skip": false
  },
  "players": {
    "player_0": {
      "island": {
        "plantations": [
          {"type": "corn", "colonized": false, "slot_id": "island:corn:0", "capacity": 1}
        ]
      },
      "city": {
        "buildings": [
          {"name": "small_market", "current_colonists": 0, "max_colonists": 1, "slot_id": "city:small_market:0"}
        ]
      }
    }
  }
}
```

패치 스니펫 예시:

```py
plantations = [
    {
        "type": TILE_TO_STR.get(_safe_get(t, "tile_type"), "empty"),
        "colonized": bool(_safe_get(t, "is_occupied", "occupied", default=False)),
        "slot_id": f"island:{TILE_TO_STR.get(_safe_get(t, 'tile_type'), 'empty')}:{idx}",
        "capacity": 1,
    }
    for idx, t in enumerate(player.island_board)
]
```

```py
buildings_data.append({
    "name": _building_name(bt),
    "max_colonists": max_col,
    "current_colonists": _safe_int(_safe_get(b, "colonists", "worker_count", default=0)),
    "empty_slots": max_col - _safe_int(_safe_get(b, "colonists", "worker_count", default=0)),
    "slot_id": f"city:{_building_name(bt)}:{idx}",
})
```

영향 범위:

- 프론트 타입
- 프론트 토글 payload 생성
- snapshot/contract 테스트

리스크:

- slot_id 생성 규칙이 의미 기반인지 index 기반인지 애매하면 이후 리팩터링 때 깨짐

롤백 방법:

1. slot_id, capacity 필드 제거
2. 프론트에서 기존 배열 index 기반 토글 로직 복귀
3. orchestrator가 slot_id 대신 기존 0~23 분포 배열 사용하도록 후퇴

## Patch 3. Channel `mayor-distribute`를 공식 orchestration 경로로 변경

대상 파일:

- `backend/app/api/channel/game.py`
- `backend/app/api/legacy/actions.py`는 shared service를 재사용하는 호환층으로 최소화

현재 문제:

- `mayor-distribute`가 현재 legacy 쪽에서 엔진 loop를 직접 돌리는 구현인데, 공식 책임 계층이 없다.
- payload도 `distribution: [24]` 형식이라 의미가 약하다.

권장 변경:

- 사람 Mayor의 표준 공개 경로는 channel에 둔다.
- legacy는 나중에 모든 기능이 channel로 흡수될 수 있게 shared orchestrator를 재사용하는 얇은 wrapper로 남긴다.

기존:

```json
{
  "player": "P0",
  "distribution": [1,0,0,...]
}
```

신규:

```json
{
  "player": "P0",
  "placements": [
    {"slot_id": "island:corn:0", "count": 1},
    {"slot_id": "city:small_market:0", "count": 1}
  ]
}
```

엔드포인트 내부 스니펫:

```py
@router.post("/{game_id}/mayor-distribute")
async def channel_mayor_distribute(game_id: str, body: MayorDistributeBody, ...):
    ...
```

영향 범위:

- channel mayor API payload
- 프론트 confirm 경로
- Mayor 관련 백엔드 에러 형식

리스크:

- channel route 추가에 따른 라우팅/권한 처리 변경
- 기존 `distribution[24]`를 기대하는 테스트 전부 수정 필요

롤백 방법:

1. channel mayor-distribute endpoint 제거
2. 프론트를 기존 legacy mayor-distribute 호출로 복귀
3. legacy/actions.py`의 old loop 또는 기존 구현으로 임시 복귀
4. orchestrator 내부 구현은 남겨두되 endpoint wiring만 해제

## Patch 4. Legacy schemas 변경

대상 파일:

- `backend/app/api/legacy/schemas.py`

추가 제안:

```py
from pydantic import BaseModel, Field


class MayorPlacementItem(BaseModel):
    slot_id: str
    count: int = Field(ge=0, le=3)


class MayorDistributeBody(BaseModel):
    player: str
    placements: list[MayorPlacementItem]
```

권장:

- `MayorColonistBody`는 deprecated 주석 추가
- `MayorPlaceAmountBody`는 봇/내부 디버그 전용 주석 추가

영향 범위:

- OpenAPI
- request validation
- legacy 기능 테스트

롤백 방법:

- 기존 schema로 복구
- orchestrator 입력에서 `placements`를 `distribution`으로 다시 매핑

## Patch 5. Frontend `confirmMayorDistribution()`를 plan 제출 방식으로 변경

대상 파일:

- `frontend/src/App.tsx`

현재 문제:

- 프론트가 직접 `mayorIsland(i)`, `mayorCity(i)` action을 순회 전송한다.
- 이건 엔진 contract를 프론트가 알고 있는 구조다.

현재 코드의 문제 구간:

```ts
for (let i = 0; i < 12; i++) {
  for (let j = 0; j < mayorPending[i]; j++) {
    await channelAction(channelActionIndex.mayorIsland(i));
  }
}
```

수정 방향:

```ts
function buildMayorPlacements(state: GameState, mayorPending: number[]) {
  const player = state.players[state.meta.active_player];
  const placements: Array<{ slot_id: string; count: number }> = [];

  player.island.plantations.forEach((p, idx) => {
    const count = mayorPending[idx] ?? 0;
    if (count > 0 && p.slot_id) placements.push({ slot_id: p.slot_id, count });
  });

  player.city.buildings.forEach((b, idx) => {
    const count = mayorPending[12 + idx] ?? 0;
    if (count > 0 && b.slot_id) placements.push({ slot_id: b.slot_id, count });
  });

  return placements;
}
```

```ts
async function confirmMayorDistribution() {
  if (!state || !mayorPending || notMyTurn()) return;
  const placements = buildMayorPlacements(state, mayorPending);

  const res = await fetch(`/api/puco/game/${gameId}/mayor-distribute`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${authToken}`,
    },
    body: JSON.stringify({
      placements,
    }),
  });
  ...
}
```

영향 범위:

- 인간 Mayor 제출 로직
- 에러 처리
- `channelActionIndex.mayorIsland/mayorCity` 제거 가능

리스크:

- channel route 추가 전까지는 구현이 incomplete 상태가 됨
- 인증/권한 검증을 기존 channel game action 정책과 맞춰야 함

롤백 방법:

1. 기존 `channelActionIndex.mayorIsland/mayorCity` 복원
2. 기존 confirm loop 복원
3. serializer slot_id 미사용 복귀

## Patch 6. Frontend 타입 보강

대상 파일:

- `frontend/src/types/gameState.ts`

추가 제안:

```ts
export interface Plantation {
  type: string;
  colonized: boolean;
  slot_id?: string;
  capacity?: number;
}

export interface PlayerBuilding {
  name: string;
  max_colonists: number;
  current_colonists: number;
  empty_slots: number;
  is_active: boolean;
  vp: number;
  slot_id?: string;
}
```

영향 범위:

- IslandGrid
- CityGrid
- PlayerPanel
- Mayor plan builder

롤백 방법:

- optional field 삭제
- plan builder를 array index 기반으로 되돌림

## Patch 7. `action_translator.py` 역할 축소

대상 파일:

- `backend/app/services/action_translator.py`

`방향 B`에서는 이 파일을 완전히 amount-based로 바꾸는 것이 필수는 아니다.
다만 역할을 분명히 줄여야 한다.

권장:

- 사람 Mayor 표준 경로에서는 `mayor_toggle()`를 더 이상 직접 쓰지 않음
- `mayor_toggle()`는 deprecated 주석 추가
- `mayor_place(amount)`를 내부 순차 경로용으로 추가 가능

예시:

```py
def mayor_place(amount: int) -> int:
    if not (0 <= amount <= 3):
        raise ValueError("Mayor amount out of range")
    return 69 + amount
```

```py
def mayor_toggle(target_type: str, target_index: int) -> int:
    # Deprecated: human Mayor should use mayor-distribute orchestration.
    ...
```

영향 범위:

- legacy endpoint
- 테스트 설명
- 문서

롤백 방법:

- deprecated 주석 제거
- 기존 helper만 유지

## Patch 8. `legacy/deps.py` 히스토리 해석 정리

대상 파일:

- `backend/app/api/legacy/deps.py`

현재:

- `69~80`은 `mayor_toggle_island`
- `81~92`은 `mayor_toggle_city`

`방향 B`에서는 이 해석을 당장 완전히 제거할 필요는 없지만,
사람 표준 경로가 `mayor-distribute`로 이동하면 히스토리 의미가 바뀐다.

권장 변경:

- 사람 최종 제출은 `mayor_distribute`
- 필요하면 내부 상세 로그는 별도 debug log로만 남김
- user-facing history는 slot toggle 연속 로그를 굳이 보여주지 않음

예시:

```py
session.add_history("mayor_distribute", {"player": player_name})
```

영향 범위:

- HistoryPanel
- locale 문구
- 디버그 로그 해석

롤백 방법:

- 기존 toggle history 유지
- collapse 로직 그대로 사용

## Patch 9. Frontend History 정리

대상 파일:

- `frontend/src/components/HistoryPanel.tsx`
- `frontend/src/locales/en.json`
- `frontend/src/locales/ko.json`
- `frontend/src/locales/it.json`

현재는:

- `mayor_toggle_island`
- `mayor_toggle_city`

를 묶어서 `mayor_place_done`으로 보여준다.

`방향 B`에서 권장:

- 사람 Mayor 성공 결과는 그냥 `mayor_distribute`
- slot toggle 세부 로그는 user-facing history에서 약화 또는 제거

예시:

```diff
- const MAYOR_TOGGLE_ACTIONS = new Set(['mayor_toggle_island', 'mayor_toggle_city']);
+ const MAYOR_TOGGLE_ACTIONS = new Set<string>();
```

또는 collapse 로직은 유지하되, 사람 경로에서는 toggle history를 생성하지 않도록 백엔드에서 정리한다.

영향 범위:

- 사용자 히스토리 가독성
- 테스트 스냅샷

롤백 방법:

- locale와 collapse 로직 원복

## Patch 10. 테스트 계획

### 백엔드 테스트 추가

신규 파일:

- `backend/tests/test_mayor_orchestrator.py`

권장 테스트:

```py
def test_translate_plan_to_actions_keeps_engine_slot_order():
    ...

def test_validate_distribution_rejects_over_capacity():
    ...

def test_validate_distribution_rejects_over_total_colonists():
    ...

def test_apply_distribution_executes_until_phase_advances():
    ...
```

### 기존 테스트 수정

대상:

- `backend/tests/test_legacy_features.py`
- `backend/tests/test_todo_priority1_task1_mayor_contract.py`
- `backend/tests/test_state_serializer_action_index.py`

수정 포인트:

- `distribution: [24]` 기반 테스트를 `placements` 기반 테스트로 교체
- serializer contract test에 `slot_id` 존재 검증 추가
- Mayor contract test는 "프론트가 직접 slot-address action을 보내면 안 된다"는 식으로 재정의 가능

### 프론트 테스트

권장 신규 테스트:

- `frontend/src/components/__tests__/MayorPlanBuilder.test.ts`
- 또는 `frontend/src/App.mayor.test.tsx`

검증 내용:

- `mayorPending`에서 `placements` payload가 정확히 생성되는지
- `slot_id` 없는 슬롯은 제출되지 않는지
- count=0 슬롯은 제출되지 않는지

## 변경 순서 제안

안전한 순서:

1. serializer에 `slot_id` 추가
2. orchestrator 파일 작성
3. backend schema 변경
4. `mayor-distribute`를 orchestrator 사용으로 전환
5. 프론트 `confirmMayorDistribution()`를 `placements` 제출로 변경
6. 테스트 수정
7. history/locale 정리

이 순서가 좋은 이유:

- backend contract를 먼저 고정
- 프론트는 그 계약만 소비
- 중간 상태에서도 엔진 자체는 건드리지 않음

## 롤백 전략

### 최소 롤백

문제가 orchestration layer에서만 발생하면:

1. `legacy/actions.py`에서 `mayor-distribute`를 기존 distribution loop로 복귀
2. `frontend/src/App.tsx`를 기존 confirm loop로 복귀
3. `state_serializer.py`의 slot_id 필드는 남겨도 무방

### 중간 롤백

프론트 payload 구조가 문제면:

1. `placements` -> `distribution[24]`로 schema 복귀
2. orchestrator는 내부 util로만 남기고 비활성

### 전체 롤백

설계 자체가 맞지 않으면:

1. `backend/app/services/mayor_orchestrator.py` 제거
2. legacy actions를 기존 구현으로 복귀
3. serializer slot_id 추가분 제거
4. 프론트 mayor-distribute payload 생성 로직 제거
5. history/locale 원복

## 추천 판단

`방향 B`는 UX 보존 측면에서는 맞다.
대신 조건이 있다.

- 사람 Mayor의 공식 입력 경로를 반드시 `mayor-distribute` 하나로 고정해야 한다.
- 변환 책임을 백엔드 한 곳으로 모아야 한다.
- serializer가 stable slot identity를 내려줘야 한다.

이 세 가지를 안 하면, 토글 UI 유지 방향은 다시 같은 contract drift를 만들 가능성이 높다.

## 최종 제안

실행 기준:

- 엔진은 그대로 둔다.
- 프론트 Mayor UX는 그대로 둔다.
- 백엔드에 `mayor_orchestrator.py`를 추가한다.
- 사람 Mayor 입력의 표준 API는 channel의 `mayor-distribute(placements)`로 통일한다.
- slot-address action helper는 내부/legacy 호환용으로만 축소한다.
- legacy Mayor API는 shared orchestrator를 재사용하는 호환층으로만 유지한다.

이게 현재 코드베이스에서 `방향 B`로 갈 때 가장 현실적인 patch plan이다.

## 1단계 테스트 파일 초안

이 섹션은 실제 구현 전에 어떤 테스트 파일을 만들고, 각 파일에서 무엇을 먼저 고정할지 초안 수준으로 정리한 것이다.

### A. `backend/tests/test_mayor_serializer_contract.py`

목적:

- serializer가 slot identity와 toggle UI용 metadata를 안정적으로 내려준다는 계약 고정

초안:

```py
def test_island_slots_include_slot_id_and_capacity():
    ...


def test_city_slots_include_slot_id_and_capacity():
    ...


def test_slot_ids_follow_engine_slot_order():
    ...


def test_mayor_slot_idx_is_still_exposed_for_reconciliation():
    ...
```

검증 포인트:

- `players[player_id].island.plantations[*].slot_id`
- `players[player_id].city.buildings[*].slot_id`
- `capacity`, `empty_slots` 등 프론트 토글 검증용 필드
- `meta.mayor_slot_idx` 유지 여부

### B. `backend/tests/test_mayor_orchestrator.py`

목적:

- `plan -> sequential actions` 변환 책임을 백엔드 단위 테스트로 고정

초안:

```py
def test_build_slot_catalog_matches_engine_order():
    ...


def test_translate_plan_to_actions_maps_missing_slots_to_zero():
    ...


def test_translate_plan_to_actions_maps_declared_slots_to_counts():
    ...


def test_validate_distribution_rejects_unknown_slot():
    ...


def test_validate_distribution_rejects_over_capacity():
    ...


def test_validate_distribution_rejects_total_colonists_overflow():
    ...


def test_apply_distribution_plan_advances_phase():
    ...
```

검증 포인트:

- island 0~11, city 12~23 순서
- `69 + amount` 생성 규칙
- 누락 슬롯은 `0` 처리
- invalid slot id / capacity overflow / colonist overflow 거절

### C. `backend/tests/test_channel_mayor_distribute.py`

목적:

- 사람 Mayor의 표준 공개 입력 경로를 channel API로 고정

초안:

```py
def test_channel_mayor_distribute_accepts_placements_payload(client, db):
    ...


def test_channel_mayor_distribute_returns_updated_state(client, db):
    ...


def test_channel_mayor_distribute_rejects_invalid_slot_id(client, db):
    ...


def test_channel_mayor_distribute_rejects_not_your_turn(client, db):
    ...
```

검증 포인트:

- endpoint path
- auth/ownership
- `placements` payload 형식
- 성공 시 최신 state 반환

### D. `backend/tests/test_legacy_mayor_compat.py`

목적:

- legacy는 진실 소스가 아니라 shared orchestrator 재사용층임을 고정

초안:

```py
def test_legacy_mayor_distribute_reuses_shared_orchestrator(client):
    ...


def test_legacy_payload_is_translated_to_same_internal_plan(client):
    ...
```

검증 포인트:

- legacy와 channel이 같은 service를 타는지
- contract drift가 다시 생기지 않는지

### E. `frontend/src/components/__tests__/mayorPlanBuilder.test.ts`

목적:

- 프론트가 서버 상태에서 받은 `slot_id`를 기준으로 payload를 만든다는 계약 고정

초안:

```ts
it('builds placements from island and city slot ids', () => {
  ...
})

it('omits zero-count slots', () => {
  ...
})

it('does not synthesize slot ids on the client', () => {
  ...
})
```

검증 포인트:

- `mayorPending -> placements[]` 변환
- zero count omission
- `slot_id` 없으면 제출하지 않음

### F. `frontend/src/App.mayor.test.tsx`

목적:

- 최종 confirm 시 channel mayor-distribute endpoint로 요청이 나가는지 고정

초안:

```ts
it('posts placements payload to channel mayor-distribute endpoint', async () => {
  ...
})

it('shows server error when mayor-distribute fails', async () => {
  ...
})
```

검증 포인트:

- endpoint path
- auth header
- payload shape
- 에러 반영

## 2단계 구현 순서 체크리스트

이 순서는 실제 코드 작업 시 충돌과 재작업을 줄이기 위한 권장 순서다.

### Step 1. Serializer contract 먼저 고정

- `state_serializer.py`에 `slot_id`, `capacity` 등 필요한 필드 추가
- `types/gameState.ts`에 대응 타입 추가
- serializer contract test 통과

완료 기준:

- 프론트가 slot identity를 자체 계산하지 않아도 된다.

### Step 2. Orchestrator 신설

- `backend/app/services/mayor_orchestrator.py` 생성
- `build_slot_catalog`, `validate_distribution_plan`, `translate_plan_to_actions`, `apply_distribution_plan` 구현
- orchestrator unit tests 통과

완료 기준:

- 사람 Mayor plan을 sequential action 목록으로 안정적으로 변환 가능

### Step 3. Channel endpoint 추가

- `backend/app/api/channel/game.py`에 `mayor-distribute` endpoint 추가
- endpoint가 shared orchestrator를 사용하도록 연결
- channel endpoint tests 통과

완료 기준:

- 사람 Mayor는 channel 경로로 최종 제출 가능

### Step 4. Frontend payload builder 연결

- `App.tsx`의 `confirmMayorDistribution()`를 channel mayor-distribute 호출로 전환
- `channelActionIndex.mayorIsland/mayorCity` 직접 사용 제거
- frontend payload tests 통과

완료 기준:

- 프론트가 더 이상 Mayor action index를 직접 생성하지 않음

### Step 5. Legacy 호환층 축소

- `legacy/actions.py`의 mayor-distribute를 shared orchestrator 재사용 구조로 정리
- 필요 시 old payload를 new placements로 번역하는 adapter만 유지
- legacy compatibility tests 통과

완료 기준:

- legacy는 진실 소스가 아니라 adapter 계층

### Step 6. History / locale 정리

- `HistoryPanel.tsx`, locales 정리
- 사람 Mayor는 최종 제출 단위 히스토리만 노출
- history regression tests 통과

완료 기준:

- 사용자 히스토리가 toggle spam에 의존하지 않음

### Step 7. 최종 회귀 점검

- serializer contract
- orchestrator unit
- channel endpoint
- frontend payload
- legacy compatibility
- history regression

이 6개 축을 모두 다시 실행

완료 기준:

- 방향 B 구조가 테스트와 함께 고정됨

## 바로 다음 실행 순서

가장 바로 시작할 작업 순서는 아래와 같다.

1. `backend/tests/test_mayor_serializer_contract.py` 추가
2. `backend/tests/test_mayor_orchestrator.py` 추가
3. `backend/app/services/mayor_orchestrator.py` 생성
4. `backend/app/services/state_serializer.py` 수정
5. `backend/app/api/channel/game.py` 수정
6. `frontend/src/types/gameState.ts` 수정
7. `frontend/src/App.tsx` 수정

이 순서로 가면 channel 우선 원칙과 TDD 원칙을 둘 다 지킬 수 있다.


api 중 레거시 api는 나중에 모든 기능을 channel이 포함 할 수 있게 리펙토링할거야 
즉 최대한 channel api에 넣어줘 
