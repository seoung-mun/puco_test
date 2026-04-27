# Model Bundle Adapter Implementation Spec

작성일: 2026-04-19
기반 문서: `design/2026-04-19_model_bundle_adapter_serving_design.md`
브랜치: `refactor/adapter`

---

## 1. Overview

현재 backend는 `pr_env.py`의 obs/action space에 직접 결합되어 있다.
이 구현은 **Canonical State + Model Bundle Adapter Registry** 구조로 개편하여,
이후 새 모델 온보딩 시 backend 코드 수정 없이 서빙이 가능하도록 한다.

### 핵심 결정 사항 (brainstorming 확정)

| 항목 | 결정 |
|------|------|
| 구현 범위 | Phase 0~5 전체 |
| canonical state 접근 | (B) state_serializer 기반, adapter/decode 최적화 재정의 |
| rule-based bots | (B) 기존 경로 유지, model-file bots만 adapter 경로 |
| adapter 모듈 위치 | (C) base + concrete 모두 `PuCo_RL/common/`, backend는 동적 import |
| 테스트 | Docker에서만 실행 (`docker compose exec backend pytest`) |

### Target Architecture

```text
Web / Public API
    |
    v
Castone Backend
    |- EngineWrapper / Game State
    |- CanonicalStateBuilder          [NEW]
    |- CanonicalActionCatalog         [NEW]
    |- ModelBundleRegistry            [ENHANCED]
    |- AdapterRuntime                 [NEW]
    |
    v
Model Bundle (in PuCo_RL/models/<bundle_id>/)
    |- checkpoint.pth
    |- manifest.json
    |- obs_spec.json
    |- action_spec.json
    |- adapter module (PuCo_RL/common/adapter.py)
```

---

## 2. File Inventory

### 새로 생성

| 파일 | 역할 |
|------|------|
| `backend/app/services/canonical_state.py` | CanonicalStateBuilder - engine state -> canonical dict |
| `backend/app/services/canonical_action.py` | CanonicalActionCatalog - legal actions -> semantic catalog |
| `backend/app/services/adapter_runtime.py` | AdapterRuntime - bundle/adapter 로딩 및 추론 실행 |
| `PuCo_RL/common/base_adapter.py` | PolicyAdapter ABC |
| `PuCo_RL/common/semantic293_adapter.py` | 현재 293-dim 모델용 concrete adapter |
| `PuCo_RL/common/bundle.py` | Bundle writer/loader utility |
| `backend/tests/test_canonical_state.py` | canonical state 테스트 |
| `backend/tests/test_canonical_action.py` | canonical action catalog 테스트 |
| `backend/tests/test_adapter_runtime.py` | adapter runtime 테스트 |
| `backend/tests/test_bundle_integration.py` | bundle 통합 테스트 |

### 수정

| 파일 | 변경 내용 |
|------|-----------|
| `backend/app/services/bot_service.py` | adapter runtime 경로 추가, env flatten 의존 제거 |
| `backend/app/services/model_registry.py` | bundle manifest v2 지원 추가 |
| `backend/app/services/agent_registry.py` | bundle-based bot type 라우팅 추가 |
| `backend/app/services/agents/wrappers.py` | `_adapt_obs_dim` 제거, adapter 위임 |
| `backend/app/services/replay_logger.py` | bundle/adapter metadata 기록 |
| `PuCo_RL/common/adapter.py` | base_adapter re-export |

### 삭제 (Phase 5)

| 대상 | 사유 |
|------|------|
| `wrappers.py:_adapt_obs_dim()` | adapter가 대체 |
| `bot_service.py:_build_obs_space()` | canonical state가 대체 |
| `model_registry.py:get_ppo_pr_server_bootstrap_profile()` | bundle manifest가 대체 |

---

## 3. Canonical State v1 Schema

### 설계 철학

- source: `engine.env.game` (state_serializer와 같은 원천)
- 목적: 모델 서빙/adapter decode 최적화 (프론트 표시용 아님)
- 포함: game logic 판단에 필요한 모든 필드
- 제외: UI display label, 정렬 순서, 문구, 중복 편의 필드

### Schema 정의

```python
# canonical_state.py - build_canonical_state() 반환 타입

CanonicalState = {
    "schema_version": "castone.canonical-state.v1",

    # ── meta ──
    "meta": {
        "phase_id": int,              # Phase enum value (0-8, None->8)
        "current_player_idx": int,    # 0-based
        "governor_idx": int,
        "round": int,
        "step_count": int,
        "num_players": int,
    },

    # ── global ──
    "global": {
        "vp_supply": int,
        "colonist_supply": int,
        "colonist_ship": int,
        "goods_supply": {             # {good_name: count}
            "corn": int,
            "indigo": int,
            "sugar": int,
            "tobacco": int,
            "coffee": int,
        },
        "trading_house": [str, ...],  # list of good names in trading house
        "trading_house_count": int,
        "cargo_ships": [
            {
                "capacity": int,
                "good": str | None,   # good name or None
                "load": int,
                "space": int,
            },
            # ... per ship
        ],
        "available_roles": [int, ...],     # Role enum values
        "role_doubloons": {int: int, ...}, # role_value -> bonus doubloons
        "face_up_plantations": [int, ...], # TileType enum values
        "quarry_supply": int,
        "game_progress": float,           # 0-1, max(vp_depletion, city_fill, colonist_depletion)
    },

    # ── players ──
    "players": [
        {
            "idx": int,
            "doubloons": int,
            "vp_chips": int,
            "goods": {                     # {good_name: count}
                "corn": int,
                "indigo": int,
                "sugar": int,
                "tobacco": int,
                "coffee": int,
            },
            "unplaced_colonists": int,
            "empty_island_spaces": int,
            "empty_city_spaces": int,

            # island board - adapter decode에 필요
            "island_tiles": [
                {
                    "slot_idx": int,
                    "tile_type": int,      # TileType enum value
                    "is_occupied": bool,
                },
                # ... per slot
            ],

            # city board - adapter decode에 필요
            "city_buildings": [
                {
                    "slot_idx": int,
                    "building_type": int,  # BuildingType enum value
                    "colonists": int,
                    "max_colonists": int,
                },
                # ... per slot (OCCUPIED_SPACE 제외)
            ],

            # derived - adapter decode 전용
            "has_building": {int: bool, ...},   # BuildingType -> owned?
            "building_colonists": {int: int, ...},  # BuildingType -> colonist count
            "island_tile_counts": {int: int, ...},  # TileType -> count
            "island_tile_occupied": {int: int, ...}, # TileType -> occupied count
            "production_capacity": {               # good_name -> producible count
                "corn": int,
                "indigo": int,
                "sugar": int,
                "tobacco": int,
                "coffee": int,
            },
        },
        # ... per player
    ],
}
```

### 구현 코드 (canonical_state.py)

