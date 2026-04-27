# Action Index Contract Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** settler/mayor 페이즈에서 사람 액션이 의미와 다르게(corn→coffee, 시장 위치 어긋남) 적용되는 contract bug를 fix한다. backend serializer가 face_up/mayor_legal에 위치 인덱스(`8 + i`, `120 + slot_idx`)를 실어 보내고 엔진은 의미 인덱스(`8 + tile.value`)로 디코드하던 mismatch를, **explicit dual-field (`engine_action_index` + `display_position` + `canonical_id`) + ingress canonical guard** 방식으로 닫는다.

**Architecture:** outbound rich state에 의미와 위치를 명시 분리하고, ingress payload에 옵셔널 `canonical_id`를 받아 디코드 의미와 mismatch 시 fail-closed 422로 거절한다. Backwards-compat을 위해 `action_index` 단일 필드는 `engine_action_index`와 같은 값을 그대로 둔다. transition envelope에는 `submitted_canonical_id`, `decoded_canonical_id`, `canonical_id_match` 필드를 추가해 contract observability를 확보한다.

**Tech Stack:** Python (FastAPI, Pydantic v2, pytest), TypeScript (React, Vitest), Docker Compose.

**Spec:** [docs/superpowers/specs/2026-04-27-action-index-contract-fix-design.md](../specs/2026-04-27-action-index-contract-fix-design.md)

**Branch:** `refactor/adapter` (commit OK, push only on user verification)

**Test execution rule:** 모든 테스트는 `docker compose exec backend pytest …` / `docker compose exec frontend npx vitest …`만 사용. 로컬 실행 금지.

---

## File Structure

### Created
- `backend/tests/test_action_index_contract.py` — settler face_up + mayor island/city `engine_action_index` 회귀
- `backend/tests/test_action_request_canonical_guard.py` — ingress `canonical_id` mismatch/match/omitted 회귀
- `frontend/src/__tests__/App.action-index-contract.test.tsx` — corn 클릭 시 `engine_action_index`와 `canonical_id` 전송 회귀

### Modified
- `backend/app/services/contracts.py` — `CANONICAL_ACTION_VERSION` re-export 또는 helper (필요 시)
- `backend/app/services/state_serializer_support.py:155-163` — `face_up` 빌더 의미 인덱스화
- `backend/app/services/state_serializer.py:_build_mayor_meta` — `mayor_island_actions`, `mayor_city_actions` 추가
- `backend/app/schemas/game.py:9-13` — `canonical_id: Optional[str]` 추가
- `backend/app/api/channel/game.py:60-75` — canonical guard + 422 + 구조화 로그
- `backend/app/services/ml_logger.py` — transition envelope에 `submitted_canonical_id`, `decoded_canonical_id`, `canonical_id_match` 추가
- `backend/app/services/game_service.py` (필요 시) — ml_logger 호출 시 새 필드 전달
- `backend/tests/test_ml_logger.py` — 새 envelope 필드 회귀 테스트 한 개 추가
- `backend/tests/test_game_action.py` — canonical guard 통합 회귀 한 개 추가
- `frontend/src/types/gameState.ts` — `face_up` entry / mayor_*_actions 타입 확장
- `frontend/src/App.tsx:485-499, 770-779` — `channelAction(actionIndex, canonicalId?)`, quarry=13, settler 시 `engine_action_index` 사용
- `frontend/src/components/MayorSequentialPanel.tsx` — `mayor_island_actions`/`mayor_city_actions` 직접 사용
- `frontend/src/components/AvailablePlantations.tsx` — 새 face_up entry 타입 호환

---

## Phase 1: 모든 failing test를 먼저 RED로 잠근다

### Task 1: backend `test_action_index_contract.py` (settler face_up)

**Files:**
- Create: `backend/tests/test_action_index_contract.py`

- [ ] **Step 1: failing test 작성**

