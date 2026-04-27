# Observation Adapter Layer Design

작성일: 2026-04-17 (rev.2 — diff 분석 반영)
범위: `PuCo_RL/adapters/` (신규) + `backend/app/services/agents/wrappers.py` + 학습 파이프라인
목적: observation vector 변경에도 기존 학습 모델이 깨지지 않도록 버전별 어댑터 계층을 설계한다.

---

## 1. Problem Statement

### 1.1 현재 일어난 일 (diff 분석)

PuCo_RL이 최신 브랜치로 교체되면서 **두 가지 파괴적 변경**이 동시에 발생했다.

**변경 1: Observation 인코딩 전면 교체**

| 항목 | Old (committed) | New (working tree) |
| --- | --- | --- |
| Global: cargo ships | `cargo_ships_good`: MultiDiscrete([6,6,6]) = 3dim | `cargo_ships_good_onehot`: Box(18) = 18dim |
| Global: trading house | `trading_house`: MultiDiscrete([6,6,6,6]) = 4dim | `trading_house_has_good`: Box(5) + `trading_house_count`: Box(1) = 6dim |
| Global: face_up | `face_up_plantations`: MultiDiscrete([7]*4) = 4dim | `face_up_plantation_counts`: Box(6) = 6dim |
| Global: phase | `current_phase`: Discrete(10) = 1dim | `current_phase_onehot`: Box(10) = 10dim |
| Global: 신규 필드 | 없음 | `cargo_ships_space`(3), `game_progress`(1) |
| Player: island | `island_tiles`: MultiDiscrete([7]*12) + `island_occupied`: MultiBinary(12) = 24dim | `island_tile_count`(6) + `island_tile_occupied`(6) + `island_empty_spaces`(1) = 13dim |
| Player: city | `city_buildings`: MultiDiscrete([25]*12) + `city_colonists`: MultiDiscrete([4]*12) = 24dim | `has_building`(23) + `building_colonists`(23) + `empty_city_spaces`(1) = 47dim |
| Player: 신규 필드 | 없음 | `production_capacity`(5) |
| **Total obs_dim (3P)** | **210** | **293** |

인코딩 패러다임 자체가 바뀌었다: ordinal scalars → semantic one-hot/binary/count.

**변경 2: Action Semantics 변경**

| Phase | Old | New |
| --- | --- | --- |
| Settler | 8-13: face_up **슬롯 인덱스** (0-5번째 타일) | 8-12: **TileType** (Coffee=0..Indigo=4), 13: Quarry |
| Mayor Island | 120-131: **슬롯 인덱스** (island_board[0..11]) | 120-125: **TileType** (어떤 타입에 배치할지) |
| Mayor City | 140-151: **슬롯 인덱스** (city_board[0..11]) | 140-162: **BuildingType** (어떤 건물에 배치할지) |
| Quarry | action 14 | action 13 (TileType.QUARRY=5이지만 별도 핸들링) |
| Hacienda | 98-104: deprecated settler+hacienda combo | 제거됨 (auto-use) |

### 1.2 핵심 결론

> **Old ordinal 모델(obs_dim=210)은 adapter만으로 살릴 수 없다.**
> Observation을 변환해주더라도, 모델이 출력하는 action의 의미가 달라졌기 때문이다.
> (예: 모델이 "island slot 3에 배치"로 학습한 action 123 → 새 엔진은 "Sugar type에 배치"로 해석)

따라서 adapter의 역할은:

1. **Old ordinal 모델 호환이 아니라**, 현재 semantic encoding(obs_dim=293)을 기준선으로
2. **미래 obs 변경** (필드 추가/제거/변경)에 대비하여 기존 semantic 모델을 보호하는 것

### 1.3 해결해야 할 문제

1. **Forward Compatibility**: semantic encoding에 필드가 추가되어도 기존 모델이 동작해야 한다.
2. **Multi-Version Serving**: 서로 다른 semantic obs_dim으로 학습된 모델들이 동시에 서빙될 수 있어야 한다.
3. **Training-Serving Parity**: 학습과 서빙에서 동일한 전처리 코드를 사용해야 한다.
4. **Backend 계약 안정성**: 웹 backend가 보내는 데이터 형태는 변하지 않아야 한다.

---

## 2. Current Architecture & What Changed

### 2.1 데이터 흐름 (Before — committed 코드)

```text
pr_env._get_obs()  →  Dict (ordinal scalars, int64)
        ↓
flatten_dict_observation()  →  np.ndarray (210dim, sorted-key)
        ↓
Agent(obs_dim=210).forward(flat_obs)
```