```python
"""
CanonicalStateBuilder - engine state를 모델 서빙/adapter용 표준 상태로 변환.

이 모듈은 frontend rich JSON과 별개의 내부 계약이다.
같은 engine state에서 생성되지만, adapter decode 최적화를 위해 설계됨.
"""
from typing import Any, Dict, List, TYPE_CHECKING

from app.services.engine_gateway.constants import (
    BUILDING_DATA,
    BuildingType,
    Good,
    Phase,
    TileType,
)

if TYPE_CHECKING:
    from app.engine_wrapper.wrapper import EngineWrapper

CANONICAL_STATE_VERSION = "castone.canonical-state.v1"

GOOD_NAMES_BY_ENUM = ["coffee", "tobacco", "corn", "sugar", "indigo"]  # Good enum order
GOOD_ENUM_TO_NAME = {Good.COFFEE: "coffee", Good.TOBACCO: "tobacco",
                     Good.CORN: "corn", Good.SUGAR: "sugar",
                     Good.INDIGO: "indigo"}

# env constants for game_progress calculation
VP_CHIPS_SETUP = {2: 65, 3: 75, 4: 100, 5: 122}
COLONIST_SUPPLY_SETUP = {2: 40, 3: 55, 4: 75, 5: 95}


def _safe_phase_id(phase) -> int:
    """Phase enum -> int. None은 9로 매핑 (env의 one-hot index 9 = None/INIT)."""
    if phase is None:
        return 9
    try:
        return int(phase)
    except (TypeError, ValueError):
        return 9


def _build_player_canonical(player, player_idx: int, game) -> Dict[str, Any]:
    """단일 플레이어의 canonical state를 생성한다."""
    # goods
    goods = {GOOD_ENUM_TO_NAME[g]: v for g, v in player.goods.items()}

    # island tiles
    island_tiles = []
    island_tile_counts: Dict[int, int] = {}
    island_tile_occupied: Dict[int, int] = {}
    for slot_idx, t in enumerate(player.island_board):
        tt = t.tile_type
        island_tiles.append({
            "slot_idx": slot_idx,
            "tile_type": int(tt),
            "is_occupied": bool(t.is_occupied),
        })
        if tt != TileType.EMPTY:
            island_tile_counts[int(tt)] = island_tile_counts.get(int(tt), 0) + 1
            if t.is_occupied:
                island_tile_occupied[int(tt)] = island_tile_occupied.get(int(tt), 0) + 1

    # city buildings
    city_buildings = []
    has_building: Dict[int, bool] = {}
    building_colonists: Dict[int, int] = {}
    for slot_idx, b in enumerate(player.city_board):
        bt = b.building_type
        if bt == BuildingType.OCCUPIED_SPACE:
            continue
        bdata = BUILDING_DATA.get(bt)
        if bdata is None:
            continue
        city_buildings.append({
            "slot_idx": slot_idx,
            "building_type": int(bt),
            "colonists": b.colonists,
            "max_colonists": bdata[2],
        })
        if bt != BuildingType.EMPTY:
            has_building[int(bt)] = True
            building_colonists[int(bt)] = b.colonists

    # production capacity (derived)
    production_capacity = _compute_production_capacity(player)

    return {
        "idx": player_idx,
        "doubloons": player.doubloons,
        "vp_chips": player.vp_chips,
        "goods": goods,
        "unplaced_colonists": player.unplaced_colonists,
        "empty_island_spaces": player.empty_island_spaces,
        "empty_city_spaces": player.empty_city_spaces,
        "island_tiles": island_tiles,
        "city_buildings": city_buildings,
        "has_building": has_building,
        "building_colonists": building_colonists,
        "island_tile_counts": island_tile_counts,
        "island_tile_occupied": island_tile_occupied,
        "production_capacity": production_capacity,
    }


def _compute_production_capacity(player) -> Dict[str, int]:
    """각 재화의 생산 가능 수량을 계산한다."""
    # plantation에서 occupied인 것 카운트
    raw = {"corn": 0, "indigo": 0, "sugar": 0, "tobacco": 0, "coffee": 0}
    tile_to_good = {
        TileType.CORN_PLANTATION: "corn",
        TileType.INDIGO_PLANTATION: "indigo",
        TileType.SUGAR_PLANTATION: "sugar",
        TileType.TOBACCO_PLANTATION: "tobacco",
        TileType.COFFEE_PLANTATION: "coffee",
    }
    for t in player.island_board:
        good = tile_to_good.get(t.tile_type)
        if good and t.is_occupied:
            raw[good] += 1

    # 건물 처리 능력 (colonists 수)
    building_cap = {"indigo": 0, "sugar": 0, "tobacco": 0, "coffee": 0}
    indigo_buildings = {BuildingType.SMALL_INDIGO_PLANT, BuildingType.INDIGO_PLANT}
    sugar_buildings = {BuildingType.SMALL_SUGAR_MILL, BuildingType.SUGAR_MILL}
    for b in player.city_board:
        bt = b.building_type
        if bt in indigo_buildings:
            building_cap["indigo"] += b.colonists
        elif bt in sugar_buildings:
            building_cap["sugar"] += b.colonists
        elif bt == BuildingType.TOBACCO_STORAGE:
            building_cap["tobacco"] += b.colonists
        elif bt == BuildingType.COFFEE_ROASTER:
            building_cap["coffee"] += b.colonists

    return {
        "corn": raw["corn"],  # corn은 건물 불필요
        "indigo": min(raw["indigo"], building_cap["indigo"]),
        "sugar": min(raw["sugar"], building_cap["sugar"]),
        "tobacco": min(raw["tobacco"], building_cap["tobacco"]),
        "coffee": min(raw["coffee"], building_cap["coffee"]),
    }


def build_canonical_state(engine: "EngineWrapper") -> Dict[str, Any]:
    """EngineWrapper에서 canonical serving state를 생성한다."""
    game = engine.env.game

    # cargo ships
    cargo_ships = []
    for ship in game.cargo_ships:
        good_type = getattr(ship, "good_type", None)
        cargo_ships.append({
            "capacity": ship.capacity,
            "good": GOOD_ENUM_TO_NAME.get(good_type) if good_type is not None else None,
            "load": ship.current_load,
            "space": max(0, ship.capacity - ship.current_load),
        })

    # available roles
    available_roles = [int(r) for r in game.available_roles]
    role_doubloons = {int(r): v for r, v in game.role_doubloons.items()}

    # face up plantations
    face_up = [int(t) for t in game.face_up_plantations]

    # game_progress: max(vp_depletion, city_fill, colonist_depletion) - matches env
    initial_vp = VP_CHIPS_SETUP.get(game.num_players, 75)
    vp_prog = max(0.0, (initial_vp - game.vp_chips)) / initial_vp
    max_city = 0
    for p in game.players:
        filled = sum(1 for b in p.city_board
                     if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE))
        max_city = max(max_city, filled)
    city_prog = max_city / 12.0
    initial_col = COLONIST_SUPPLY_SETUP.get(game.num_players, 55)
    col_prog = max(0.0, (initial_col - game.colonists_supply)) / initial_col
    game_progress = min(1.0, max(vp_prog, city_prog, col_prog))

    # goods supply
    goods_supply = {GOOD_ENUM_TO_NAME[g]: v for g, v in game.goods_supply.items()}

    # trading house
    trading_house = [GOOD_ENUM_TO_NAME[g] for g in game.trading_house]

    # players
    players = [
        _build_player_canonical(p, i, game)
        for i, p in enumerate(game.players)
    ]

    return {
        "schema_version": CANONICAL_STATE_VERSION,
        "meta": {
            "phase_id": _safe_phase_id(game.current_phase),
            "current_player_idx": game.current_player_idx,
            "governor_idx": game.governor_idx,
            "round": getattr(engine, "_round_count", 0) + 1,
            "step_count": getattr(engine, "_step_count", 0),
            "num_players": game.num_players,
        },
        "global": {
            "vp_supply": game.vp_chips,
            "colonist_supply": game.colonists_supply,
            "colonist_ship": game.colonists_ship,
            "goods_supply": goods_supply,
            "trading_house": trading_house,
            "trading_house_count": len(game.trading_house),
            "cargo_ships": cargo_ships,
            "available_roles": available_roles,
            "role_doubloons": role_doubloons,
            "face_up_plantations": face_up,
            "quarry_supply": game.quarry_stack,
            "game_progress": game_progress,
        },
        "players": players,
    }
```

---

## 4. Canonical Action Catalog v1

### Schema 정의

```python
# canonical_action.py - build_canonical_action_catalog() 반환 타입

CanonicalActionEntry = {
    "canonical_id": str,       # 의미 기반 고유 식별자
    "engine_action": int,      # 0-199 정수
    "category": str,           # "role", "settler", "builder", "trader", ...
    "detail": dict,            # category별 추가 정보
}

# 예시:
# {"canonical_id": "role:settler", "engine_action": 0, "category": "role",
#  "detail": {"role": "settler"}}
# {"canonical_id": "mayor:island:slot:3", "engine_action": 123, "category": "mayor",
#  "detail": {"target": "island", "slot_idx": 3, "tile_type": 5}}
```

### 구현 코드 (canonical_action.py)

```python
"""
CanonicalActionCatalog - legal actions를 의미 단위로 카탈로그화.

adapter가 semantic decode를 수행할 수 있도록
각 legal action에 canonical_id, category, detail을 부여한다.
"""
from typing import Any, Dict, List, TYPE_CHECKING

from app.services.engine_gateway.constants import (
    BuildingType,
    Good,
    Phase,
    Role,
    TileType,
)

if TYPE_CHECKING:
    pass

CANONICAL_ACTION_VERSION = "castone.canonical-action.v1"

GOOD_NAMES = {0: "coffee", 1: "tobacco", 2: "corn", 3: "sugar", 4: "indigo"}
ROLE_NAMES = {
    0: "settler", 1: "mayor", 2: "builder", 3: "craftsman",
    4: "trader", 5: "captain", 6: "prospector_1", 7: "prospector_2",
}


def _describe_action(action_idx: int, state: Dict[str, Any]) -> Dict[str, Any] | None:
    """단일 action index를 canonical entry로 변환한다. state는 canonical state."""

    # Role selection: 0-7
    if 0 <= action_idx <= 7:
        role = ROLE_NAMES.get(action_idx, f"role_{action_idx}")
        return {
            "canonical_id": f"role:{role}",
            "engine_action": action_idx,
            "category": "role",
            "detail": {"role": role, "role_id": action_idx},
        }

    # Settler by tile type: 8-12 (8 + TileType.value)
    # Action 8=Coffee(0), 9=Tobacco(1), 10=Corn(2), 11=Sugar(3), 12=Indigo(4)
    if 8 <= action_idx <= 12:
        tile_type = action_idx - 8  # TileType enum value
        tile_names = {0: "coffee", 1: "tobacco", 2: "corn", 3: "sugar", 4: "indigo"}
        tile_name = tile_names.get(tile_type, f"tile_{tile_type}")
        return {
            "canonical_id": f"settler:tile_type:{tile_name}",
            "engine_action": action_idx,
            "category": "settler",
            "detail": {"tile_type": tile_type, "tile_name": tile_name},
        }

    # Settler quarry: 13 (8 + QUARRY=5) and 14 (explicit quarry action)
    # Both map to quarry. In practice mask sets 13 only if quarry appears face-up.
    if action_idx in (13, 14):
        return {
            "canonical_id": "settler:quarry",
            "engine_action": action_idx,
            "category": "settler",
            "detail": {"quarry": True},
        }

    # Pass: 15
    if action_idx == 15:
        return {
            "canonical_id": "pass",
            "engine_action": 15,
            "category": "pass",
            "detail": {},
        }

    # Builder: 16-38
    if 16 <= action_idx <= 38:
        bt = action_idx - 16
        return {
            "canonical_id": f"builder:building:{bt}",
            "engine_action": action_idx,
            "category": "builder",
            "detail": {"building_type": bt},
        }

    # Trader: 39-43
    if 39 <= action_idx <= 43:
        good_id = action_idx - 39
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"trader:sell:{good}",
            "engine_action": action_idx,
            "category": "trader",
            "detail": {"good": good, "good_id": good_id},
        }

    # Captain load ship: 44-58
    if 44 <= action_idx <= 58:
        index = action_idx - 44
        ship_idx = index // 5
        good_id = index % 5
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"captain:load:{good}:ship:{ship_idx}",
            "engine_action": action_idx,
            "category": "captain",
            "detail": {"good": good, "good_id": good_id,
                       "ship_idx": ship_idx, "wharf": False},
        }

    # Captain wharf: 59-63
    if 59 <= action_idx <= 63:
        good_id = action_idx - 59
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"captain:wharf:{good}",
            "engine_action": action_idx,
            "category": "captain",
            "detail": {"good": good, "good_id": good_id,
                       "ship_idx": -1, "wharf": True},
        }

    # Store windrose: 64-68
    if 64 <= action_idx <= 68:
        good_id = action_idx - 64
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"store:windrose:{good}",
            "engine_action": action_idx,
            "category": "store",
            "detail": {"good": good, "good_id": good_id, "method": "windrose"},
        }

    # Craftsman privilege: 93-97
    if 93 <= action_idx <= 97:
        good_id = action_idx - 93
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"craftsman:privilege:{good}",
            "engine_action": action_idx,
            "category": "craftsman",
            "detail": {"good": good, "good_id": good_id},
        }

    # Hacienda: 105
    if action_idx == 105:
        return {
            "canonical_id": "settler:hacienda",
            "engine_action": 105,
            "category": "settler",
            "detail": {"hacienda": True},
        }

    # Store warehouse: 106-110
    if 106 <= action_idx <= 110:
        good_id = action_idx - 106
        good = GOOD_NAMES.get(good_id, f"good_{good_id}")
        return {
            "canonical_id": f"store:warehouse:{good}",
            "engine_action": action_idx,
            "category": "store",
            "detail": {"good": good, "good_id": good_id, "method": "warehouse"},
        }

    # Mayor island: 120 + TileType.value (120-125, TileType 0-5)
    # Action 120=Coffee, 121=Tobacco, 122=Corn, 123=Sugar, 124=Indigo, 125=Quarry
    if 120 <= action_idx <= 125:
        tile_type = action_idx - 120  # TileType enum value
        tile_names = {0: "coffee", 1: "tobacco", 2: "corn", 3: "sugar", 4: "indigo", 5: "quarry"}
        tile_name = tile_names.get(tile_type, f"tile_{tile_type}")
        return {
            "canonical_id": f"mayor:island:tile_type:{tile_name}",
            "engine_action": action_idx,
            "category": "mayor",
            "detail": {"target": "island", "tile_type": tile_type,
                       "tile_name": tile_name},
        }

    # Mayor city: 140 + BuildingType.value (140-162, BuildingType 0-22)
    if 140 <= action_idx <= 162:
        building_type = action_idx - 140  # BuildingType enum value
        return {
            "canonical_id": f"mayor:city:building_type:{building_type}",
            "engine_action": action_idx,
            "category": "mayor",
            "detail": {"target": "city", "building_type": building_type},
        }

    # Unknown / reserved
    return {
        "canonical_id": f"unknown:{action_idx}",
        "engine_action": action_idx,
        "category": "unknown",
        "detail": {},
    }


def build_canonical_action_catalog(
    action_mask: List[int],
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """action mask와 canonical state로부터 legal action catalog를 생성한다."""
    legal_actions = []
    for idx, valid in enumerate(action_mask):
        if valid > 0.5:
            entry = _describe_action(idx, state)
            if entry is not None:
                legal_actions.append(entry)

    return {
        "schema_version": CANONICAL_ACTION_VERSION,
        "legal_actions": legal_actions,
        "total_legal": len(legal_actions),
    }
```