```python
"""Action index contract regression: face_up + mayor metas use semantic engine_action_index."""
from __future__ import annotations

from app.services.engine_gateway.constants import Good, TileType
from app.services.state_serializer_support import serialize_common_board


class _StubGame:
    """Minimal stub mirroring PuertoRicoGame fields used by serialize_common_board."""

    def __init__(self, face_up_tiles):
        self.face_up_plantations = face_up_tiles
        self.available_roles = []
        self.roles_in_play = []
        self.role_doubloons = {}
        self.active_role = None
        self.trading_house = []
        self.plantation_stack = []
        self.cargo_ships = []
        self.building_supply = {}
        self.quarry_stack = 0
        self.goods_supply = {g: 0 for g in Good}


def test_face_up_engine_action_index_uses_tile_type_value():
    # face_up 순서가 [CORN, COFFEE]일 때 corn entry는 8 + Good.CORN.value(=2) = 10이어야 한다.
    game = _StubGame(
        face_up_tiles=[TileType.CORN_PLANTATION, TileType.COFFEE_PLANTATION],
    )
    board = serialize_common_board(game)
    face_up = board["available_plantations"]["face_up"]

    by_type = {entry["type"]: entry for entry in face_up}
    assert by_type["corn"]["engine_action_index"] == 10
    assert by_type["coffee"]["engine_action_index"] == 8
    # backwards-compat: action_index도 같은 값(의미)이어야 한다.
    assert by_type["corn"]["action_index"] == 10
    assert by_type["coffee"]["action_index"] == 8
    # display_position은 face_up 순서를 그대로 유지한다.
    assert by_type["corn"]["display_position"] == 0
    assert by_type["coffee"]["display_position"] == 1
    # canonical_id는 settler:tile_type:{name}.
    assert by_type["corn"]["canonical_id"] == "settler:tile_type:corn"
    assert by_type["coffee"]["canonical_id"] == "settler:tile_type:coffee"
```

- [ ] **Step 2: RED 확인**

```bash
docker compose exec backend pytest backend/tests/test_action_index_contract.py::test_face_up_engine_action_index_uses_tile_type_value -q
```

Expected: FAIL (KeyError 'engine_action_index' 또는 assertion).

- [ ] **Step 3: Commit (Red lock)**

```bash
git add backend/tests/test_action_index_contract.py
git commit -m "test(action-contract): RED face_up engine_action_index uses tile_type.value"
```

---

### Task 2: mayor island/city action index regression

**Files:**
- Modify: `backend/tests/test_action_index_contract.py`

- [ ] **Step 1: failing test 두 개 추가**

```python
def test_mayor_island_actions_use_tile_type_value(make_session_in_mayor_phase):
    """mayor_island_actions의 engine_action_index는 120 + tile.value 이어야 한다."""
    session = make_session_in_mayor_phase(
        island_layout=["corn", "coffee", "indigo"],  # 빈 슬롯/미점유 가정
    )
    state = session_state_dict(session)
    actions = state["meta"]["mayor_island_actions"]

    by_tile = {a["tile_name"]: a for a in actions}
    # Good enum: COFFEE=0, TOBACCO=1, CORN=2, SUGAR=3, INDIGO=4
    assert by_tile["corn"]["engine_action_index"] == 122
    assert by_tile["coffee"]["engine_action_index"] == 120
    assert by_tile["indigo"]["engine_action_index"] == 124
    assert by_tile["corn"]["canonical_id"] == "mayor:island:tile_type:corn"


def test_mayor_city_actions_use_building_type_value(make_session_in_mayor_phase):
    """mayor_city_actions의 engine_action_index는 140 + building_type.value 이어야 한다."""
    session = make_session_in_mayor_phase(
        city_buildings=["small_market", "indigo_plant"],  # 미만 점유 가정
    )
    state = session_state_dict(session)
    actions = state["meta"]["mayor_city_actions"]

    by_name = {a["building_name"]: a for a in actions}
    # 건물별 BuildingType.value 검증 (constants에서 정확한 값을 import해 비교)
    from app.services.engine_gateway.constants import BuildingType
    for entry in actions:
        bt = BuildingType[entry["building_name"].upper()]
        assert entry["engine_action_index"] == 140 + bt.value
        assert entry["canonical_id"] == f"mayor:city:building_type:{bt.value}"
```

> **Note:** `make_session_in_mayor_phase`와 `session_state_dict`는 이 시점에서 fixture로 존재하지 않는다. Step 2에서 fixture를 먼저 추가한다.

- [ ] **Step 2: 필요한 conftest fixture 추가**

`backend/tests/conftest.py`에 fixture가 이미 있는지 grep. 없으면 `backend/tests/test_action_index_contract.py` 상단에 fixture로 추가:

```python
import pytest
from app.engine_wrapper.wrapper import EngineWrapper
from app.services.state_serializer import serialize_game_state_from_engine
from app.services.engine_gateway.constants import BuildingType, TileType


def _force_phase_mayor(engine: EngineWrapper, island_tiles, city_buildings):
    """Forcefully set engine state to MAYOR with given island/city slots."""
    # 구현 세부는 실제 EngineWrapper API에 맞춰 GREEN 단계에서 다듬는다.
    raise NotImplementedError


@pytest.fixture
def make_session_in_mayor_phase():
    def _factory(*, island_layout=None, city_buildings=None):
        engine = EngineWrapper(num_players=3)
        engine.reset()
        _force_phase_mayor(engine, island_layout or [], city_buildings or [])
        return engine
    return _factory


def session_state_dict(engine):
    return serialize_game_state_from_engine(engine, ["A", "B", "C"], game_id="test")
```

- [ ] **Step 3: RED 확인**

```bash
docker compose exec backend pytest backend/tests/test_action_index_contract.py -q
```

Expected: 3 failed (둘은 KeyError 'mayor_island_actions'/`mayor_city_actions`, 하나는 NotImplementedError 또는 assertion).

- [ ] **Step 4: Commit (Red lock)**

```bash
git add backend/tests/test_action_index_contract.py
git commit -m "test(action-contract): RED mayor island/city actions use semantic indices"
```

---

### Task 3: ingress canonical guard regression

**Files:**
- Create: `backend/tests/test_action_request_canonical_guard.py`

- [ ] **Step 1: failing tests 작성 (3 케이스)**

```python
"""Action request ingress: canonical_id mismatch returns 422; match/omitted pass."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.tests.helpers.client_fixtures import (  # 기존 helper 재사용
    bot_game_with_human_seat,
    auth_headers_for,
)


@pytest.mark.usefixtures("docker_only")
def test_canonical_id_mismatch_returns_422(client: TestClient):
    game_id, human_id = bot_game_with_human_seat()
    # 의도적으로 잘못된 canonical_id (engine은 action 8을 settler:tile_type:coffee로 디코드)
    payload = {
        "payload": {
            "schema_version": "action-request.v1",
            "action_index": 8,
            "canonical_id": "settler:tile_type:corn",  # mismatch
        }
    }
    res = client.post(
        f"/api/puco/game/{game_id}/action",
        json=payload,
        headers=auth_headers_for(human_id),
    )
    assert res.status_code == 422
    body = res.json()
    assert body["detail"]["error"] == "canonical_id_mismatch"
    assert body["detail"]["submitted_canonical_id"] == "settler:tile_type:corn"
    assert body["detail"]["decoded_canonical_id"] == "settler:tile_type:coffee"


def test_canonical_id_match_processes_action(client: TestClient):
    game_id, human_id = bot_game_with_human_seat()
    payload = {
        "payload": {
            "schema_version": "action-request.v1",
            "action_index": 8,
            "canonical_id": "settler:tile_type:coffee",
        }
    }
    res = client.post(
        f"/api/puco/game/{game_id}/action",
        json=payload,
        headers=auth_headers_for(human_id),
    )
    # mask가 false라면 200/400 둘 다 가능 — 핵심은 422가 아니어야 한다는 것.
    assert res.status_code != 422


def test_canonical_id_omitted_processes_action(client: TestClient):
    game_id, human_id = bot_game_with_human_seat()
    payload = {
        "payload": {
            "schema_version": "action-request.v1",
            "action_index": 8,
        }
    }
    res = client.post(
        f"/api/puco/game/{game_id}/action",
        json=payload,
        headers=auth_headers_for(human_id),
    )
    assert res.status_code != 422
```

> **Note:** `bot_game_with_human_seat`, `auth_headers_for` helper는 기존 테스트(예: `test_game_action.py`)의 패턴을 그대로 사용한다. 없으면 그곳에서 import하거나 본 파일에서 inline 구성. 첫 RED 확인은 mismatch 422 케이스만으로도 충분.

- [ ] **Step 2: RED 확인**

```bash
docker compose exec backend pytest backend/tests/test_action_request_canonical_guard.py -q
```