### 2.2 데이터 흐름 (After — working tree)

```text
pr_env._get_obs()  →  Dict (semantic: one-hot, binary, count, float32)
        ↓
flatten_dict_observation()  →  np.ndarray (293dim, sorted-key)
        ↓
Agent(obs_dim=293).forward(flat_obs)
```

### 2.3 변경된 파일 요약 (git diff --stat)

```text
PuCo_RL/env/pr_env.py                      | 399 +++++++++-----   # obs/action 전면 교체
PuCo_RL/agents/shipping_rush_agent.py       | 318 ++++++------   # new obs key 적응
PuCo_RL/agents/action_value_agent.py        |  32 +-            # new obs key 적응
PuCo_RL/agents/factory_rule_based_agent.py  |  86 ++--          # new obs key 적응
PuCo_RL/train/train_ppo_hybrid_server.py    |  58 ++-           # TradeBuildingAgent 추가, 하이퍼파라미터
PuCo_RL/evaluate/*                          | various           # 평가 파이프라인 업데이트
```

### 2.4 기존 모델 현황

| 모델 | obs_dim | 인코딩 | action semantics | 서빙 가능? |
| --- | --- | --- | --- | --- |
| PPO_...5billion...481689600.pth | 293 | semantic | new (type-based) | **Yes** (현재 엔진 호환) |
| backend _adapt_obs_dim의 210/211 모델 | 210/211 | ordinal | old (slot-based) | **No** (action 불호환) |

### 2.5 `_adapt_obs_dim()` 핵의 운명

```python
# backend/app/services/agents/wrappers.py — 기존 코드
def _adapt_obs_dim(obs, expected_dim):
    if current_dim == 211 and expected_dim == 210:
        return torch.cat([obs[..., :42], obs[..., 43:]], dim=-1)
```

이 핵은 old ordinal encoding 내부의 210↔211 차이를 패치한 것이다. ordinal 모델 자체가 폐기되므로, adapter 도입 시 **이 코드는 삭제한다**.

---

## 3. Proposed Architecture: Versioned Observation Adapters

### 3.1 핵심 아이디어

각 adapter 버전이 **game engine 객체에서 직접 flat vector를 구축**한다.

`obs_dict`의 키 구조가 바뀌어도 game engine(PuertoRicoGame)의 내부 상태는 안정적이므로, adapter가 engine을 직접 읽으면 중간 표현(`obs_dict`)에 의존하지 않아 더 견고하다.

```text
PuertoRicoGame (engine — stable source of truth)
        ↓
ObsAdapter[version].build_flat(game, num_players)  →  np.ndarray (고정 dim)
        ↓
Model[version].forward(flat_obs)
```

단, **현재 버전 adapter**는 `pr_env._get_obs()` + flatten과 동일한 결과를 보장해야 한다 (training-serving parity). 따라서 현재 버전은 `obs_dict` 경유 방식도 지원한다.

### 3.2 Adapter 입력 전략

```python
class ObsAdapter(ABC):
    def from_obs_dict(self, obs_dict: dict, num_players: int) -> np.ndarray:
        """obs_dict(pr_env._get_obs() 반환값)에서 flat vector 생성.
        현재 버전 adapter에서 사용. 학습/서빙 모두 활용."""
        ...

    def from_game(self, game: PuertoRicoGame, num_players: int) -> np.ndarray:
        """game engine에서 직접 flat vector 생성.
        과거 버전 adapter에서 사용. obs_dict 키 변경에 면역."""
        ...
```

| 사용 시점 | 메서드 | 이유 |
| --- | --- | --- |
| 학습 (현재 버전) | `from_obs_dict()` | `_get_obs()`와 동일 결과 보장 |
| 서빙 (현재 버전) | `from_obs_dict()` | training-serving parity |
| 서빙 (과거 버전) | `from_game()` | obs_dict 키가 달라도 engine에서 직접 구축 |

### 3.3 접근법 비교

| 접근법 | 장점 | 단점 | 판정 |
| --- | --- | --- | --- |
| **A. Versioned Adapter (game 직접 읽기)** | obs_dict 변경에 면역, 명시적 | 버전마다 빌드 로직 복사 필요 | **채택** |
| B. obs_dict 키 매핑 | 코드 중복 적음 | 키 이름/타입 변경 시 매핑 깨짐 | 기각 |
| C. Trainable Projection | 유지보수 불필요 | 재학습 필요, 성능 저하 위험 | 기각 |

---

## 4. Detailed Design