---

## 5. PolicyAdapter Interface (PuCo_RL/common/base_adapter.py)

```python
"""
PolicyAdapter ABC - 모든 모델 adapter의 기본 인터페이스.

이 클래스를 상속하여 각 모델 번들의 encode/decode 로직을 구현한다.
backend는 이 인터페이스만 의존하고, concrete adapter는 동적으로 import한다.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List

import numpy as np


class PolicyAdapter(ABC):
    """모델 번들의 obs/action 변환을 담당하는 기본 인터페이스."""

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """adapter 고유 식별자. 예: 'puco.semantic293.type_mayor.v1'"""
        ...

    @property
    @abstractmethod
    def canonical_state_version(self) -> str:
        """지원하는 canonical state 버전. 예: 'castone.canonical-state.v1'"""
        ...

    @property
    @abstractmethod
    def canonical_action_version(self) -> str:
        """지원하는 canonical action 버전. 예: 'castone.canonical-action.v1'"""
        ...

    @property
    @abstractmethod
    def obs_dim(self) -> int:
        """모델이 기대하는 observation 벡터 차원."""
        ...

    @property
    @abstractmethod
    def action_dim(self) -> int:
        """모델의 action space 크기."""
        ...

    def validate_compatibility(
        self, manifest: Dict[str, Any], runtime_versions: Dict[str, Any]
    ) -> None:
        """
        manifest와 runtime canonical version의 호환성을 사전 검증한다.
        호환 불가 시 ValueError를 raise한다.
        """
        rt_state = runtime_versions.get("canonical_state_version", "")
        rt_action = runtime_versions.get("canonical_action_version", "")
        supported_states = manifest.get("compatibility", {}).get(
            "supported_canonical_state_versions", []
        )
        supported_actions = manifest.get("compatibility", {}).get(
            "supported_canonical_action_versions", []
        )
        if supported_states and rt_state not in supported_states:
            raise ValueError(
                f"Adapter {self.adapter_id} does not support "
                f"canonical state version '{rt_state}'. "
                f"Supported: {supported_states}"
            )
        if supported_actions and rt_action not in supported_actions:
            raise ValueError(
                f"Adapter {self.adapter_id} does not support "
                f"canonical action version '{rt_action}'. "
                f"Supported: {supported_actions}"
            )

    @abstractmethod
    def encode_obs(
        self, state: Dict[str, Any], player_idx: int
    ) -> np.ndarray:
        """
        canonical state를 모델 입력 벡터로 변환한다.

        Args:
            state: canonical state dict
            player_idx: 현재 플레이어 인덱스

        Returns:
            1-D float32 numpy array (shape: [obs_dim])
        """
        ...

    @abstractmethod
    def encode_action_mask(
        self, state: Dict[str, Any], legal_actions: List[Dict[str, Any]]
    ) -> np.ndarray:
        """
        canonical legal actions를 모델 action space mask로 변환한다.

        Args:
            state: canonical state dict
            legal_actions: canonical action catalog의 legal_actions 리스트

        Returns:
            1-D float32 numpy array (shape: [action_dim])
        """
        ...

    @abstractmethod
    def decode_action(
        self,
        model_action_idx: int,
        state: Dict[str, Any],
        legal_actions: List[Dict[str, Any]],
    ) -> "DecodeResult":
        """
        모델 output action index를 engine action int로 변환한다.

        Args:
            model_action_idx: 모델이 선택한 action index
            state: canonical state dict
            legal_actions: canonical action catalog의 legal_actions 리스트

        Returns:
            DecodeResult with engine_action and metadata
        """
        ...


class DecodeResult:
    """decode_action의 반환 타입."""

    __slots__ = ("engine_action", "canonical_id", "fallback_used",
                 "fallback_reason", "confidence")

    def __init__(
        self,
        engine_action: int,
        canonical_id: str = "",
        fallback_used: bool = False,
        fallback_reason: str = "",
        confidence: float = 1.0,
    ):
        self.engine_action = engine_action
        self.canonical_id = canonical_id
        self.fallback_used = fallback_used
        self.fallback_reason = fallback_reason
        self.confidence = confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_action": self.engine_action,
            "canonical_id": self.canonical_id,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "confidence": self.confidence,
        }
```

---

## 6. Bundle Manifest v2 Schema

```json
{
  "schema_version": "model-bundle.v2",
  "bundle_id": "ppo-pr-server-semantic293-20260419",
  "family": "ppo",
  "policy_tag": "candidate",
  "architecture": "ppo_residual",
  "checkpoint_file": "checkpoint.pth",
  "checkpoint_sha256": "...",
  "adapter_module": "common.semantic293_adapter:Semantic293TypeMayorAdapter",
  "adapter_version": "1.0.0",
  "canonical_state_version": "castone.canonical-state.v1",
  "canonical_action_version": "castone.canonical-action.v1",
  "obs_dim": 293,
  "action_dim": 200,
  "num_players": 3,
  "network": {
    "hidden_dim": 512,
    "num_res_blocks": 3
  },
  "compatibility": {
    "supported_canonical_state_versions": ["castone.canonical-state.v1"],
    "supported_canonical_action_versions": ["castone.canonical-action.v1"]
  }
}
```

---

## 7. Implementation Tasks (Phase 0 ~ Phase 5)

---

### Phase 0: Design Lock

#### Task 0.1: CanonicalStateBuilder 구현

**파일**: `backend/app/services/canonical_state.py` (신규)
**테스트**: `backend/tests/test_canonical_state.py` (신규)

**TDD RED 시나리오**:

```python
# test_canonical_state.py

def test_canonical_state_has_required_schema_version(three_player_engine):
    """canonical state는 반드시 schema_version 필드를 포함해야 한다."""
    state = build_canonical_state(three_player_engine)
    assert state["schema_version"] == "castone.canonical-state.v1"


def test_canonical_state_meta_fields(three_player_engine):
    """meta에는 phase_id, current_player_idx, governor_idx, round, step_count, num_players가 있어야 한다."""
    state = build_canonical_state(three_player_engine)
    meta = state["meta"]
    assert set(meta.keys()) >= {"phase_id", "current_player_idx", "governor_idx",
                                 "round", "step_count", "num_players"}
    assert isinstance(meta["phase_id"], int)
    assert 0 <= meta["current_player_idx"] < 3


def test_canonical_state_player_count_matches(three_player_engine):
    """players 리스트 길이는 num_players와 일치해야 한다."""
    state = build_canonical_state(three_player_engine)
    assert len(state["players"]) == state["meta"]["num_players"]


def test_canonical_state_goods_supply_has_five_goods(three_player_engine):
    """goods_supply는 corn/indigo/sugar/tobacco/coffee 5종을 포함해야 한다."""
    state = build_canonical_state(three_player_engine)
    goods = state["global"]["goods_supply"]
    assert set(goods.keys()) == {"corn", "indigo", "sugar", "tobacco", "coffee"}


def test_canonical_state_player_has_derived_fields(three_player_engine):
    """각 player에는 has_building, production_capacity 등 derived field가 있어야 한다."""
    state = build_canonical_state(three_player_engine)
    player = state["players"][0]
    assert "has_building" in player
    assert "production_capacity" in player
    assert set(player["production_capacity"].keys()) == {"corn", "indigo", "sugar", "tobacco", "coffee"}


def test_canonical_state_cargo_ships(three_player_engine):
    """cargo_ships의 각 엔트리는 capacity, good, load, space를 가져야 한다."""
    state = build_canonical_state(three_player_engine)
    for ship in state["global"]["cargo_ships"]:
        assert set(ship.keys()) >= {"capacity", "good", "load", "space"}
        assert ship["load"] + ship["space"] == ship["capacity"]
```

**fixture 설계** (conftest.py에 추가):

```python
@pytest.fixture
def three_player_engine():
    """3인 게임의 초기 상태 EngineWrapper를 반환한다."""
    from app.engine_wrapper.wrapper import EngineWrapper
    engine = EngineWrapper(num_players=3)
    engine.reset()
    return engine
```

**GREEN 구현**: Section 3의 코드를 `canonical_state.py`에 작성.

**수용 기준**:
- [x] schema_version 포함
- [x] meta 6필드 존재
- [x] players 길이 == num_players
- [x] 5종 goods_supply
- [x] player derived fields (has_building, production_capacity)
- [x] cargo_ships capacity == load + space
- [x] Docker에서 테스트 통과

---

#### Task 0.2: CanonicalActionCatalog 구현

**파일**: `backend/app/services/canonical_action.py` (신규)
**테스트**: `backend/tests/test_canonical_action.py` (신규)

**TDD RED 시나리오**:

