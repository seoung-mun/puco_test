# Dual Mayor Engine Design

> Deprecated: 이 문서는 human sequential Mayor 와 bot strategy Mayor 공존안을 설명하는 historical design 이다.
> 현재 canonical contract는 strategy-first Mayor 이며 `contract.md` 와
> `design/2026-04-08_engine_cutover_task_breakdown.md` 를 우선한다.

## Date: 2026-04-07

## 1. Overview

PuCo_RL 엔진의 Mayor Phase를 **전략 중심(AI/Bot)**과 **순차 배치(Human)**가 공존하도록 리팩토링한다.
추가로 인간 배치 데이터를 AI 전략으로 변환하는 **결과 벡터 기반 매핑** 로직을 구현한다.

### 핵심 원칙
- **69-71의 시맨틱(MayorStrategy)은 절대 변경 불가** (학습 환경 계약)
- 하나의 게임 = 하나의 canonical engine state (엔진 분리 금지)
- 인간 UX 불변: slot-by-slot 배치 유지
- `player_control_modes`는 게임 생성 시 고정, 중간 변경 불가

---

## 2. Action Space 재설계 (Breaking Change)

### Before (현재)
```
69-72: Mayor Sequential Place (place 0/1/2/3 colonists) — 인간/봇 공용
```

### After (목표)
```
69: MayorStrategy.CAPTAIN_FOCUS    (S0) — Bot 전용
70: MayorStrategy.TRADE_FACTORY_FOCUS (S1) — Bot 전용
71: MayorStrategy.BUILDING_FOCUS   (S2) — Bot 전용
72: HumanSequentialPlace 0 (skip)       — Human 전용
73: HumanSequentialPlace 1              — Human 전용
74: HumanSequentialPlace 2              — Human 전용
75: HumanSequentialPlace 3              — Human 전용
```

### 영향 범위 (17개 파일)
| 파일 | 변경 내용 |
|------|-----------|
| `PuCo_RL/env/engine.py` | dual-mode dispatch, `action_mayor_strategy()` 추가, `map_human_to_strategy()` 추가 |
| `PuCo_RL/env/pr_env.py` | action range shift, dual mask, `player_control_modes` 지원 |
| `PuCo_RL/configs/constants.py` | `ControlMode` enum 추가 |
| `PuCo_RL/utils/board_evaluator.py` | **NEW** — V_prod, V_vp, V_eff 벡터 추출 |
| `PuCo_RL/agents/rule_based_agent.py` | 69-72 → 69-71 (strategy mode) |
| `PuCo_RL/agents/advanced_rule_based_agent.py` | 이미 69-71 사용 (변경 없음) |
| `PuCo_RL/agents/factory_rule_based_agent.py` | 이미 69-71 사용 (변경 없음) |
| `backend/app/services/state_serializer.py` | mayor_can_skip: `[69]` → `[72]` |
| `backend/app/services/mayor_orchestrator.py` | `69 + amount` → `72 + amount` |
| `backend/app/services/replay_logger.py` | range check shift |
| `backend/app/services/bot_service.py` | adapter 제거, engine strategy 직접 사용 |
| `backend/app/services/mayor_strategy_adapter.py` | **DELETE** (엔진이 직접 처리) |
| `backend/app/api/legacy/actions.py` | `69 + amount` → `72 + amount` |
| `backend/app/api/legacy/deps.py` | range check shift |
| `frontend/src/App.tsx` | action index 업데이트 |
| `backend/tests/*` | 모든 Mayor 관련 assertion 업데이트 |

---

## 3. 엔진 제어 로직

### 3.1 ControlMode Enum
```python
class ControlMode(IntEnum):
    HUMAN = 0
    BOT = 1
```

### 3.2 PuertoRicoGame 생성자 확장
```python
class PuertoRicoGame:
    def __init__(self, num_players: int, player_control_modes: list[int] | None = None):
        ...
        # Default: all human (backward compatible)
        self.player_control_modes = player_control_modes or [ControlMode.HUMAN] * num_players
```