### 4.1 디렉토리 구조

```text
PuCo_RL/
├── adapters/
│   ├── __init__.py              # Public API + auto-import
│   ├── base.py                  # ObsAdapter ABC
│   ├── registry.py              # Version registry + CURRENT_VERSION
│   ├── checkpoint_utils.py      # Checkpoint → version 추론
│   └── v1_semantic_293.py       # 첫 번째 semantic encoding (현재)
├── env/
│   ├── engine.py                # 변경 없음
│   └── pr_env.py                # 변경 없음
├── utils/
│   └── env_wrappers.py          # 유지 (generic fallback, 테스트용)
├── agents/
│   └── ppo_agent.py             # 변경 없음
├── train/
│   └── train_ppo_hybrid_server.py  # adapter 사용으로 변경
└── models/
    └── *.pth                    # 체크포인트 (버전 메타데이터 포함)
```

### 4.2 ObsAdapter ABC (`adapters/base.py`)

```python
from abc import ABC, abstractmethod
import numpy as np
from typing import Any


class ObsAdapter(ABC):
    """
    Observation adapter base class.
    
    각 버전은 game engine 또는 obs_dict에서 고정 차원의 flat vector를 생성한다.
    - 현재 버전: from_obs_dict() (training-serving parity)
    - 과거 버전: from_game() (obs_dict 키 변경에 면역)
    """

    @property
    @abstractmethod
    def version(self) -> str:
        """버전 식별자 (예: "v1_semantic_293")"""
        ...

    @property
    @abstractmethod
    def obs_dim(self) -> int:
        """이 버전의 flat observation 차원 (3인 기준)"""
        ...

    @property
    @abstractmethod
    def global_dim(self) -> int:
        """Global state 부분의 차원"""
        ...

    @property
    @abstractmethod
    def per_player_dim(self) -> int:
        """플레이어 1명당 차원"""
        ...

    def obs_dim_for_players(self, num_players: int) -> int:
        """플레이어 수에 따른 total obs_dim"""
        return self.global_dim + self.per_player_dim * num_players

    @abstractmethod
    def from_obs_dict(self, obs_dict: dict, num_players: int = 3) -> np.ndarray:
        """
        pr_env._get_obs() 반환값 → 1D float32 array.
        현재 버전 adapter 전용. 과거 버전은 NotImplementedError 가능.
        """
        ...

    @abstractmethod
    def from_game(self, game: Any, num_players: int = 3) -> np.ndarray:
        """
        PuertoRicoGame 객체 → 1D float32 array.
        과거/현재 모든 버전에서 구현. obs_dict 키 변경에 면역.
        """
        ...
```

### 4.3 Version Registry (`adapters/registry.py`)

```python
from typing import Dict, Type
from adapters.base import ObsAdapter

_REGISTRY: Dict[str, Type[ObsAdapter]] = {}

# 현재 canonical 버전 (pr_env.py와 동기화)
CURRENT_VERSION: str = "v1_semantic_293"


def register(version: str):
    """데코레이터: 어댑터 클래스를 레지스트리에 등록"""
    def decorator(cls: Type[ObsAdapter]):
        _REGISTRY[version] = cls
        return cls
    return decorator


def get_adapter(version: str) -> ObsAdapter:
    """버전 문자열로 어댑터 인스턴스 반환"""
    if version not in _REGISTRY:
        raise ValueError(
            f"Unknown obs adapter version: '{version}'. "
            f"Available: {sorted(_REGISTRY.keys())}"
        )
    return _REGISTRY[version]()


def get_current_adapter() -> ObsAdapter:
    """현재 canonical 버전의 어댑터 반환"""
    return get_adapter(CURRENT_VERSION)


def list_versions() -> list[str]:
    """등록된 모든 버전 목록"""
    return sorted(_REGISTRY.keys())
```

### 4.4 V1 Semantic Adapter (`adapters/v1_semantic_293.py`)

현재 `pr_env._get_obs()` + `flatten_dict_observation()`과 동일 결과를 보장한다.