```python
# test_canonical_action.py

def test_catalog_schema_version(three_player_engine):
    """catalog에는 schema_version이 포함되어야 한다."""
    state = build_canonical_state(three_player_engine)
    mask = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    assert catalog["schema_version"] == "castone.canonical-action.v1"


def test_catalog_only_contains_legal_actions(three_player_engine):
    """catalog의 legal_actions 수 == mask에서 1인 action 수."""
    state = build_canonical_state(three_player_engine)
    mask = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    expected_count = sum(1 for v in mask if v > 0.5)
    assert catalog["total_legal"] == expected_count
    assert len(catalog["legal_actions"]) == expected_count


def test_catalog_entries_have_required_fields(three_player_engine):
    """각 entry에는 canonical_id, engine_action, category, detail이 있어야 한다."""
    state = build_canonical_state(three_player_engine)
    mask = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    for entry in catalog["legal_actions"]:
        assert "canonical_id" in entry
        assert "engine_action" in entry
        assert "category" in entry
        assert "detail" in entry


def test_role_selection_catalog_entries(three_player_engine):
    """초기 상태에서 role selection phase이면 category='role'인 entry가 존재해야 한다."""
    state = build_canonical_state(three_player_engine)
    mask = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    role_entries = [e for e in catalog["legal_actions"] if e["category"] == "role"]
    assert len(role_entries) > 0
    for entry in role_entries:
        assert entry["canonical_id"].startswith("role:")
        assert 0 <= entry["engine_action"] <= 7


def test_mayor_catalog_has_tile_type_detail(three_player_engine_at_mayor):
    """Mayor phase에서 island slot entry에는 tile_type detail이 포함되어야 한다."""
    state = build_canonical_state(three_player_engine_at_mayor)
    mask = three_player_engine_at_mayor.get_action_mask()
    catalog = build_canonical_action_catalog(mask, state)
    island_entries = [e for e in catalog["legal_actions"]
                      if e["category"] == "mayor" and e["detail"].get("target") == "island"]
    for entry in island_entries:
        assert "tile_type" in entry["detail"]
```

**구현 메모**:
- `GOOD_NAMES`, `GOOD_ENUM_TO_NAME`처럼 canonical state/action 양쪽에서 반복되는 goods 명칭 매핑은 가능하면 `backend/app/services/canonical_common.py` 같은 공용 상수 모듈로 통합한다.
- 이번 Phase 0에서는 계약을 바꾸지 않는 범위에서만 정리하고, 상수 통합이 구현 범위를 크게 늘리면 후속 cleanup PR로 분리해도 된다.

**수용 기준**:
- [x] schema_version 포함
- [x] legal action count 일치
- [x] entry 구조 4필드 보장
- [x] role selection 올바른 매핑
- [x] mayor island에 tile_type detail 포함
- [x] Docker에서 테스트 통과

---

#### Task 0.3: PolicyAdapter Base Class 구현

**파일**: `PuCo_RL/common/base_adapter.py` (신규)
**테스트**: `backend/tests/test_adapter_runtime.py` (일부)

**구현**: Section 5의 코드를 그대로 사용.

**TDD RED 시나리오**:

```python
# test_adapter_runtime.py (일부)

def test_adapter_abc_cannot_be_instantiated():
    """PolicyAdapter는 직접 인스턴스화할 수 없어야 한다."""
    from common.base_adapter import PolicyAdapter
    with pytest.raises(TypeError):
        PolicyAdapter()


def test_decode_result_to_dict():
    """DecodeResult.to_dict()는 5개 필드를 반환해야 한다."""
    from common.base_adapter import DecodeResult
    result = DecodeResult(engine_action=42, canonical_id="role:settler")
    d = result.to_dict()
    assert d["engine_action"] == 42
    assert d["canonical_id"] == "role:settler"
    assert d["fallback_used"] is False
```

**수용 기준**:
- [x] ABC이므로 직접 인스턴스화 불가
- [x] DecodeResult 직렬화 가능
- [x] validate_compatibility 기본 구현 동작

---

#### Task 0.4: PuCo_RL/common/ 모듈 구조 정리

**파일**:
- `PuCo_RL/common/__init__.py` (신규 or 수정)
- `PuCo_RL/common/adapter.py` (기존 빈 파일 -> re-export)

```python
# PuCo_RL/common/__init__.py
# common 패키지 초기화

# PuCo_RL/common/adapter.py
# 기존 빈 파일 -> 편의 re-export
from .base_adapter import PolicyAdapter, DecodeResult

__all__ = ["PolicyAdapter", "DecodeResult"]
```

**구현 메모**:
- `common/adapter.py`의 re-export는 패키지 내부 이동에 덜 취약하도록 relative import(`from .base_adapter import ...`)를 사용한다.

---

### Phase 1: Backend Runtime Split

#### Task 1.1: AdapterRuntime 구현

**파일**: `backend/app/services/adapter_runtime.py` (신규)
**테스트**: `backend/tests/test_adapter_runtime.py`

**핵심 로직**: manifest의 `adapter_module` 경로로 adapter를 동적 import하고, canonical state/action을 전달하여 추론을 실행한다.

**구현 코드**:

```python
"""
AdapterRuntime - Model bundle의 adapter를 동적 로딩하고 추론을 실행한다.

핵심 흐름:
1. manifest에서 adapter_module 경로를 읽는다
2. importlib로 adapter class를 동적 로딩한다
3. validate_compatibility로 호환성을 검증한다
4. encode_obs -> model forward -> decode_action을 수행한다
"""
import importlib
import logging
from typing import Any, Dict, Optional, Tuple

import torch
import numpy as np

from app.services.canonical_state import build_canonical_state, CANONICAL_STATE_VERSION
from app.services.canonical_action import build_canonical_action_catalog, CANONICAL_ACTION_VERSION

logger = logging.getLogger(__name__)

RUNTIME_VERSIONS = {
    "canonical_state_version": CANONICAL_STATE_VERSION,
    "canonical_action_version": CANONICAL_ACTION_VERSION,
}


def load_adapter_class(adapter_module_path: str):
    """
    'common.semantic293_adapter:Semantic293TypeMayorAdapter'
    형태의 경로에서 adapter class를 동적 로딩한다.
    """
    module_path, class_name = adapter_module_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls


class AdapterRuntime:
    """Bundle의 adapter를 관리하고 추론을 실행한다."""

    def __init__(self, manifest: Dict[str, Any], checkpoint_path: str):
        self._manifest = manifest
        self._checkpoint_path = checkpoint_path

        # adapter 로딩
        adapter_module = manifest["adapter_module"]
        adapter_cls = load_adapter_class(adapter_module)
        self._adapter = adapter_cls()

        # 호환성 검증
        self._adapter.validate_compatibility(manifest, RUNTIME_VERSIONS)

        # 모델 로딩
        self._model = self._load_model(manifest, checkpoint_path)

        logger.info(
            "AdapterRuntime initialized: bundle=%s adapter=%s obs_dim=%d action_dim=%d",
            manifest.get("bundle_id"),
            self._adapter.adapter_id,
            self._adapter.obs_dim,
            self._adapter.action_dim,
        )

    def _load_model(self, manifest: Dict[str, Any], checkpoint_path: str):
        """checkpoint를 로딩하고 모델을 초기화한다."""
        from app.services.engine_gateway.bootstrap import ensure_puco_rl_path
        ensure_puco_rl_path()
        from agents.ppo_agent import Agent

        obs_dim = manifest["obs_dim"]
        action_dim = manifest["action_dim"]
        network = manifest.get("network", {})

        model = Agent(
            obs_dim=obs_dim,
            action_dim=action_dim,
            hidden_dim=network.get("hidden_dim", 512),
            num_res_blocks=network.get("num_res_blocks", 3),
        )
        model.eval()

        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        if not isinstance(checkpoint, dict):
            raise ValueError(
                "Checkpoint must be a dict containing 'model_state_dict' or a raw state_dict."
            )

        state_dict = checkpoint.get("model_state_dict", checkpoint)
        if not isinstance(state_dict, dict) or not state_dict:
            raise ValueError("Checkpoint payload does not contain a valid state_dict.")

        if not any(torch.is_tensor(v) for v in state_dict.values()):
            raise ValueError("Checkpoint state_dict does not contain tensor weights.")

        load_result = model.load_state_dict(state_dict, strict=False)
        if load_result.missing_keys:
            logger.warning(
                "Model load missing keys (%d): %s",
                len(load_result.missing_keys),
                load_result.missing_keys[:10],
            )
        if load_result.unexpected_keys:
            logger.warning(
                "Model load unexpected keys (%d): %s",
                len(load_result.unexpected_keys),
                load_result.unexpected_keys[:10],
            )

        return model

    def infer(self, engine) -> "InferenceResult":
        """
        전체 추론 파이프라인을 실행한다.

        1. canonical state 생성
        2. canonical action catalog 생성
        3. adapter.encode_obs()
        4. adapter.encode_action_mask()
        5. model forward
        6. adapter.decode_action()
        """
        # 1-2. canonical state & action catalog
        canonical_state = build_canonical_state(engine)
        action_mask_raw = engine.get_action_mask()
        catalog = build_canonical_action_catalog(action_mask_raw, canonical_state)

        player_idx = canonical_state["meta"]["current_player_idx"]
        legal_actions = catalog["legal_actions"]

        # 3-4. encode
        obs = self._adapter.encode_obs(canonical_state, player_idx)
        mask = self._adapter.encode_action_mask(canonical_state, legal_actions)

        obs_tensor = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
        mask_tensor = torch.as_tensor(mask, dtype=torch.float32).unsqueeze(0)

        # 5. model forward
        # Serving semantics는 deterministic masked argmax를 사용한다.
        # 학습 시점의 exploration/sampling과 intentionally 다르며,
        # replay parity와 promotion gate도 serving semantics를 기준으로 본다.
        with torch.no_grad():
            features = self._model._shared_features(obs_tensor)
            logits = self._model.actor_head(features)
            masked_logits = torch.where(
                mask_tensor > 0.5, logits,
                torch.tensor(-1e8, dtype=logits.dtype)
            )
            model_action_idx = int(masked_logits.argmax(dim=-1).item())

        # 6. decode
        decode_result = self._adapter.decode_action(
            model_action_idx, canonical_state, legal_actions
        )

        return InferenceResult(
            engine_action=decode_result.engine_action,
            canonical_id=decode_result.canonical_id,
            fallback_used=decode_result.fallback_used,
            fallback_reason=decode_result.fallback_reason,
            bundle_id=self._manifest.get("bundle_id", "unknown"),
            adapter_id=self._adapter.adapter_id,
            canonical_state_version=CANONICAL_STATE_VERSION,
            canonical_action_version=CANONICAL_ACTION_VERSION,
            phase_id=canonical_state["meta"]["phase_id"],
        )


class InferenceResult:
    """추론 결과와 audit/replay용 메타데이터."""

    __slots__ = ("engine_action", "canonical_id", "fallback_used",
                 "fallback_reason", "bundle_id", "adapter_id",
                 "canonical_state_version", "canonical_action_version",
                 "phase_id")

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def to_dict(self) -> Dict[str, Any]:
        return {slot: getattr(self, slot) for slot in self.__slots__}
```