Expected: 3 failed (현재는 422가 안 나오고 200/400/extra=forbid 422 중 하나가 나옴).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_action_request_canonical_guard.py
git commit -m "test(action-contract): RED ingress canonical_id guard returns 422 on mismatch"
```

---

### Task 4: ml_logger transition envelope 회귀

**Files:**
- Modify: `backend/tests/test_ml_logger.py`

- [ ] **Step 1: 기존 파일 확인**

```bash
docker compose exec backend pytest backend/tests/test_ml_logger.py -q --collect-only
```

기존 transition envelope 테스트 패턴 확인.

- [ ] **Step 2: failing test 추가**

`test_ml_logger.py` 끝에 추가:

```python
def test_transition_envelope_includes_canonical_decoded(captured_log):
    logger = MLLogger(sink=captured_log.append)
    logger.log_transition(
        trace_id="t-1",
        game_id="g-1",
        actor_id="player_0",
        action_index=8,
        submitted_canonical_id="settler:tile_type:coffee",
        decoded_canonical_id="settler:tile_type:coffee",
        state_before={"state_kind": "model-observation", "schema_version": "model-observation.v1"},
        state_after={"state_kind": "model-observation", "schema_version": "model-observation.v1"},
        reward=0.0,
        done=False,
    )
    assert len(captured_log) == 1
    env = captured_log[0]
    assert env["schema_version"] == "transition-envelope.v1"
    assert env["submitted_action_index"] == 8
    assert env["submitted_canonical_id"] == "settler:tile_type:coffee"
    assert env["decoded_canonical_id"] == "settler:tile_type:coffee"
    assert env["canonical_id_match"] is True
```

> 기존 `MLLogger.log_transition` signature가 다르면 테스트는 그 signature로 RED를 만들고 GREEN 단계에서 signature를 확장한다.

- [ ] **Step 3: RED 확인**

```bash
docker compose exec backend pytest backend/tests/test_ml_logger.py::test_transition_envelope_includes_canonical_decoded -q
```

Expected: FAIL (TypeError unexpected kwarg 또는 KeyError).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_ml_logger.py
git commit -m "test(action-contract): RED transition envelope carries canonical decoded fields"
```

---

### Task 5: frontend `App.action-index-contract.test.tsx`

**Files:**
- Create: `frontend/src/__tests__/App.action-index-contract.test.tsx`

- [ ] **Step 1: failing test 작성**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import App from '../App';
import { stubGameState, stubAuthOk, stubFetch } from './helpers';

describe('action_index contract — settler corn click', () => {
  beforeEach(() => {
    stubAuthOk();
  });

  it('sends engine_action_index and canonical_id when corn is clicked in settler phase', async () => {
    const fetchMock = stubFetch();
    const state = stubGameState({
      phase: 'settler_action',
      faceUp: [
        { type: 'corn', engine_action_index: 10, action_index: 10, display_position: 0, canonical_id: 'settler:tile_type:corn' },
        { type: 'coffee', engine_action_index: 8, action_index: 8, display_position: 1, canonical_id: 'settler:tile_type:coffee' },
      ],
    });
    render(<App initialState={state} />);

    fireEvent.click(screen.getByText(/corn/i));

    const actionCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/action'));
    expect(actionCall).toBeDefined();
    const body = JSON.parse(actionCall![1].body);
    expect(body.payload.action_index).toBe(10);
    expect(body.payload.canonical_id).toBe('settler:tile_type:corn');
  });
});
```

> `stubGameState`, `stubAuthOk`, `stubFetch`는 `frontend/src/__tests__/helpers.ts`에 이미 있는 패턴을 따른다. 없으면 GREEN 단계에서 helper를 추가한다.

- [ ] **Step 2: RED 확인**

```bash
docker compose exec frontend npx vitest run src/__tests__/App.action-index-contract.test.tsx
```

Expected: FAIL (타입 또는 click이 잘못된 action_index를 보냄).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/App.action-index-contract.test.tsx
git commit -m "test(action-contract): RED frontend sends engine_action_index + canonical_id on corn click"
```

---

## Phase 2: Backend GREEN — outbound state 의미 인덱스화

### Task 6: `state_serializer_support.serialize_common_board` 의미 인덱스 + canonical_id

**Files:**
- Modify: `backend/app/services/state_serializer_support.py:155-163`

- [ ] **Step 1: 기존 face_up 빌더 코드 확인**

```bash
sed -n '155,170p' backend/app/services/state_serializer_support.py
```

(실제로는 Read 도구 사용; bash 예시는 reviewer 가독성용)

- [ ] **Step 2: face_up 빌더 교체**

다음과 같이 교체. **TileType.QUARRY는 13, plantation은 8 + tile.value.**