```python
import numpy as np
from typing import Any
from adapters.base import ObsAdapter
from adapters.registry import register


@register("v1_semantic_293")
class ObsAdapterV1Semantic(ObsAdapter):
    """
    첫 번째 semantic encoding adapter.
    
    pr_env.py 2026-04-12 기준.
    Global: 74dim (one-hot cargo, one-hot phase, count plantations, etc.)
    Per-player: 73dim (binary has_building, count tile types, production_capacity, etc.)
    Total (3P): 74 + 73×3 = 293
    
    Flat vector layout (sorted key order):
    ┌─ Global (74) ────────────────────────────────────────────┐
    │ cargo_ships_good_onehot(18) cargo_ships_load(3)          │
    │ cargo_ships_space(3)        colonists_ship(1)            │
    │ colonists_supply(1)         current_phase_onehot(10)     │
    │ current_player(1)           face_up_plantation_counts(6) │
    │ game_progress(1)            goods_supply(5)              │
    │ governor_idx(1)             quarry_stack(1)              │
    │ role_doubloons(8)           roles_available(8)           │
    │ trading_house_count(1)      trading_house_has_good(5)    │
    │ vp_chips(1)                                              │
    └──────────────────────────────────────────────────────────┘
    ┌─ Per-Player ×N (73 each) ────────────────────────────────┐
    │ building_colonists(23) doubloons(1) empty_city_spaces(1) │
    │ goods(5) has_building(23) island_empty_spaces(1)         │
    │ island_tile_count(6) island_tile_occupied(6)             │
    │ production_capacity(5) unplaced_colonists(1) vp_chips(1) │
    └──────────────────────────────────────────────────────────┘
    """

    @property
    def version(self) -> str:
        return "v1_semantic_293"

    @property
    def obs_dim(self) -> int:
        return 293

    @property
    def global_dim(self) -> int:
        return 74

    @property
    def per_player_dim(self) -> int:
        return 73

    # ── from_obs_dict: pr_env._get_obs() 결과를 flat vector로 ──

    def from_obs_dict(self, obs_dict: dict, num_players: int = 3) -> np.ndarray:
        gs = obs_dict["global_state"]
        parts = []

        # Global state (sorted key order)
        parts.append(np.asarray(gs["cargo_ships_good_onehot"], dtype=np.float32))  # 18
        parts.append(np.asarray(gs["cargo_ships_load"], dtype=np.float32))          # 3
        parts.append(np.asarray(gs["cargo_ships_space"], dtype=np.float32))         # 3
        parts.append(np.asarray(gs["colonists_ship"], dtype=np.float32))            # 1
        parts.append(np.asarray(gs["colonists_supply"], dtype=np.float32))          # 1
        parts.append(np.asarray(gs["current_phase_onehot"], dtype=np.float32))      # 10
        parts.append(np.asarray(gs["current_player"], dtype=np.float32))            # 1
        parts.append(np.asarray(gs["face_up_plantation_counts"], dtype=np.float32)) # 6
        parts.append(np.asarray(gs["game_progress"], dtype=np.float32))             # 1
        parts.append(np.asarray(gs["goods_supply"], dtype=np.float32))              # 5
        parts.append(np.asarray(gs["governor_idx"], dtype=np.float32))              # 1
        parts.append(np.asarray(gs["quarry_stack"], dtype=np.float32))              # 1
        parts.append(np.asarray(gs["role_doubloons"], dtype=np.float32))            # 8
        parts.append(np.asarray(gs["roles_available"], dtype=np.float32))           # 8
        parts.append(np.asarray(gs["trading_house_count"], dtype=np.float32))       # 1
        parts.append(np.asarray(gs["trading_house_has_good"], dtype=np.float32))    # 5
        parts.append(np.asarray(gs["vp_chips"], dtype=np.float32))                  # 1

        # Per-player state (sorted key order)
        for i in range(num_players):
            p = obs_dict["players"][f"player_{i}"]
            parts.append(np.asarray(p["building_colonists"], dtype=np.float32))     # 23
            parts.append(np.asarray(p["doubloons"], dtype=np.float32))              # 1
            parts.append(np.asarray(p["empty_city_spaces"], dtype=np.float32))      # 1
            parts.append(np.asarray(p["goods"], dtype=np.float32))                  # 5
            parts.append(np.asarray(p["has_building"], dtype=np.float32))           # 23
            parts.append(np.asarray(p["island_empty_spaces"], dtype=np.float32))    # 1
            parts.append(np.asarray(p["island_tile_count"], dtype=np.float32))      # 6
            parts.append(np.asarray(p["island_tile_occupied"], dtype=np.float32))   # 6
            parts.append(np.asarray(p["production_capacity"], dtype=np.float32))    # 5
            parts.append(np.asarray(p["unplaced_colonists"], dtype=np.float32))     # 1
            parts.append(np.asarray(p["vp_chips"], dtype=np.float32))               # 1

        return np.concatenate([p.flatten() for p in parts])

    # ── from_game: engine 직접 읽기 (obs_dict 키 변경에 면역) ──

    def from_game(self, game: Any, num_players: int = 3) -> np.ndarray:
        """PuertoRicoGame → flat vector. pr_env._get_obs()와 동일 로직."""
        from configs.constants import (
            Good, TileType, BuildingType, Role,
            VP_CHIPS_SETUP, COLONIST_SUPPLY_SETUP, BUILDING_DATA,
        )

        parts = []

        # ── Global State ──
        cargo_onehot = np.zeros(18, dtype=np.float32)
        cargo_load = np.zeros(3, dtype=np.float32)
        cargo_space = np.zeros(3, dtype=np.float32)
        for i, ship in enumerate(game.cargo_ships[:3]):
            if ship.good_type is not None:
                cargo_onehot[i * 6 + ship.good_type.value] = 1.0
            else:
                cargo_onehot[i * 6 + 5] = 1.0
            cargo_load[i] = float(ship.current_load)
            cargo_space[i] = float(ship.capacity - ship.current_load)

        th_has = np.zeros(5, dtype=np.float32)
        for g in game.trading_house:
            th_has[g.value] = 1.0
        th_count = np.array([len(game.trading_house)], dtype=np.float32)

        rd = np.zeros(8, dtype=np.float32)
        ra = np.zeros(8, dtype=np.int8)
        for ri in range(8):
            try:
                role = Role(ri)
                rd[ri] = float(game.role_doubloons.get(role, 0))
                ra[ri] = 1 if role in game.available_roles else 0
            except ValueError:
                pass

        fup = np.zeros(6, dtype=np.float32)
        for t in game.face_up_plantations:
            if t != TileType.EMPTY:
                fup[t.value] += 1.0

        phase_oh = np.zeros(10, dtype=np.float32)
        pidx = int(game.current_phase) if game.current_phase is not None else 9
        phase_oh[pidx] = 1.0

        # game_progress
        initial_vp = VP_CHIPS_SETUP.get(num_players, 75)
        vp_prog = max(0.0, (initial_vp - game.vp_chips)) / initial_vp
        max_city = 0
        for p in game.players:
            filled = sum(1 for b in p.city_board
                         if b.building_type not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE))
            max_city = max(max_city, filled)
        city_prog = max_city / 12.0
        initial_col = COLONIST_SUPPLY_SETUP.get(num_players, 55)
        col_prog = max(0.0, (initial_col - game.colonists_supply)) / initial_col
        gp = min(1.0, max(vp_prog, city_prog, col_prog))

        parts.extend([
            cargo_onehot, cargo_load, cargo_space,
            np.array([game.colonists_ship], dtype=np.float32),
            np.array([game.colonists_supply], dtype=np.float32),
            phase_oh,
            np.array([game.current_player_idx], dtype=np.float32),
            fup,
            np.array([gp], dtype=np.float32),
            np.array([game.goods_supply[Good(i)] for i in range(5)], dtype=np.float32),
            np.array([game.governor_idx], dtype=np.float32),
            np.array([game.quarry_stack], dtype=np.float32),
            rd, ra.astype(np.float32),
            th_count, th_has,
            np.array([game.vp_chips], dtype=np.float32),
        ])

        # ── Per-Player ──
        for i in range(num_players):
            p = game.players[i]

            itc = np.zeros(6, dtype=np.float32)
            ito = np.zeros(6, dtype=np.float32)
            for t in p.island_board:
                if t.tile_type != TileType.EMPTY:
                    itc[t.tile_type.value] += 1.0
                    if t.is_occupied:
                        ito[t.tile_type.value] += 1.0

            hb = np.zeros(23, dtype=np.float32)
            bc = np.zeros(23, dtype=np.float32)
            for b in p.city_board:
                bt = b.building_type
                if bt not in (BuildingType.EMPTY, BuildingType.OCCUPIED_SPACE):
                    hb[bt.value] = 1.0
                    bc[bt.value] = float(b.colonists)

            # production_capacity
            pcap = np.zeros(5, dtype=np.float32)
            plan_cnt = {g: 0 for g in Good}
            for t in p.island_board:
                if t.is_occupied:
                    tt = t.tile_type
                    if tt == TileType.COFFEE_PLANTATION:  plan_cnt[Good.COFFEE] += 1
                    elif tt == TileType.TOBACCO_PLANTATION: plan_cnt[Good.TOBACCO] += 1
                    elif tt == TileType.CORN_PLANTATION:    plan_cnt[Good.CORN] += 1
                    elif tt == TileType.SUGAR_PLANTATION:   plan_cnt[Good.SUGAR] += 1
                    elif tt == TileType.INDIGO_PLANTATION:  plan_cnt[Good.INDIGO] += 1
            bldg_cap = {g: 0 for g in Good}
            for b in p.city_board:
                bt = b.building_type
                if bt in (BuildingType.SMALL_INDIGO_PLANT, BuildingType.INDIGO_PLANT):
                    bldg_cap[Good.INDIGO] += b.colonists
                elif bt in (BuildingType.SMALL_SUGAR_MILL, BuildingType.SUGAR_MILL):
                    bldg_cap[Good.SUGAR] += b.colonists
                elif bt == BuildingType.TOBACCO_STORAGE:
                    bldg_cap[Good.TOBACCO] += b.colonists
                elif bt == BuildingType.COFFEE_ROASTER:
                    bldg_cap[Good.COFFEE] += b.colonists
            pcap[Good.COFFEE]  = min(plan_cnt[Good.COFFEE],  bldg_cap[Good.COFFEE])
            pcap[Good.TOBACCO] = min(plan_cnt[Good.TOBACCO], bldg_cap[Good.TOBACCO])
            pcap[Good.CORN]    = plan_cnt[Good.CORN]
            pcap[Good.SUGAR]   = min(plan_cnt[Good.SUGAR],   bldg_cap[Good.SUGAR])
            pcap[Good.INDIGO]  = min(plan_cnt[Good.INDIGO],  bldg_cap[Good.INDIGO])

            parts.extend([
                bc,
                np.array([p.doubloons], dtype=np.float32),
                np.array([p.empty_city_spaces], dtype=np.float32),
                np.array([p.goods[Good(g)] for g in range(5)], dtype=np.float32),
                hb,
                np.array([p.empty_island_spaces], dtype=np.float32),
                itc, ito, pcap,
                np.array([p.unplaced_colonists], dtype=np.float32),
                np.array([p.vp_chips], dtype=np.float32),
            ])

        return np.concatenate([p.flatten() for p in parts])
```