**TDD RED 시나리오**:

```python
def test_load_adapter_class_valid_path():
    """유효한 adapter_module 경로로 class를 로딩할 수 있어야 한다."""
    cls = load_adapter_class("common.base_adapter:PolicyAdapter")
    assert cls is not None
    assert hasattr(cls, "encode_obs")


def test_load_adapter_class_invalid_path():
    """존재하지 않는 경로는 ImportError/AttributeError를 발생시켜야 한다."""
    with pytest.raises((ImportError, AttributeError)):
        load_adapter_class("nonexistent.module:FakeAdapter")


def test_adapter_runtime_validates_compatibility(mock_manifest, tmp_checkpoint):
    """AdapterRuntime 초기화 시 호환성 검증이 수행되어야 한다."""
    # manifest의 supported_canonical_state_versions에 v1이 포함되어 있으면 통과
    runtime = AdapterRuntime(mock_manifest, tmp_checkpoint)
    assert runtime._adapter is not None


def test_adapter_runtime_rejects_non_state_dict_checkpoint(mock_manifest, tmp_path):
    """checkpoint dict가 state_dict가 아니면 ValueError를 발생시켜야 한다."""
    bad_checkpoint = tmp_path / "bad_checkpoint.pt"
    torch.save({"epoch": 3, "metrics": {"loss": 1.23}}, bad_checkpoint)

    with pytest.raises(ValueError, match="state_dict"):
        AdapterRuntime(mock_manifest, str(bad_checkpoint))
```

**구현 메모**:
- serving runtime은 PPO 학습 시점의 `Categorical.sample()` 기반 탐험 정책을 재현하지 않고, 마스킹된 logits에 대해 deterministic `argmax`를 사용한다.
- 운영 환경의 replay parity, fallback rate, promotion gate는 모두 이 serving semantics를 기준으로 측정한다.

**수용 기준**:
- [x] adapter_module 경로로 동적 import 성공
- [x] validate_compatibility 호출
- [x] state_dict가 아닌 checkpoint payload는 초기화 시점에 명시적 `ValueError`
- [x] infer() 파이프라인: canonical state -> encode -> forward -> decode
- [x] serving path는 masked greedy argmax를 사용하며, training sampling과의 차이가 문서화됨
- [x] InferenceResult에 audit용 메타데이터 포함
- [x] Docker에서 테스트 통과

---

#### Task 1.2: model_registry.py에 Bundle Manifest v2 지원 추가

**파일**: `backend/app/services/model_registry.py` (수정)

**변경 내용**:

```python
# 추가할 상수
MODEL_BUNDLE_SCHEMA_V2 = "model-bundle.v2"

# 추가할 함수
def load_bundle_manifest(bundle_dir: str) -> Dict[str, Any] | None:
    """bundle 디렉토리에서 manifest.json을 로딩한다."""
    manifest_path = os.path.join(bundle_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return None
    data = _load_json(manifest_path)
    if data.get("schema_version") != MODEL_BUNDLE_SCHEMA_V2:
        return None
    return data


def resolve_bundle_checkpoint(bundle_dir: str, manifest: Dict[str, Any]) -> str:
    """manifest에서 checkpoint 경로를 resolve한다."""
    checkpoint_file = manifest.get("checkpoint_file", "checkpoint.pth")
    path = os.path.join(bundle_dir, checkpoint_file)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Bundle checkpoint not found: {path}")
    return path


def _parse_bundle_v2(
    manifest: Dict[str, Any],
    *,
    bundle_dir: str,
) -> ModelArtifact:
    """Bundle manifest v2를 ModelArtifact로 변환한다."""
    checkpoint_file = manifest.get("checkpoint_file", "checkpoint.pth")
    checkpoint_path = os.path.join(bundle_dir, checkpoint_file)
    network = manifest.get("network", {})
    return ModelArtifact(
        family=manifest.get("family", "ppo"),
        policy_tag=manifest.get("policy_tag", "candidate"),
        artifact_name=manifest.get("bundle_id", ""),
        checkpoint_filename=checkpoint_file,
        checkpoint_path=checkpoint_path,
        architecture=manifest.get("architecture"),
        obs_dim=manifest.get("obs_dim"),
        action_dim=manifest.get("action_dim"),
        num_players=manifest.get("num_players"),
        hidden_dim=network.get("hidden_dim"),
        num_res_blocks=network.get("num_res_blocks"),
        metadata_source="bundle_v2",
        metadata=dict(manifest),
    )
```

**TDD RED 시나리오**:

```python
def test_load_bundle_manifest_valid(tmp_bundle_dir):
    """유효한 bundle manifest v2를 로딩할 수 있어야 한다."""
    manifest = load_bundle_manifest(tmp_bundle_dir)
    assert manifest is not None
    assert manifest["schema_version"] == "model-bundle.v2"


def test_load_bundle_manifest_v1_returns_none(tmp_bundle_dir_v1):
    """v1 manifest는 None을 반환해야 한다."""
    manifest = load_bundle_manifest(tmp_bundle_dir_v1)
    assert manifest is None


def test_parse_bundle_v2_creates_artifact(sample_v2_manifest, tmp_bundle_dir):
    """v2 manifest에서 ModelArtifact를 생성할 수 있어야 한다."""
    artifact = _parse_bundle_v2(sample_v2_manifest, bundle_dir=tmp_bundle_dir)
    assert artifact.metadata_source == "bundle_v2"
    assert artifact.obs_dim == 293
    assert artifact.action_dim == 200
```

**수용 기준**:
- [x] bundle manifest v2 로딩
- [x] v1 manifest 하위 호환 (None 반환)
- [x] ModelArtifact 생성
- [x] 기존 sidecar/bootstrap 경로 미영향

---

#### Task 1.3: agent_registry.py에 Bundle 기반 라우팅 추가

**파일**: `backend/app/services/agent_registry.py` (수정)

**변경 내용**: `AGENT_REGISTRY`에 bundle 설정을 추가하고, bundle이 있는 bot_type은 AdapterRuntime 경로로 라우팅한다.

```python
# agent_registry.py에 추가

from functools import lru_cache
from app.services.adapter_runtime import AdapterRuntime

# AGENT_REGISTRY의 ppo 항목에 bundle 지원 추가
# "ppo": {
#     ...기존 필드...
#     "bundle_dir": "ppo-pr-server-semantic293-20260419",  # models/ 하위 디렉토리
#     "use_adapter": True,  # adapter runtime 사용 여부 (feature flag)
# },


@lru_cache(maxsize=None)
def _resolve_adapter_runtime(bot_type: str) -> AdapterRuntime | None:
    """bundle 설정이 있는 bot_type에 대해 AdapterRuntime을 반환한다.
    
    lru_cache를 사용하여 기존 get_wrapper()와 동일한 싱글톤 패턴을 따른다.
    thread-safe: CPython의 GIL이 dict lookup을 보호한다.
    """
    cfg = AGENT_REGISTRY.get(bot_type, {})
    if not cfg.get("use_adapter"):
        return None

    bundle_dir_name = cfg.get("bundle_dir")
    if not bundle_dir_name:
        return None

    bundle_dir = os.path.join(_MODELS_DIR, bundle_dir_name)
    manifest = load_bundle_manifest(bundle_dir)
    if manifest is None:
        logger.warning("Bundle manifest not found for %s at %s", bot_type, bundle_dir)
        return None

    checkpoint_path = resolve_bundle_checkpoint(bundle_dir, manifest)
    return AdapterRuntime(manifest, checkpoint_path)


def get_adapter_runtime(bot_type: str) -> AdapterRuntime | None:
    """외부에서 호출 가능한 adapter runtime getter."""
    normalized = require_valid_bot_type(bot_type)
    return _resolve_adapter_runtime(normalized)
```

---

#### Task 1.4: bot_service.py 리팩터링 - Adapter 경로 추가

**파일**: `backend/app/services/bot_service.py` (수정)

**핵심 변경**: `get_action()`에서 adapter runtime이 있으면 adapter 경로로, 없으면 기존 wrapper 경로로 분기한다.

```python
# bot_service.py의 get_action() 수정

@staticmethod
def get_action(bot_type: str, game_context: Dict[str, Any]) -> int:
    """Universal Agent Interface - adapter 경로 우선, fallback으로 기존 wrapper."""

    # 1. adapter runtime 확인
    from app.services.agent_registry import get_adapter_runtime
    adapter_runtime = get_adapter_runtime(bot_type)

    if adapter_runtime is not None:
        # NEW PATH: canonical state -> adapter -> model -> decode
        engine = game_context.get("engine_instance") or game_context.get("engine")
        if engine is None:
            # engine_instance가 없으면 기존 경로로 fallback
            logger.warning("[BOT] adapter path requested but no engine_instance, falling back to wrapper")
        else:
            result = adapter_runtime.infer(engine)
            logger.warning(
                "[BOT_TRACE] adapter_inference bot_type=%s bundle=%s adapter=%s action=%d fallback=%s",
                bot_type, result.bundle_id, result.adapter_id,
                result.engine_action, result.fallback_used,
            )
            return result.engine_action

    # 2. LEGACY PATH: 기존 wrapper 경로 (변경 없음)
    wrapper = BotService.get_agent_wrapper(bot_type)
    raw_obs = game_context["vector_obs"]
    action_mask = game_context["action_mask"]
    phase_id = game_context.get("phase_id", 8)
    current_player_idx = game_context.get("current_player_idx")
    env_context = (
        game_context.get("env")
        or game_context.get("engine_env")
        or game_context.get("engine_instance")
    )

    BotService._ensure_obs_space()
    flat_obs = flatten_dict_observation(raw_obs, BotService._obs_space)
    obs_tensor = torch.as_tensor(flat_obs, dtype=torch.float32)
    mask_tensor = torch.as_tensor(action_mask, dtype=torch.float32)
    if obs_tensor.dim() == 1:
        obs_tensor = obs_tensor.unsqueeze(0)
    if mask_tensor.dim() == 1:
        mask_tensor = mask_tensor.unsqueeze(0)

    action = wrapper.act(
        obs_tensor, mask_tensor,
        phase_id=phase_id, obs_dict=raw_obs,
        player_idx=current_player_idx, env=env_context,
    )
    return action
```

**추가**: `_select_action_for_current_state()`에서 `game_context`에 `engine_instance`를 추가.