### 3.3 Mayor Phase 분기 (engine.py)
```
step(action) 호출 시:
├─ current_phase == MAYOR?
│  ├─ player_control_modes[current_player_idx] == BOT?
│  │  ├─ action in 69-71 → action_mayor_strategy(player_idx, MayorStrategy(action-69))
│  │  └─ action in 72-75 → ValueError("Bot must use strategy actions 69-71")
│  └─ player_control_modes[current_player_idx] == HUMAN?
│     ├─ action in 72-75 → action_mayor_place(player_idx, action-72)
│     └─ action in 69-71 → ValueError("Human must use sequential actions 72-75")
└─ 다른 phase → 기존 로직 그대로
```

### 3.4 action_mayor_strategy() (upstream에서 가져옴)
4단계 자동 배치:
1. Large VP Buildings (GUILDHALL, RESIDENCE, FORTRESS, CUSTOMS_HOUSE, CITY_HALL)
2. Strategy-Specific Buildings (MAYOR_STRATEGY_BUILDINGS[strategy])
3. Production Pairs (Coffee → Tobacco → Sugar → Indigo → Corn)
4. Remaining → empty buildings → empty plantations

### 3.5 action_mayor_place() (기존 유지, index만 shift)
- 현재: `amount = action - 69`
- 변경: `amount = action - 72` (pr_env에서 디코딩)
- engine 내부 메서드 자체는 amount를 받으므로 변경 없음

---

## 4. pr_env.py 변경

### 4.1 생성자 확장
```python
class PuertoRicoEnv(AECEnv):
    def __init__(self, ..., player_control_modes=None):
        ...
        self.player_control_modes = player_control_modes  # PuertoRicoGame에 전달
```

### 4.2 Action Mask (Mayor section)
```python
if phase == Phase.MAYOR:
    if self.player_control_modes[player_idx] == ControlMode.BOT:
        mask[69] = mask[70] = mask[71] = True  # 3 strategies always valid
    else:  # HUMAN
        # 기존 sequential mask 로직, but shifted to 72-75
        # mask[72 + amount] = True (instead of mask[69 + amount])
```

### 4.3 Action Dispatch (step)
```python
elif 69 <= action <= 71:
    # Strategy (Bot only — enforced by mask)
    strategy = MayorStrategy(action - 69)
    self.game.action_mayor_strategy(player_idx, strategy)

elif 72 <= action <= 75:
    # Sequential Placement (Human only)
    amount = action - 72
    self.game.action_mayor_place(player_idx, amount)
```

---

## 5. BoardEvaluator (NEW: utils/board_evaluator.py)

### 5.1 목적
인간 배치 결과를 3차원 벡터 $V = [V_{prod}, V_{vp}, V_{eff}]$로 추출하여
전략 시뮬레이션 결과와 비교한다.

### 5.2 지표 정의

**V_prod (Production Value)**: 다음 생산 단계 기대 재화 가치
```
V_prod = sum(min(manned_plantations[g], manned_buildings[g]) * GOOD_PRICES[g]
             for g in [COFFEE, TOBACCO, SUGAR, INDIGO, CORN])
```
- Corn은 plantation만으로 생산 가능 (건물 불필요)
- GOOD_PRICES: Coffee=4, Tobacco=3, Sugar=2, Indigo=1, Corn=0

**V_vp (VP Potential)**: 활성화된 대형 건물의 잠재적 승점
```
V_vp = sum(BUILDING_DATA[b.building_type][1]  # VP value
           for b in city_board
           if b.building_type in LARGE_VP_BUILDINGS and b.colonists > 0)
```

**V_eff (Efficiency Count)**: 활성화된 특수 기능 건물 수
```
SPECIAL_BUILDINGS = {Factory, Harbor, Wharf, Office, Large_Market, Small_Market,
                     University, Hospice, Construction_Hut, Hacienda,
                     Small_Warehouse, Large_Warehouse}
V_eff = count(b for b in city_board
              if b.building_type in SPECIAL_BUILDINGS and b.colonists > 0)
```