### 4.5 미래 버전 어댑터 예시

`pr_env.py`에 per-player `total_colonists` 필드가 추가된다고 가정:

```python
@register("v2_semantic_296")
class ObsAdapterV2Semantic(ObsAdapter):
    """v2: per-player에 total_colonists(1) 추가. obs_dim=296 (3P)"""

    @property
    def version(self) -> str:
        return "v2_semantic_296"

    @property
    def obs_dim(self) -> int:
        return 296

    @property
    def global_dim(self) -> int:
        return 74  # 변경 없음

    @property
    def per_player_dim(self) -> int:
        return 74  # 73 + 1

    def from_obs_dict(self, obs_dict, num_players=3):
        # v1과 동일 + total_colonists 추가
        ...

    def from_game(self, game, num_players=3):
        # v1의 from_game() 확장
        ...
```

이때 v1 모델은 `v1_semantic_293` adapter의 `from_game()`으로 서빙되므로, `total_colonists` 필드 유무와 무관하게 동작한다.

### 4.6 Checkpoint Metadata

```python
# 학습 시 저장 (train_ppo_hybrid_server.py)
torch.save({
    "model_state_dict": agent.state_dict(),
    "obs_adapter_version": adapter.version,    # "v1_semantic_293"
    "obs_dim": adapter.obs_dim,                # 293
    "num_players": NUM_PLAYERS,
    "step": global_step,
    "optimizer_state_dict": optimizer.state_dict(),
}, checkpoint_path)
```