```python
# 기존 game_context dict에 engine 자체를 추가
game_context = {
    "vector_obs": snapshot.obs,
    "action_mask": snapshot.action_mask,
    "phase_id": snapshot.phase_id,
    "current_player_idx": snapshot.current_player_idx,
    "env": engine.env,
    "engine_instance": engine,  # NEW: adapter runtime용
}
```

**TDD RED 시나리오**:

```python
def test_bot_service_uses_adapter_when_available(three_player_engine, monkeypatch):
    """use_adapter=True인 bot_type은 adapter 경로를 사용해야 한다."""
    # adapter runtime을 mock으로 주입
    mock_result = InferenceResult(engine_action=3, ...)
    mock_runtime = MagicMock()
    mock_runtime.infer.return_value = mock_result
    monkeypatch.setattr("app.services.agent_registry.get_adapter_runtime",
                        lambda bt: mock_runtime)

    action = BotService.get_action("ppo", {"engine_instance": three_player_engine, ...})
    assert action == 3
    mock_runtime.infer.assert_called_once()


def test_bot_service_falls_back_to_wrapper(three_player_engine, monkeypatch):
    """adapter runtime이 None이면 기존 wrapper 경로를 사용해야 한다."""
    monkeypatch.setattr("app.services.agent_registry.get_adapter_runtime",
                        lambda bt: None)
    # 기존 경로가 정상 동작하는지 확인
    action = BotService.get_action("ppo", {
        "vector_obs": three_player_engine.last_obs,
        "action_mask": three_player_engine.get_action_mask(),
        "phase_id": 8,
        "current_player_idx": 0,
        "env": three_player_engine.env,
    })
    assert isinstance(action, int)
    assert 0 <= action < 200
```

**수용 기준**:
- [x] adapter runtime 있으면 adapter 경로 사용
- [x] adapter runtime 없으면 기존 wrapper 경로 fallback
- [x] engine_instance를 game_context에 전달
- [x] 기존 rule-based bots 미영향
- [x] Docker에서 기존 테스트 전부 통과

---

#### Task 1.5: replay_logger.py에 Bundle/Adapter 메타데이터 추가

**파일**: `backend/app/services/replay_logger.py` (수정)

**변경 내용**: `build_replay_entry()`에 adapter inference 결과 메타데이터를 기록한다.

```python
# build_replay_entry() 시그니처에 추가
def build_replay_entry(
    *,
    # ... 기존 파라미터 ...
    adapter_info: dict[str, Any] | None = None,  # NEW
) -> dict[str, Any]:
    # ... 기존 로직 ...
    if adapter_info is not None:
        entry["adapter_info"] = adapter_info
    # adapter_info 예시:
    # {
    #     "bundle_id": "ppo-pr-server-semantic293-20260419",
    #     "adapter_id": "puco.semantic293.type_mayor.v1",
    #     "canonical_state_version": "castone.canonical-state.v1",
    #     "canonical_action_version": "castone.canonical-action.v1",
    #     "fallback_used": False,
    #     "fallback_reason": "",
    # }
    return entry
```

---

### Phase 2: First Adapter

#### Task 2.1: Semantic293TypeMayorAdapter 구현

**파일**: `PuCo_RL/common/semantic293_adapter.py` (신규)

**역할**: 현재 293-dim obs + type-mayor action space 모델을 canonical state/action으로 변환하는 concrete adapter.

**핵심 구현 과제**:
1. `encode_obs()`: canonical state dict -> 293-dim flattened vector (pr_env.py의 obs 구조와 동일한 순서)
2. `encode_action_mask()`: canonical legal actions -> 200-dim mask
3. `decode_action()`: model action idx -> engine action int

**구현 코드**:

```python
"""
Semantic293TypeMayorAdapter — 현재 293-dim semantic obs + type mayor 모델용 adapter.

이 adapter는 pr_env.py의 feature/obs-encoding-onehot 브랜치 기준
293-dim observation space를 재현한다.

obs 구조 (3인 게임, 293 dims):
  global: 74 dims
    - cargo_ships_good_onehot: 18 (6-class one-hot × 3 ships)
    - cargo_ships_load: 3
    - cargo_ships_space: 3
    - colonists_ship: 1
    - colonists_supply: 1
    - current_phase_onehot: 10
    - current_player: 1
    - face_up_plantation_counts: 6
    - game_progress: 1
    - goods_supply: 5
    - governor_idx: 1
    - quarry_stack: 1
    - role_doubloons: 8
    - roles_available: 8
    - trading_house_count: 1
    - trading_house_has_good: 5
    - vp_chips: 1
  per_player: 73 dims × 3 players = 219 dims
    - building_colonists: 23
    - doubloons: 1
    - empty_city_spaces: 1
    - goods: 5
    - has_building: 23
    - island_empty_spaces: 1
    - island_tile_count: 6
    - island_tile_occupied: 6
    - production_capacity: 5
    - unplaced_colonists: 1
    - vp_chips: 1

  Total: 74 + 219 = 293
"""
import numpy as np
from typing import Any, Dict, List

from common.base_adapter import PolicyAdapter, DecodeResult


# TileType enum values: Coffee=0, Tobacco=1, Corn=2, Sugar=3, Indigo=4, Quarry=5
TILE_TYPES_FOR_COUNT = [0, 1, 2, 3, 4, 5]  # Coffee, Tobacco, Corn, Sugar, Indigo, Quarry
# Good enum values: Coffee=0, Tobacco=1, Corn=2, Sugar=3, Indigo=4
GOOD_ENUM_ORDER = ["coffee", "tobacco", "corn", "sugar", "indigo"]
NUM_BUILDING_TYPES = 23  # BuildingType 0-22
NUM_GOODS = 5
NUM_PHASES = 10  # 0-8 + None mapped to 9
NUM_ROLES = 8
NUM_SHIPS = 3
GOOD_ONEHOT_CLASSES = 6  # 5 goods + 1 empty (index 0-4 = Good enum, 5 = empty)


class Semantic293TypeMayorAdapter(PolicyAdapter):

    @property
    def adapter_id(self) -> str:
        return "puco.semantic293.type_mayor.v1"

    @property
    def canonical_state_version(self) -> str:
        return "castone.canonical-state.v1"

    @property
    def canonical_action_version(self) -> str:
        return "castone.canonical-action.v1"

    @property
    def obs_dim(self) -> int:
        return 293

    @property
    def action_dim(self) -> int:
        return 200

    def encode_obs(self, state: Dict[str, Any], player_idx: int) -> np.ndarray:
        """canonical state를 293-dim vector로 변환한다."""
        g = state["global"]
        meta = state["meta"]
        players = state["players"]
        num_players = meta["num_players"]

        obs = []

        # ── global features (74 dims) ──

        # cargo_ships_good_onehot: 18 (6 × 3)
        for ship in g["cargo_ships"][:NUM_SHIPS]:
            onehot = [0.0] * GOOD_ONEHOT_CLASSES
            good = ship["good"]
            if good is not None:
                good_idx = GOOD_ENUM_ORDER.index(good)
                onehot[good_idx] = 1.0
            else:
                onehot[5] = 1.0  # empty class
            obs.extend(onehot)

        # cargo_ships_load: 3
        for ship in g["cargo_ships"][:NUM_SHIPS]:
            obs.append(float(ship["load"]))

        # cargo_ships_space: 3
        for ship in g["cargo_ships"][:NUM_SHIPS]:
            obs.append(float(ship["space"]))

        # colonists_ship: 1
        obs.append(float(g["colonist_ship"]))

        # colonists_supply: 1
        obs.append(float(g["colonist_supply"]))

        # current_phase_onehot: 10
        phase_onehot = [0.0] * NUM_PHASES
        phase_id = meta["phase_id"]
        if 0 <= phase_id < NUM_PHASES:
            phase_onehot[phase_id] = 1.0
        else:
            phase_onehot[9] = 1.0  # None/INIT
        obs.extend(phase_onehot)

        # current_player: 1
        obs.append(float(meta["current_player_idx"]))

        # face_up_plantation_counts: 6
        face_up_counts = [0] * 6  # coffee, tobacco, corn, sugar, indigo, quarry
        tile_type_to_idx = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
        for tile_type in g["face_up_plantations"]:
            idx = tile_type_to_idx.get(tile_type)
            if idx is not None:
                face_up_counts[idx] += 1
        obs.extend([float(c) for c in face_up_counts])

        # game_progress: 1
        # env는 max(vp_depletion, city_fill, colonist_depletion)으로 계산한다.
        # canonical state의 game_progress 필드를 그대로 사용한다.
        obs.append(float(g["game_progress"]))

        # goods_supply: 5
        for good_name in GOOD_ENUM_ORDER:
            obs.append(float(g["goods_supply"].get(good_name, 0)))

        # governor_idx: 1
        obs.append(float(meta["governor_idx"]))

        # quarry_stack: 1
        obs.append(float(g["quarry_supply"]))

        # role_doubloons: 8
        for role_id in range(NUM_ROLES):
            obs.append(float(g["role_doubloons"].get(role_id, g["role_doubloons"].get(str(role_id), 0))))

        # roles_available: 8
        available_set = set(g["available_roles"])
        for role_id in range(NUM_ROLES):
            obs.append(1.0 if role_id in available_set else 0.0)

        # trading_house_count: 1
        obs.append(float(g["trading_house_count"]))

        # trading_house_has_good: 5
        th_goods = set(g["trading_house"])
        for good_name in GOOD_ENUM_ORDER:
            obs.append(1.0 if good_name in th_goods else 0.0)

        # vp_chips: 1
        obs.append(float(g["vp_supply"]))

        # ── per-player features (73 × num_players) ──
        # player 순서: 고정 (player_0, player_1, player_2)
        # env의 flatten_dict_observation은 key를 알파벳 순 정렬하므로
        # player_0, player_1, player_2 순서가 된다.
        player_order = list(range(num_players))

        for pidx in player_order:
            p = players[pidx]

            # building_colonists: 23
            for bt in range(NUM_BUILDING_TYPES):
                obs.append(float(p["building_colonists"].get(bt, p["building_colonists"].get(str(bt), 0))))

            # doubloons: 1
            obs.append(float(p["doubloons"]))

            # empty_city_spaces: 1
            obs.append(float(p["empty_city_spaces"]))

            # goods: 5
            for good_name in GOOD_ENUM_ORDER:
                obs.append(float(p["goods"].get(good_name, 0)))

            # has_building: 23
            for bt in range(NUM_BUILDING_TYPES):
                obs.append(1.0 if p["has_building"].get(bt, p["has_building"].get(str(bt), False)) else 0.0)

            # island_empty_spaces: 1
            obs.append(float(p["empty_island_spaces"]))

            # island_tile_count: 6
            for tt in TILE_TYPES_FOR_COUNT:
                obs.append(float(p["island_tile_counts"].get(tt, p["island_tile_counts"].get(str(tt), 0))))

            # island_tile_occupied: 6
            for tt in TILE_TYPES_FOR_COUNT:
                obs.append(float(p["island_tile_occupied"].get(tt, p["island_tile_occupied"].get(str(tt), 0))))

            # production_capacity: 5
            for good_name in GOOD_ENUM_ORDER:
                obs.append(float(p["production_capacity"].get(good_name, 0)))

            # unplaced_colonists: 1
            obs.append(float(p["unplaced_colonists"]))

            # vp_chips: 1
            obs.append(float(p["vp_chips"]))

        result = np.array(obs, dtype=np.float32)
        assert result.shape == (293,), f"Expected 293 dims, got {result.shape}"
        return result

    def encode_action_mask(
        self, state: Dict[str, Any], legal_actions: List[Dict[str, Any]]
    ) -> np.ndarray:
        """canonical legal actions를 200-dim mask로 변환한다."""
        mask = np.zeros(200, dtype=np.float32)
        for entry in legal_actions:
            action_idx = entry["engine_action"]
            if 0 <= action_idx < 200:
                mask[action_idx] = 1.0
        return mask

    def decode_action(
        self,
        model_action_idx: int,
        state: Dict[str, Any],
        legal_actions: List[Dict[str, Any]],
    ) -> DecodeResult:
        """model action index를 engine action으로 변환한다."""
        # 현재 모델의 action space가 engine action space와 동일하므로
        # 직접 매핑이 가능하다. 단, legal action 검증을 수행한다.

        legal_engine_actions = {e["engine_action"] for e in legal_actions}

        # exact match
        if model_action_idx in legal_engine_actions:
            canonical_id = ""
            for entry in legal_actions:
                if entry["engine_action"] == model_action_idx:
                    canonical_id = entry["canonical_id"]
                    break
            return DecodeResult(
                engine_action=model_action_idx,
                canonical_id=canonical_id,
            )

        # fallback: same category 내 deterministic 선택
        # model action의 category를 추정
        fallback_action = self._category_fallback(model_action_idx, legal_actions)
        if fallback_action is not None:
            return DecodeResult(
                engine_action=fallback_action["engine_action"],
                canonical_id=fallback_action["canonical_id"],
                fallback_used=True,
                fallback_reason="exact_match_missing",
            )

        # last resort: 첫 번째 legal action
        if legal_actions:
            first = legal_actions[0]
            return DecodeResult(
                engine_action=first["engine_action"],
                canonical_id=first["canonical_id"],
                fallback_used=True,
                fallback_reason="illegal_model_action",
            )

        # no legal actions (should not happen)
        return DecodeResult(
            engine_action=15,  # pass
            canonical_id="pass",
            fallback_used=True,
            fallback_reason="adapter_guard_triggered",
        )

    def _category_fallback(
        self, model_action_idx: int, legal_actions: List[Dict[str, Any]]
    ) -> Dict[str, Any] | None:
        """model action과 같은 category에서 가장 작은 engine_action을 선택한다."""
        # model action의 category 추정
        target_category = self._infer_category(model_action_idx)
        same_category = [
            e for e in legal_actions if e["category"] == target_category
        ]
        if same_category:
            return min(same_category, key=lambda e: e["engine_action"])
        return None

    @staticmethod
    def _infer_category(action_idx: int) -> str:
        """action index에서 category를 추정한다."""
        if 0 <= action_idx <= 7: return "role"
        if 8 <= action_idx <= 14: return "settler"
        if action_idx == 15: return "pass"
        if 16 <= action_idx <= 38: return "builder"
        if 39 <= action_idx <= 43: return "trader"
        if 44 <= action_idx <= 63: return "captain"
        if 64 <= action_idx <= 68: return "store"
        if 93 <= action_idx <= 97: return "craftsman"
        if action_idx == 105: return "settler"
        if 106 <= action_idx <= 110: return "store"
        if 120 <= action_idx <= 125: return "mayor"
        if 140 <= action_idx <= 162: return "mayor"
        return "unknown"
```