```python
def _settler_action_for_tile(tile: TileType) -> tuple[int, str]:
    if tile == TileType.QUARRY:
        return 13, "settler:quarry"
    name = TILE_TO_STR.get(tile, "empty")
    return 8 + int(tile.value), f"settler:tile_type:{name}"


face_up = []
for i, tile in enumerate(game.face_up_plantations):
    engine_idx, canonical_id = _settler_action_for_tile(tile)
    face_up.append({
        "type": TILE_TO_STR.get(tile, "empty"),
        "display_position": i,
        "engine_action_index": engine_idx,
        "action_index": engine_idx,  # backwards-compat: legacy clients receive semantic index too
        "canonical_id": canonical_id,
    })
```

> Good enum value와 TileType plantation value의 매핑이 동일한지 확인 후 진행. 다르면 `int(tile.value)` 부분을 `Good`으로 변환하는 별도 헬퍼로 감싼다 (예: `TILE_TO_GOOD = {COFFEE_PLANTATION: Good.COFFEE, ...}`).

- [ ] **Step 3: 회귀 확인**

```bash
docker compose exec backend pytest \
  backend/tests/test_action_index_contract.py::test_face_up_engine_action_index_uses_tile_type_value \
  backend/tests/test_state_serializer_action_index.py \
  -q
```

Expected: face_up 테스트 PASS, 기존 state_serializer_action_index 테스트는 PASS 유지(backwards-compat 보장 가정).

- [ ] **Step 4: 기존 테스트 깨졌으면 진단**

만약 `test_state_serializer_action_index.py`가 깨졌다면 **bypass 금지**. 기존 테스트가 positional `8 + i`를 가정하고 있는지 코드를 읽고, 의미 인덱스로 마이그레이션 후 commit. 비파괴 수정 원칙에 따라 working path 자체를 삭제하지는 않는다.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/state_serializer_support.py backend/tests/test_state_serializer_action_index.py
git commit -m "fix(serializer): face_up uses semantic engine_action_index + canonical_id"
```

---

### Task 7: `_build_mayor_meta`에 `mayor_island_actions` 추가

**Files:**
- Modify: `backend/app/services/state_serializer.py:31-63`

- [ ] **Step 1: 현재 _build_mayor_meta 코드 확인**

(이미 spec에서 본 형태. raw idx만 push하고 있음.)

- [ ] **Step 2: `mayor_island_actions` 빌더 추가**

```python
mayor_island_actions = []
for i, t in enumerate(player.island_board):
    if t.tile_type == TileType.EMPTY or t.is_occupied:
        continue
    tile_name = TILE_TO_STR.get(t.tile_type, "empty")
    engine_idx = 120 + int(t.tile_type.value)
    mayor_island_actions.append({
        "display_position": i,
        "engine_action_index": engine_idx,
        "tile_name": tile_name,
        "canonical_id": f"mayor:island:tile_type:{tile_name}",
    })
```

`return` dict에 `"mayor_island_actions": mayor_island_actions` 추가.

- [ ] **Step 3: 회귀 확인**

```bash
docker compose exec backend pytest backend/tests/test_action_index_contract.py::test_mayor_island_actions_use_tile_type_value -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/state_serializer.py
git commit -m "fix(serializer): emit mayor_island_actions with semantic engine_action_index"
```

---

### Task 8: `_build_mayor_meta`에 `mayor_city_actions` 추가

**Files:**
- Modify: `backend/app/services/state_serializer.py:31-63`

- [ ] **Step 1: city 빌더 추가**

```python
mayor_city_actions = []
for i, b in enumerate(player.city_board):
    if b.building_type in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
        continue
    cap = BUILDING_DATA[b.building_type][2]
    if b.colonists >= cap:
        continue
    bname = building_name(b.building_type)
    engine_idx = 140 + int(b.building_type.value)
    mayor_city_actions.append({
        "display_position": i,
        "engine_action_index": engine_idx,
        "building_name": bname,
        "canonical_id": f"mayor:city:building_type:{int(b.building_type.value)}",
    })
```

return dict에 `"mayor_city_actions": mayor_city_actions` 추가.

- [ ] **Step 2: 회귀 확인**

```bash
docker compose exec backend pytest backend/tests/test_action_index_contract.py -q
```

Expected: 3 PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/state_serializer.py
git commit -m "fix(serializer): emit mayor_city_actions with semantic engine_action_index"
```