### 4.7 Checkpoint Utils (`adapters/checkpoint_utils.py`)

```python
import torch

PHASE_EMBED_DIM = 16

# embed.0.weight의 input_dim → version
_DIM_TO_VERSION = {
    293: "v1_semantic_293",
    # 210, 211: ordinal 모델 — action 불호환으로 서빙 불가
}


def infer_version_from_checkpoint(state_dict: dict) -> str:
    """
    obs_adapter_version 메타데이터가 없는 체크포인트에서
    embed layer shape로 버전 추론.
    """
    embed_weight = state_dict.get("embed.0.weight")
    if embed_weight is None:
        raise ValueError("Cannot infer version: no embed.0.weight found")

    input_dim = int(embed_weight.shape[1])
    is_phase_ppo = "phase_embed.weight" in state_dict
    obs_dim = input_dim - PHASE_EMBED_DIM if is_phase_ppo else input_dim

    if obs_dim in _DIM_TO_VERSION:
        return _DIM_TO_VERSION[obs_dim]

    # Ordinal 모델은 action semantics 불호환
    if obs_dim in (210, 211):
        raise ValueError(
            f"obs_dim={obs_dim} is an ordinal-encoding model. "
            "Action semantics changed (slot→type for Mayor/Settler). "
            "This model cannot run on the current engine."
        )

    raise ValueError(f"Unknown obs_dim={obs_dim}. Register a new adapter version.")


def load_checkpoint_with_adapter(path: str):
    """
    체크포인트 로드 → (state_dict, version, obs_dim) 반환.
    """
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)

    if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
        state_dict = checkpoint["model_state_dict"]
        version = checkpoint.get("obs_adapter_version")
    else:
        state_dict = checkpoint
        version = None

    if version is None:
        version = infer_version_from_checkpoint(state_dict)

    from adapters.registry import get_adapter
    adapter = get_adapter(version)

    return state_dict, version, adapter.obs_dim
```