**TDD RED 시나리오**:

```python
# test_bundle_integration.py

def test_adapter_encode_obs_produces_293_dims(three_player_engine):
    """encode_obs는 293-dim vector를 반환해야 한다."""
    state = build_canonical_state(three_player_engine)
    adapter = Semantic293TypeMayorAdapter()
    obs = adapter.encode_obs(state, player_idx=0)
    assert obs.shape == (293,)
    assert obs.dtype == np.float32


def test_adapter_encode_action_mask_produces_200_dims(three_player_engine):
    """encode_action_mask는 200-dim mask를 반환해야 한다."""
    state = build_canonical_state(three_player_engine)
    mask_raw = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask_raw, state)
    adapter = Semantic293TypeMayorAdapter()
    mask = adapter.encode_action_mask(state, catalog["legal_actions"])
    assert mask.shape == (200,)
    assert sum(mask) == catalog["total_legal"]


def test_adapter_decode_exact_match(three_player_engine):
    """legal action과 exact match하면 fallback_used=False여야 한다."""
    state = build_canonical_state(three_player_engine)
    mask_raw = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask_raw, state)
    adapter = Semantic293TypeMayorAdapter()

    # 첫 번째 legal action의 engine_action으로 decode
    first_legal = catalog["legal_actions"][0]["engine_action"]
    result = adapter.decode_action(first_legal, state, catalog["legal_actions"])
    assert result.engine_action == first_legal
    assert result.fallback_used is False


def test_adapter_decode_illegal_action_uses_fallback(three_player_engine):
    """illegal action은 fallback을 사용해야 한다."""
    state = build_canonical_state(three_player_engine)
    mask_raw = three_player_engine.get_action_mask()
    catalog = build_canonical_action_catalog(mask_raw, state)
    adapter = Semantic293TypeMayorAdapter()

    # 199는 초기 상태에서 illegal
    result = adapter.decode_action(199, state, catalog["legal_actions"])
    assert result.fallback_used is True
    assert result.fallback_reason in ("exact_match_missing", "illegal_model_action")


def test_adapter_decode_mayor_exact_match(three_player_engine_at_mayor):
    """Mayor phase legal action exact match는 fallback 없이 통과해야 한다."""
    state = build_canonical_state(three_player_engine_at_mayor)
    mask_raw = three_player_engine_at_mayor.get_action_mask()
    catalog = build_canonical_action_catalog(mask_raw, state)
    adapter = Semantic293TypeMayorAdapter()

    mayor_entry = next(
        e for e in catalog["legal_actions"]
        if e["category"] == "mayor" and e["detail"].get("target") == "island"
    )
    result = adapter.decode_action(mayor_entry["engine_action"], state, catalog["legal_actions"])
    assert result.engine_action == mayor_entry["engine_action"]
    assert result.canonical_id == mayor_entry["canonical_id"]
    assert result.fallback_used is False


def test_adapter_decode_mayor_fallback_uses_lowest_slot_index():
    """Mayor fallback은 deterministic하게 가장 낮은 slot index를 선택해야 한다."""
    adapter = Semantic293TypeMayorAdapter()
    legal_actions = [
        {
            "engine_action": 123,
            "canonical_id": "mayor:island:slot:3",
            "category": "mayor",
            "detail": {"target": "island", "slot_idx": 3, "tile_type": 5},
        },
        {
            "engine_action": 121,
            "canonical_id": "mayor:island:slot:1",
            "category": "mayor",
            "detail": {"target": "island", "slot_idx": 1, "tile_type": 2},
        },
    ]

    result = adapter.decode_action(125, {"meta": {"phase_id": 1}}, legal_actions)
    assert result.engine_action == 121
    assert result.canonical_id == "mayor:island:slot:1"
    assert result.fallback_used is True
    assert result.fallback_reason == "exact_match_missing"


def test_adapter_obs_parity_with_env_flatten(three_player_engine):
    """
    adapter의 encode_obs 결과가 pr_env의 flatten 결과와 동일해야 한다.
    이 테스트는 adapter가 학습 시점의 obs를 정확히 재현하는지 검증한다.
    """
    from app.services.engine_gateway.env import flatten_dict_observation, get_flattened_obs_dim

    state = build_canonical_state(three_player_engine)
    adapter = Semantic293TypeMayorAdapter()
    adapter_obs = adapter.encode_obs(state, player_idx=0)

    # env에서 직접 flatten
    raw_obs = three_player_engine.last_obs
    obs_space = three_player_engine.env.observation_space(
        three_player_engine.env.possible_agents[0]
    )["observation"]
    env_obs = flatten_dict_observation(raw_obs, obs_space)

    np.testing.assert_allclose(adapter_obs, env_obs, atol=1e-5,
        err_msg="Adapter obs does not match env flatten - obs parity broken!")
```

**수용 기준**:
- [x] encode_obs -> 293 dims
- [x] encode_action_mask -> 200 dims, legal count 일치
- [x] decode exact match -> fallback_used=False
- [x] decode illegal -> fallback 사용
- [x] Mayor phase exact match -> fallback 없이 동일 action 유지
- [x] Mayor fallback -> deterministic lowest slot index 선택
- [x] **obs parity**: adapter encode_obs == env flatten (핵심 검증)
- [x] Docker에서 테스트 통과

---

#### Task 2.2: First Bundle 패키징

**파일**: `PuCo_RL/common/bundle.py` (신규)

**역할**: 학습 완료 후 bundle directory를 생성하는 유틸리티.