---

## Phase 3: Backend GREEN — ingress canonical guard

### Task 9: `ActionRequestPayload`에 `canonical_id` 옵셔널 필드

**Files:**
- Modify: `backend/app/schemas/game.py:9-13`

- [ ] **Step 1: 필드 추가**

```python
class ActionRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = ACTION_REQUEST_SCHEMA_VERSION
    action_index: int
    canonical_id: Optional[str] = None
```

`from typing import Optional` import 누락 여부 확인.

- [ ] **Step 2: 기존 schema 회귀**

```bash
docker compose exec backend pytest backend/tests/test_game_action.py -q
```

Expected: 기존 테스트 통과 (canonical_id 미제공 시에도 동작).

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/game.py
git commit -m "feat(schema): add optional canonical_id to ActionRequestPayload"
```

---

### Task 10: `perform_action` ingress에 canonical guard + 422

**Files:**
- Modify: `backend/app/api/channel/game.py:44-75`

- [ ] **Step 1: guard 로직 추가**

```python
from app.services.canonical_action import _describe_action

# inside perform_action, after action_int 추출
submitted_canonical = action_data.payload.canonical_id
decoded = _describe_action(action_int, state={})  # state 인자 사용 안하므로 빈 dict 안전
decoded_canonical = decoded["canonical_id"] if decoded else None

if submitted_canonical is not None and decoded_canonical is not None:
    if submitted_canonical != decoded_canonical:
        logger.warning(
            "[ACTION_TRACE] channel_action_canonical_mismatch game=%s actor=%s action=%s submitted=%s decoded=%s",
            game_id, actor_id, action_int, submitted_canonical, decoded_canonical,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "canonical_id_mismatch",
                "submitted_canonical_id": submitted_canonical,
                "decoded_canonical_id": decoded_canonical,
                "action_index": action_int,
            },
        )

# 구조화 ACTION_TRACE 확장
logger.warning(
    "[ACTION_TRACE] channel_action_request game=%s actor=%s action=%s "
    "submitted_canonical_id=%s decoded_canonical_id=%s match=%s schema=%s",
    game_id, actor_id, action_int,
    submitted_canonical, decoded_canonical,
    "match" if submitted_canonical == decoded_canonical else (
        "missing" if submitted_canonical is None else "mismatch"
    ),
    action_data.payload.schema_version,
)
```

> **주의**: `_describe_action`은 현재 private이지만 동일 패키지에서 임포트 가능. 추후 public alias가 필요하면 `canonical_action.py`에 `describe_action = _describe_action` 추가 고려.

- [ ] **Step 2: 회귀 확인**

```bash
docker compose exec backend pytest \
  backend/tests/test_action_request_canonical_guard.py \
  backend/tests/test_game_action.py \
  -q
```

Expected: 신규 3 PASS, 기존 game_action 회귀 PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/channel/game.py
git commit -m "feat(ingress): canonical_id mismatch returns 422 with decoded payload"
```

---

### Task 11: `MLLogger.log_transition` envelope 필드 확장

**Files:**
- Modify: `backend/app/services/ml_logger.py`
- Modify: `backend/app/services/game_service.py` (호출부)

- [ ] **Step 1: signature 확장**

`log_transition`에 옵셔널 kwargs 추가:

```python
def log_transition(
    self,
    *,
    trace_id: str,
    game_id: str,
    actor_id: str,
    action_index: int,
    state_before: dict,
    state_after: dict,
    reward: float,
    done: bool,
    submitted_canonical_id: Optional[str] = None,
    decoded_canonical_id: Optional[str] = None,
) -> None:
    ...
    envelope = {
        "schema_version": TRANSITION_ENVELOPE_SCHEMA_VERSION,
        "trace_id": trace_id,
        "game_id": game_id,
        "actor_id": actor_id,
        "submitted_action_index": action_index,
        "submitted_canonical_id": submitted_canonical_id,
        "decoded_canonical_id": decoded_canonical_id,
        "canonical_id_match": (
            None if submitted_canonical_id is None
            else submitted_canonical_id == decoded_canonical_id
        ),
        ...
    }
```

> 기존 envelope 필드는 그대로 유지. 새 필드는 모두 옵셔널.

- [ ] **Step 2: `game_service.process_action`에서 새 필드 전달**