### 4.8 `adapters/__init__.py`

```python
from adapters.registry import (
    get_adapter,
    get_current_adapter,
    list_versions,
    CURRENT_VERSION,
)
from adapters.base import ObsAdapter
from adapters.checkpoint_utils import infer_version_from_checkpoint, load_checkpoint_with_adapter

# 어댑터 모듈 auto-import (register 데코레이터 실행)
import adapters.v1_semantic_293  # noqa: F401

__all__ = [
    "ObsAdapter",
    "get_adapter",
    "get_current_adapter",
    "list_versions",
    "infer_version_from_checkpoint",
    "load_checkpoint_with_adapter",
    "CURRENT_VERSION",
]
```

---

## 5. Integration Points

### 5.1 학습 파이프라인 (`train/train_ppo_hybrid_server.py`)

**Before:**

```python
from utils.env_wrappers import flatten_dict_observation, get_flattened_obs_dim

obs_space = env.observation_space(agent)["observation"]
obs_dim = get_flattened_obs_dim(obs_space)
flat_obs = flatten_dict_observation(obs_dict["observation"], obs_space)
```

**After:**

```python
from adapters import get_current_adapter

adapter = get_current_adapter()
obs_dim = adapter.obs_dim
flat_obs = adapter.from_obs_dict(obs_dict["observation"], num_players=NUM_PLAYERS)
```

체크포인트 저장 시 `obs_adapter_version` 포함.

### 5.2 Backend 서빙 (`backend/app/services/agents/wrappers.py`)

**Before:**

```python
def _adapt_obs_dim(obs, expected_dim):
    if current_dim == 211 and expected_dim == 210:
        return torch.cat([obs[..., :42], obs[..., 43:]], dim=-1)
    if current_dim == 210 and expected_dim == 211:
        pad = torch.zeros(*obs.shape[:-1], 1, ...)
        return torch.cat([obs[..., :42], pad, obs[..., 42:]], dim=-1)
    raise ValueError(...)
```

**After:**

```python
class PPOWrapper(AgentWrapper):
    def __init__(self, model_path, obs_dim):
        state_dict = _load_checkpoint_state_dict(model_path)
        version = checkpoint.get("obs_adapter_version") \
                  or infer_version_from_checkpoint(state_dict)
        self._adapter = get_adapter(version)
        self._agent = Agent(obs_dim=self._adapter.obs_dim, action_dim=200)
        ...

    def act(self, obs, mask, phase_id=9, obs_dict=None, env=None, **kw):
        if obs_dict is not None:
            flat = self._adapter.from_obs_dict(obs_dict)
        elif env is not None:
            flat = self._adapter.from_game(env.game if hasattr(env, 'game') else env)
        else:
            flat = obs.numpy() if isinstance(obs, torch.Tensor) else obs
        obs_t = torch.as_tensor(flat, dtype=torch.float32).unsqueeze(0)
        mask_t = _ensure_batched_mask(mask)
        ...
```

`_adapt_obs_dim()` 함수와 `_infer_residual_obs_dim()` / `_infer_phase_obs_dim()` 함수는 모두 삭제.

### 5.3 Backend 호출 경로

```text
EngineWrapper.step()
    → env.observe(agent)
    → obs_dict = raw["observation"]
    → AgentWrapper.act(obs_dict=obs_dict, env=env)
        → adapter.from_obs_dict(obs_dict)  (or from_game)
        → model.forward(flat_obs)
        → action (int)
```

Backend API 계약 변경 없음.

---

## 6. 새 버전 추가 절차 (Future Workflow)

### Step 1: `pr_env.py` obs 변경

예: per-player에 `total_colonists` 필드 추가.