```python
"""
Bundle writer utility - 학습 산출물을 bundle directory로 패키징한다.
"""
import hashlib
import json
import os
import shutil
from typing import Any, Dict


def compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def write_bundle(
    *,
    output_dir: str,
    checkpoint_path: str,
    bundle_id: str,
    family: str = "ppo",
    policy_tag: str = "candidate",
    architecture: str = "ppo_residual",
    adapter_module: str = "common.semantic293_adapter:Semantic293TypeMayorAdapter",
    adapter_version: str = "1.0.0",
    obs_dim: int = 293,
    action_dim: int = 200,
    num_players: int = 3,
    network: Dict[str, Any] | None = None,
    extra_metadata: Dict[str, Any] | None = None,
) -> str:
    """bundle directory를 생성하고 manifest를 작성한다."""
    os.makedirs(output_dir, exist_ok=True)

    # checkpoint 복사
    dest_checkpoint = os.path.join(output_dir, "checkpoint.pth")
    shutil.copy2(checkpoint_path, dest_checkpoint)

    # manifest
    manifest = {
        "schema_version": "model-bundle.v2",
        "bundle_id": bundle_id,
        "family": family,
        "policy_tag": policy_tag,
        "architecture": architecture,
        "checkpoint_file": "checkpoint.pth",
        "checkpoint_sha256": compute_sha256(dest_checkpoint),
        "adapter_module": adapter_module,
        "adapter_version": adapter_version,
        "canonical_state_version": "castone.canonical-state.v1",
        "canonical_action_version": "castone.canonical-action.v1",
        "obs_dim": obs_dim,
        "action_dim": action_dim,
        "num_players": num_players,
        "network": network or {"hidden_dim": 512, "num_res_blocks": 3},
        "compatibility": {
            "supported_canonical_state_versions": ["castone.canonical-state.v1"],
            "supported_canonical_action_versions": ["castone.canonical-action.v1"],
        },
    }
    if extra_metadata:
        manifest.update(extra_metadata)

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return output_dir
```

**첫 번째 번들 등록 절차**:

```bash
# Docker 컨테이너 내에서 실행
python -c "
from common.bundle import write_bundle
write_bundle(
    output_dir='/PuCo_RL/models/ppo-pr-server-semantic293-20260419',
    checkpoint_path='/PuCo_RL/models/PPO_PR_Server_hybrid_selfplay_curriculum_5billion_from_scratch_20260412_122638_step_481689600.pth',
    bundle_id='ppo-pr-server-semantic293-20260419',
)
"
```

---

### Phase 3: Validation

#### Task 3.1: Smoke Inference 테스트

```python
# test_bundle_integration.py

def test_smoke_inference_full_pipeline(three_player_engine):
    """bundle -> adapter runtime -> inference가 유효한 action을 반환해야 한다."""
    # 실제 bundle이 있다고 가정
    manifest = load_bundle_manifest(BUNDLE_DIR)
    if manifest is None:
        pytest.skip("Bundle not available")

    checkpoint_path = resolve_bundle_checkpoint(BUNDLE_DIR, manifest)
    runtime = AdapterRuntime(manifest, checkpoint_path)
    result = runtime.infer(three_player_engine)

    mask = three_player_engine.get_action_mask()
    assert 0 <= result.engine_action < 200
    assert mask[result.engine_action] > 0.5  # legal action
```

#### Task 3.2: Replay Parity 테스트

```python
def test_adapter_inference_matches_legacy_wrapper(three_player_engine):
    """
    adapter 경로와 legacy wrapper 경로가 동일한 action을 반환해야 한다.
    obs parity가 보장되면 같은 모델 + 같은 입력 -> 같은 출력.
    """
    # 1. legacy wrapper 경로
    BotService._ensure_obs_space()
    raw_obs = three_player_engine.last_obs
    flat_obs = flatten_dict_observation(raw_obs, BotService._obs_space)
    obs_tensor = torch.as_tensor(flat_obs, dtype=torch.float32).unsqueeze(0)
    mask = three_player_engine.get_action_mask()
    mask_tensor = torch.as_tensor(mask, dtype=torch.float32).unsqueeze(0)
    wrapper = BotService.get_agent_wrapper("ppo")
    legacy_action = wrapper.act(obs_tensor, mask_tensor)

    # 2. adapter 경로
    runtime = AdapterRuntime(manifest, checkpoint_path)
    result = runtime.infer(three_player_engine)

    assert result.engine_action == legacy_action, \
        f"Parity broken: adapter={result.engine_action}, legacy={legacy_action}"
```

#### Task 3.3: Fallback Rate 측정

```python
def test_fallback_rate_under_threshold(three_player_engine):
    """100스텝 시뮬레이션에서 fallback rate이 5% 이하여야 한다."""
    runtime = AdapterRuntime(manifest, checkpoint_path)
    fallback_count = 0
    total_count = 0

    for _ in range(100):
        if any(three_player_engine.env.terminations.values()):
            break
        result = runtime.infer(three_player_engine)
        total_count += 1
        if result.fallback_used:
            fallback_count += 1
        # adapter가 선택한 legal engine action으로 step을 진행한다.
        step_result = three_player_engine.step(result.engine_action)
        assert isinstance(step_result, dict)
        assert "done" in step_result

    if total_count > 0:
        rate = fallback_count / total_count
        assert rate <= 0.05, f"Fallback rate {rate:.1%} exceeds 5% threshold"
```

**구현 메모**:
- 이 테스트는 `EngineWrapper.step(action: int) -> Dict[str, Any]` 시그니처를 전제로 한다.
- step 결과를 명시적으로 받아 두면 추후 wrapper 반환 계약이 바뀌었을 때 fallback rate 테스트가 조용히 잘못 통과하는 일을 막을 수 있다.

---

### Phase 4: Promotion

#### Task 4.1: agent_registry.py에서 Feature Flag 활성화

```python
# AGENT_REGISTRY의 ppo 항목 수정
"ppo": {
    "name": "PPO Bot",
    "family": "ppo",
    "policy_tag": "champion",
    "wrapper_cls": PPOWrapper,
    "model_env_key": "PPO_MODEL_FILENAME",
    "model_default": "PPO_PR_Server_...pth",
    "bundle_dir": "ppo-pr-server-semantic293-20260419",
    "use_adapter": True,  # <- champion 전환
},
```

#### Task 4.2: Rollback 테스트

```python
def test_rollback_to_legacy_wrapper(monkeypatch):
    """use_adapter=False로 전환하면 기존 wrapper 경로로 즉시 롤백되어야 한다."""
    monkeypatch.setitem(AGENT_REGISTRY["ppo"], "use_adapter", False)
    runtime = get_adapter_runtime("ppo")
    assert runtime is None  # adapter 비활성화
```

---

### Phase 5: Legacy Cleanup

#### Task 5.1: _adapt_obs_dim 제거

**파일**: `backend/app/services/agents/wrappers.py`

**삭제 대상**:
- `_adapt_obs_dim()` 함수 (lines 75-90)
- PPOWrapper.act()의 `obs = _adapt_obs_dim(obs, self._expected_obs_dim)` 호출
- HPPOWrapper.act()의 `obs = _adapt_obs_dim(obs, self._expected_obs_dim)` 호출

**테스트**: 기존 `test_serving_ppo_wrapper.py`에서 210/211 patch 관련 테스트 제거 또는 수정.

#### Task 5.2: bot_service.py env flatten 의존 제거

**삭제 대상**:
- `_build_obs_space()` 함수
- `BotService._obs_space`, `BotService._obs_dim` class variable
- `BotService._ensure_obs_space()` 메서드
- `get_action()`의 legacy flatten 경로 (adapter 경로만 남김)

**조건**: adapter 경로가 모든 model-file bot에 대해 동작함이 검증된 후에만 진행.

#### Task 5.3: model_registry.py bootstrap 의존 제거

**삭제 대상**:
- `get_ppo_pr_server_bootstrap_profile()` (PuertoRicoEnv 인스턴스화)
- `derive_bootstrap_artifact()` (checkpoint weight에서 obs_dim 추론)

**조건**: 모든 모델이 bundle manifest v2를 가진 후에만 진행.

---

## 8. Docker 테스트 워크플로

### 테스트 실행 명령

```bash
# 전체 테스트
docker compose exec backend pytest tests/ -v

# canonical state 테스트만
docker compose exec backend pytest tests/test_canonical_state.py -v

# canonical action 테스트만
docker compose exec backend pytest tests/test_canonical_action.py -v

# adapter runtime 테스트만
docker compose exec backend pytest tests/test_adapter_runtime.py -v

# bundle 통합 테스트만
docker compose exec backend pytest tests/test_bundle_integration.py -v

# 기존 테스트 회귀 확인
docker compose exec backend pytest tests/ -v --tb=short
```

### Docker 컨테이너 환경 확인

```bash
# backend 컨테이너가 PuCo_RL을 볼 수 있는지 확인
docker compose exec backend python -c "import sys; print('/PuCo_RL' in sys.path)"

# PYTHONPATH 확인
docker compose exec backend python -c "import sys; print(sys.path)"
```

---

## 9. Task Dependencies

```text
Phase 0:
  Task 0.1 (CanonicalState) ─┐
  Task 0.2 (CanonicalAction) ─┤
  Task 0.3 (PolicyAdapter)  ──┤
  Task 0.4 (common/ 구조)   ──┘
                               │
Phase 1:                       ▼
  Task 1.1 (AdapterRuntime) ──── depends on 0.1, 0.2, 0.3
  Task 1.2 (model_registry) ──── depends on 0.1
  Task 1.3 (agent_registry) ──── depends on 1.1, 1.2
  Task 1.4 (bot_service)    ──── depends on 1.1, 1.3
  Task 1.5 (replay_logger)  ──── depends on 1.1
                               │
Phase 2:                       ▼
  Task 2.1 (Semantic293Adapter) ── depends on 0.3
  Task 2.2 (First Bundle)       ── depends on 2.1
                               │
Phase 3:                       ▼
  Task 3.1 (Smoke Inference) ── depends on 1.4, 2.2
  Task 3.2 (Replay Parity)  ── depends on 3.1
  Task 3.3 (Fallback Rate)  ── depends on 3.1
                               │
Phase 4:                       ▼
  Task 4.1 (Champion Flag)  ── depends on 3.1, 3.2, 3.3
  Task 4.2 (Rollback Test)  ── depends on 4.1
                               │
Phase 5:                       ▼
  Task 5.1 (_adapt_obs_dim) ── depends on 4.1
  Task 5.2 (env flatten)    ── depends on 5.1
  Task 5.3 (bootstrap)      ── depends on 5.2
```

---

## 10. Risk Checklist

| Risk | Mitigation | Phase |
|------|-----------|-------|
| canonical state 필드 누락으로 adapter encode 실패 | obs parity 테스트로 검증 | 2 |
| adapter import 실패 (PYTHONPATH) | docker-compose에서 `/PuCo_RL`이 이미 mount됨 확인 | 1 |
| legacy wrapper 경로 회귀 | feature flag로 old/new 공존, 기존 테스트 전부 통과 유지 | 1 |
| Mayor slot/type 매핑 ambiguity | deterministic tie-break (lowest slot index) | 2 |
| fallback rate 급증 | Phase 3에서 5% threshold 검증 후 promotion | 3 |
| obs flatten 순서 불일치 | Task 2.1의 obs parity 테스트가 핵심 안전장치 | 2 |