### 5.3 인터페이스
```python
class BoardEvaluator:
    @staticmethod
    def evaluate(player: Player) -> tuple[float, float, float]:
        """보드 상태에서 (V_prod, V_vp, V_eff) 벡터를 추출한다."""

    @staticmethod
    def euclidean_distance(v1: tuple, v2: tuple) -> float:
        """두 벡터 간 유클리드 거리."""
```

---

## 6. map_human_to_strategy() (engine.py)

### 6.1 호출 시점
인간 플레이어가 Mayor 배치를 완료하는 시점 (`mayor_placement_idx >= 24` 또는 `unplaced_colonists == 0`).

### 6.2 알고리즘
```python
def map_human_to_strategy(self, player_idx: int) -> int | None:
    """인간 배치 결과를 가장 가까운 전략(0/1/2)으로 매핑.
    임계값 초과 시 None(noise) 반환."""

    # 1. 현재 보드 상태의 벡터 추출
    human_vector = BoardEvaluator.evaluate(self.players[player_idx])

    # 2. 각 전략을 시뮬레이션하여 벡터 추출
    strategy_vectors = {}
    for s in MayorStrategy:
        game_copy = deepcopy(self)           # pre-placement state 필요
        game_copy.action_mayor_strategy(player_idx, s)
        strategy_vectors[s] = BoardEvaluator.evaluate(game_copy.players[player_idx])

    # 3. 유클리드 거리 계산
    distances = {s: BoardEvaluator.euclidean_distance(human_vector, v)
                 for s, v in strategy_vectors.items()}

    # 4. 최소 거리 전략 반환 (임계값 체크)
    best = min(distances, key=distances.get)
    if distances[best] > NOISE_THRESHOLD:
        return None  # 분류 불가능
    return best.value  # 0, 1, or 2
```

### 6.3 주의사항
- `deepcopy` 비용: Mayor는 게임당 수 회 → 허용 범위
- **pre-placement state 저장 필요**: `_init_mayor_placement()` 호출 전 상태를 보존해야 시뮬레이션 가능
  - `self._mayor_pre_placement_snapshot[player_idx] = deepcopy(self.players[player_idx])`
- 당장은 **로깅용으로만 사용**, 게임 흐름에 영향 없음
- NOISE_THRESHOLD 초기값: 5.0 (튜닝 필요, 하드코딩 후 상수로 분리)

---

## 7. Decision Log

| # | 결정 | 대안 | 이유 |
|---|------|------|------|
| D1 | 69-71 = strategy, 72-75 = sequential (Option 3) | 같은 index 재사용, 별도 범위 추가 | 학습 환경 계약 보존, 시맨틱 명확 분리 |
| D2 | 한 번에 전부 변경 (Option 1) | 변환 레이어 추가, 점진적 이전 | 깔끔하고 기술 부채 없음 |
| D3 | player_control_modes 게임 생성 시 고정 | 매 step 전달, actor_id 파싱 | 불변성 보장, 인증과 분리 |
| D4 | Functional Similarity (V_prod, V_vp, V_eff) | Slot match %, Weighted match | 결과적 의미 비교, 슬롯 순서 무관 |
| D5 | BoardEvaluator 별도 모듈 분리 | engine 내장 | Clean Code, 단일 책임 원칙 |
| D6 | Euclidean Distance + Threshold | Cosine similarity, KNN | 단순, 직관적, 3차원에서 충분 |
| D7 | map_human_to_strategy 로깅 전용 | 게임 흐름 영향 | 안전, 점진적 도입 |
| D8 | MayorStrategyAdapter 제거 | 유지하며 엔진 위임 | 엔진이 직접 처리하므로 중복 |

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| 17개 파일 동시 변경 | 높음 | TDD로 RED→GREEN, 파일별 검증 |
| deepcopy 성능 | 중간 | Mayor는 게임당 수 회, 프로파일링 후 최적화 |
| NOISE_THRESHOLD 잘못된 초기값 | 낮음 | 로깅 전용이므로 게임에 영향 없음 |
| 기존 테스트 대량 실패 | 높음 | action index 일괄 치환 스크립트 준비 |
| Frontend/Backend 동시 배포 필요 | 중간 | Breaking change — 동시 배포 필수 |