decoded canonical을 ingress에서 이미 계산했다면 transition info에 실어서 ml_logger에 전달. action_value/random/ppo 봇 경로는 `submitted_canonical_id=None`로 호출.

- [ ] **Step 3: 회귀 확인**

```bash
docker compose exec backend pytest \
  backend/tests/test_ml_logger.py \
  backend/tests/test_game_service_side_effect_fail_open.py \
  -q
```

Expected: 신규 envelope test PASS, 기존 fail-open 회귀 PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/ml_logger.py backend/app/services/game_service.py
git commit -m "feat(ml-logger): transition envelope carries canonical decoded fields"
```

---

## Phase 4: Frontend GREEN

### Task 12: `frontend/src/types/gameState.ts` 타입 확장

**Files:**
- Modify: `frontend/src/types/gameState.ts`

- [ ] **Step 1: face_up entry 타입 확장**

```ts
export interface FaceUpPlantationEntry {
  type: string;
  action_index: number;
  engine_action_index: number;
  display_position: number;
  canonical_id: string;
}

export interface MayorActionEntry {
  display_position: number;
  engine_action_index: number;
  canonical_id: string;
  tile_name?: string;
  building_name?: string;
}

export interface Meta {
  // 기존 필드 ...
  mayor_island_actions?: MayorActionEntry[];
  mayor_city_actions?: MayorActionEntry[];
}
```

기존 `face_up` 사용 위치(예: `AvailablePlantations`)에서 string|object 양쪽 지원하던 부분을 검토.

- [ ] **Step 2: 타입 체크**

```bash
docker compose exec frontend npx tsc --noEmit
```

Expected: 타입 에러 없음 (있다면 GREEN 단계에서 함께 해결).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/gameState.ts
git commit -m "feat(types): add engine_action_index/canonical_id to face_up + mayor actions"
```

---

### Task 13: `App.tsx` `channelAction` signature + settler/quarry/build 적용

**Files:**
- Modify: `frontend/src/App.tsx:485-499, 770-779, 861-866`

- [ ] **Step 1: `channelAction` 확장**

```ts
async function channelAction(actionIndex: number, canonicalId?: string) {
  if (!gameId) return;
  saving = true;
  try {
    const res = await fetch(`${BACKEND}/api/puco/game/${gameId}/action`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payload: {
          action_index: actionIndex,
          ...(canonicalId ? { canonical_id: canonicalId } : {}),
        },
      }),
    });
    // 기존 에러 처리 유지
  } finally {
    saving = false;
  }
}
```

- [ ] **Step 2: `doSettlePlantation`에서 `engine_action_index` 사용**

```ts
async function doSettlePlantation(type: string, useHospice: boolean) {
  void useHospice;
  if (!state || saving) return;
  if (type === 'quarry') {
    await channelAction(13, 'settler:quarry');  // quarry는 13으로 정식화
    return;
  }
  const entry = state.common_board.available_plantations.face_up.find(p => p.type === type);
  if (entry) {
    await channelAction(entry.engine_action_index ?? entry.action_index, entry.canonical_id);
  }
}
```

- [ ] **Step 3: `build`에서도 canonical_id 동봉**

```ts
async function build(buildingName: string) {
  if (!state || notMyTurn()) return;
  const buildingData = state.common_board.available_buildings[buildingName];
  if (!buildingData?.action_index) return;
  // canonical_id는 backend가 builder:building:{n} 형태로 줄 수 있음. 미제공이면 omitted (서버는 omit 허용)
  await channelAction(buildingData.action_index, buildingData.canonical_id);
}
```

> serializer에 builder action용 canonical_id가 아직 없으면 이번 PR 범위에선 omitted로 두고 별도 follow-up.

- [ ] **Step 4: 회귀 확인**

```bash
docker compose exec frontend npx vitest run src/__tests__/App.action-index-contract.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): use engine_action_index + canonical_id, quarry=13"
```

---

### Task 14: `MayorSequentialPanel.tsx` `mayor_*_actions` 사용

**Files:**
- Modify: `frontend/src/components/MayorSequentialPanel.tsx:42-114`

- [ ] **Step 1: meta에서 새 actions 사용**

```tsx
const islandActions = meta.mayor_island_actions ?? [];
const cityActions = meta.mayor_city_actions ?? [];
const remaining = meta.mayor_remaining_colonists ?? player.city.colonists_unplaced;
```