### Step 2: 새 어댑터 작성

```bash
touch PuCo_RL/adapters/v2_semantic_296.py
```

`from_obs_dict()`와 `from_game()` 모두 구현. 기존 v1 adapter는 **그대로 유지** (frozen).

### Step 3: registry 업데이트

```python
# adapters/registry.py
CURRENT_VERSION: str = "v2_semantic_296"

# adapters/__init__.py
import adapters.v2_semantic_296  # noqa: F401
```

### Step 4: 학습 & 서빙

- 새 학습 → v2 adapter + 체크포인트에 `v2_semantic_296` 기록
- 기존 v1 모델 → v1 adapter의 `from_game()`으로 서빙 (obs_dict 키 변경 무관)

---

## 7. Scope

### In

- `PuCo_RL/adapters/` 모듈 신규 생성 (base, registry, checkpoint_utils, v1_semantic_293)
- `train_ppo_hybrid_server.py` — adapter 사용으로 변경
- `backend/app/services/agents/wrappers.py` — `_adapt_obs_dim()` 핵 삭제, adapter 사용
- 기존 체크포인트의 obs_dim → version 자동 추론
- `from_obs_dict()` 결과 == `flatten_dict_observation()` 결과 동일성 테스트

### Out

- Old ordinal 모델(210/211) 호환 (action semantics 불호환으로 불가능)
- `pr_env.py` observation space 자체의 변경 (별도 작업)
- 룰 기반 에이전트 변경 (obs_dict 직접 읽으므로 adapter 불필요)
- Frontend/Backend API 계약 변경 (없음)
- 새 PPO 모델 학습 (adapter 인프라 구축 후 별도 진행)

---

## 8. Validation Plan

1. **Parity 테스트**: `v1_semantic_293.from_obs_dict(obs)` == `flatten_dict_observation(obs, space)` 검증
2. **from_game 테스트**: `v1_semantic_293.from_game(game)` == `v1_semantic_293.from_obs_dict(_get_obs(game))` 검증
3. **차원 검증**: `adapter.obs_dim == len(adapter.from_obs_dict(sample))` 항상 성립
4. **Checkpoint 추론**: 기존 293dim 체크포인트 → `v1_semantic_293` 정확 추론
5. **Ordinal 거부**: 210/211dim 체크포인트 → ValueError 정확 발생
6. **E2E**: Docker에서 adapter 경유 PPO 서빙으로 게임 1판 완주
7. **회귀**: adapter 도입 전후 PPO inference 결과 동일

---

## 9. Migration Checklist

- [ ] `PuCo_RL/adapters/` 디렉토리 및 모든 파일 생성
- [ ] `v1_semantic_293`의 parity 테스트 (vs `flatten_dict_observation`)
- [ ] `v1_semantic_293`의 `from_game()` 일관성 테스트
- [ ] `checkpoint_utils.py`로 기존 `.pth` 파일 버전 추론 테스트
- [ ] `train_ppo_hybrid_server.py` — adapter 사용으로 변경 + 체크포인트 메타데이터
- [ ] `backend/app/services/agents/wrappers.py` — `_adapt_obs_dim()` 삭제, adapter 사용
- [ ] Docker E2E 검증
- [ ] `utils/env_wrappers.py`는 삭제하지 않고 유지 (fallback/테스트용)

---

## 10. Risk & Mitigation

| 리스크 | 완화 방안 |
| --- | --- |
| `from_obs_dict()` sorted key 순서가 `flatten_dict_observation()`과 다를 수 있음 | parity 테스트로 bit-exact 검증 |
| `from_game()`의 game engine API 변경 | engine은 obs보다 안정적; 변경 시 모든 adapter에 compilation error 발생하므로 감지 용이 |
| 체크포인트에 optimizer state만 있어 추론 실패 | `model_state_dict` 키 우선 탐색 |
| backend에서 adapter import 시 PuCo_RL path 문제 | 기존 `ensure_puco_rl_path()` 메커니즘 활용 |
| 미래 action semantics 변경 | adapter 범위 밖; action translator는 별도 설계 필요 (현재 안정적이므로 미래 과제) |

---

## 11. Open Questions

1. **`train_ppo_selfplay_server.py`도 adapter 적용?** — 향후 사용 시 적용 필요.
2. **`web/app.py` (standalone 서빙)도 adapter 적용?** — backend가 메인이므로 낮은 우선순위.
3. **Action adapter도 필요한가?** — 현재 semantic action(type-based)은 안정적. 변경 시 별도 설계.