각 버튼 onClick:
```tsx
{islandActions.map((entry) => {
  const isLegal = (actionMask?.[entry.engine_action_index] ?? 0) === 1;
  return (
    <button
      key={`island-${entry.display_position}`}
      type="button"
      className="mayor-slot-btn mayor-slot-btn--island"
      disabled={disabled || !isLegal}
      onClick={() => isLegal && onPlaceColonist?.(entry.engine_action_index, entry.canonical_id)}
    >
      {slotLabel('island', entry.display_position, player, t)}
    </button>
  );
})}
```

`onPlaceColonist` signature를 `(actionIndex: number, canonicalId?: string) => void`로 확장. App.tsx의 `placeMayorColonist`도 같이 수정.

- [ ] **Step 2: 기존 mayor_legal_island_slots fallback 유지**

`mayor_island_actions`가 없을 때(이전 backend 응답 호환) 기존 경로로 fallback. 이번 PR에서 backend도 같이 배포되니 fallback은 단기적이지만 안전망으로 둔다.

- [ ] **Step 3: 회귀 확인**

```bash
docker compose exec frontend npx vitest run \
  src/components/__tests__/MayorSequentialPanel.test.tsx \
  src/__tests__/App.mayor-flow.test.tsx
```

Expected: PASS (기존 테스트는 fallback 경로로 통과, 신규 동작은 spec 의도대로).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/MayorSequentialPanel.tsx frontend/src/App.tsx
git commit -m "feat(frontend): MayorSequentialPanel uses semantic engine_action_index + canonical_id"
```

---

## Phase 5: 회귀 묶음 + clean-up

### Task 15: 1차 contract 회귀 (Docker)

- [ ] **Step 1: 명령 실행**

```bash
docker compose exec backend pytest \
  backend/tests/test_action_index_contract.py \
  backend/tests/test_action_request_canonical_guard.py \
  backend/tests/test_state_serializer_action_index.py \
  backend/tests/test_ml_logger.py \
  backend/tests/test_replay_logger.py \
  backend/tests/test_game_action.py \
  backend/tests/test_game_service_side_effect_fail_open.py \
  -q
```

Expected: 전부 PASS.

- [ ] **Step 2: WS / serializer 인접 회귀**

```bash
docker compose exec backend pytest \
  backend/tests/test_priority2_ws_delivery_contract.py \
  backend/tests/test_phase_action_edge_cases.py \
  backend/tests/test_game_ws_auth_contract.py \
  backend/tests/test_replay_logging_integration.py \
  backend/tests/test_replay_logger_rich_state.py \
  -q
```

Expected: 전부 PASS (기존 04-21 회귀 보존).

- [ ] **Step 3: frontend 회귀**

```bash
docker compose exec frontend npx vitest run
```

Expected: 전부 PASS.

- [ ] **Step 4: 결과 정리**

실패가 있으면 비파괴 원칙대로 진단 후 fix. 통과하면 다음 단계로.

---

### Task 16: spec 9절 작업 분해 cross-check 후 PR description 초안

- [ ] **Step 1: 변경 요약**

본 plan의 Phase 1–5에서 발생한 commit 리스트를 정리해 PR description 초안 작성. (push는 사용자 검증 후.)

- [ ] **Step 2: spec 갱신 (필요 시)**

만약 구현 중 spec과 다른 결정이 발생하면 spec 8절 결정 로그에 한 줄 추가하고 commit.

- [ ] **Step 3: Commit (필요 시)**

```bash
git add docs/superpowers/specs/2026-04-27-action-index-contract-fix-design.md
git commit -m "docs(spec): record implementation deviations from initial design"
```

---

## 비파괴 원칙 재확인

- 기존 정상 경로(턴 검증, legal action 계산, websocket 전달, serializer 출력)는 임의로 제거하지 않는다.
- replay/commentary, ml_logger fail-open 정책은 유지.
- canonical guard로 인한 새로운 422는 기존 정상 트래픽을 깨뜨리지 않는다 (`canonical_id`는 옵셔널).
- "테스트 통과를 위해 working path 삭제 금지" — 04-21/04-23 보고서 원칙.

## 실행 옵션

플랜 작성 완료. 두 가지 실행 방식:

1. **Subagent-Driven (recommended)** — task별 fresh subagent + 두 단계 review
2. **Inline Execution** — 이 세션에서 batch 실행, checkpoint마다 사용자 review

선택해 주세요.
