# Dual-Mode Mayor — 상세 작업 현황 및 설계

> Deprecated: 이 문서는 dual-mode Mayor 가정을 전제로 한 과거 계획이다.
> 현재 기준 문서는 `design/2026-04-08_engine_cutover_task_breakdown.md`, `contract.md`,
> `design/2026-04-08_engine_cutover_phase2_contract_followup.md` 를 사용한다.

> 최종 갱신: 2026-04-08

---

## 1. 프로젝트 개요

Puerto Rico 보드게임 RL 환경의 **Mayor Phase를 Dual-Mode로 분리**:

| 모드 | Action 범위 | 동작 | 대상 |
|------|------------|------|------|
| **Strategy (Bot)** | 69-71 | 1-step 전략 기반 배치 (CAPTAIN/TRADE/BUILDING) | ControlMode.BOT |
| **Sequential (Human)** | 72-75 | slot-by-slot 배치 (0/1/2/3 colonists) | ControlMode.HUMAN |

**핵심 원칙**: action_dim=200 불변, 69-71 semantics 영구 고정 (learning contract), 인간 UX 불변.

---

## 2. 아키텍처 구조

```
PuCo_RL/
├── configs/constants.py          ✅ ControlMode, MayorStrategy, LARGE_VP_BUILDINGS 등 추가 완료
├── env/engine.py                 ✅ player_control_modes, action_mayor_strategy(), map_human_to_strategy()
├── env/pr_env.py                 ✅ dual-mode dispatch (69-71 bot, 72-75 human), dual mask
├── utils/board_evaluator.py      ✅ V=(V_prod, V_vp, V_eff) 가중치 기반 벡터 추출
├── tests/
│   ├── test_engine_dual_mayor.py ✅ 18/18 PASSED
│   ├── test_board_evaluator.py   ✅ 19/19 PASSED
│   └── test_mayor_strategy_mapping.py  🔴 10/12 PASSED (2 FAILED)
│
backend/
├── app/services/
│   ├── mayor_strategy_adapter.py  ⏳ Task 3 (plan.md) — 별도 plan 있으나 현재 접근법과 다름
│   ├── bot_service.py             ⏳ Mayor 분기 연동 필요
│   ├── game_service.py            ⏳ broadcast suppress 연동 필요
│   ├── state_serializer.py        ⏳ 69-72 → 72-75 마이그레이션 필요
│   ├── mayor_orchestrator.py      ⏳ 69-72 → 72-75 마이그레이션 필요
│   ├── action_translator.py       ⏳ 69-72 → 72-75 마이그레이션 필요
│   └── agent_registry.py          ⏳ rule-based agent 등록 필요
├── tests/
│   ├── test_mayor_strategy_adapter.py     🔴 5/6 FAILED (adapter 미완성)
│   └── test_bot_mayor_adapter_integration.py  🔴 4/4 FAILED (bot 연동 미완성)
│
frontend/                          ⏳ action index 업데이트 필요
```

---

## 3. 완료된 작업 (GREEN ✅)

### 3.1 configs/constants.py — 상수 추가
- `ControlMode(IntEnum)`: HUMAN=0, BOT=1
- `MayorStrategy(IntEnum)`: CAPTAIN_FOCUS=0, TRADE_FACTORY_FOCUS=1, BUILDING_FOCUS=2
- `LARGE_VP_BUILDINGS`, `MAYOR_STRATEGY_BUILDINGS`, `PRODUCTION_BUILDINGS`, `PLANTATION_TO_GOOD`, `GOOD_VALUE_ORDER`

### 3.2 engine.py — Dual-Mode 엔진
- 생성자 `player_control_modes` 파라미터 (길이/값 유효성 검증, 기본값 all HUMAN)
- `action_mayor_strategy(player_idx, strategy)`: 4단계 배치 알고리즘
  1. Large VP Buildings → 2. Strategy-Specific → 3. Production Pairs (Coffee→Tobacco→Sugar→Indigo→Corn) → 4. Remaining
- `map_human_to_strategy(player_idx)`: deepcopy + 각 전략 시뮬레이션 → BoardEvaluator 벡터 비교 → 유클리드 거리 최소 전략 반환 (NOISE_THRESHOLD=5.0 초과 시 None)

### 3.3 pr_env.py — Action Space 재설계
- Action 69-71: Bot strategy dispatch (ControlMode.BOT만 허용)
- Action 72-75: Human sequential dispatch (ControlMode.HUMAN만 허용)
- Dual mask: Bot → `mask[69:72]=True`, Human → 기존 sequential logic을 `mask[72:76]`으로 shift
- 잘못된 mode 접근 시 ValueError → termination + reward=-10

### 3.4 utils/board_evaluator.py — 상태 벡터 추출
- `V_prod`: min(manned_plantations, manned_building_cap) × GOOD_PRICES 합. Corn은 건물 불필요.
- `V_vp`: 활성화된 LARGE_VP_BUILDINGS의 BUILDING_DATA VP 합.
- `V_eff`: **카테고리 가중치 합** (단순 개수가 아님):
  - Shipping (WHARF, HARBOR, SMALL_WAREHOUSE, LARGE_WAREHOUSE): **1.0**
  - Trading (OFFICE, LARGE_MARKET, SMALL_MARKET, FACTORY): **2.0**
  - Building (UNIVERSITY, HOSPICE, CONSTRUCTION_HUT, HACIENDA): **3.0**
- `euclidean_distance(v1, v2)`: 3차원 유클리드 거리

### 3.5 테스트 현황 (PuCo_RL)

| 테스트 파일 | 결과 | 내용 |
|------------|------|------|
| `test_engine_dual_mayor.py` | **18/18 PASSED** ✅ | ControlMode, mask, dispatch, phase completion, mixed game |
| `test_board_evaluator.py` | **19/19 PASSED** ✅ | V_prod, V_vp, V_eff(가중치), vector shape, distance |
| `test_mayor_strategy_mapping.py` | **10/12 PASSED** 🔴 | 2 FAILED: trade→S0, building→S1 |

---

## 4. 현재 진행 중인 작업 🔴

### 4.1 test_mayor_strategy_mapping.py — 2개 실패 원인

**문제**: 수동 배치(manual placement)가 전략 시뮬레이션 결과와 벡터가 다름.

전략 시뮬레이션은 Step 4(remaining)에서 빈 건물을 추가로 채우지만, 수동 배치는 전략 특성 건물만 채움.

#### 전략 시뮬레이션 결과 (colonists=8, rich board):

| 전략 | 활성 건물 | V_eff | V_prod | Vector |
|------|----------|-------|--------|--------|
| CAPTAIN_FOCUS | WHARF(1.0)+HARBOR(1.0)+OFFICE(2.0) | **4.0** | 5.0 | (5,0,4) |
| TRADE_FACTORY | WHARF(1.0)+OFFICE(2.0)+FACTORY(2.0) | **5.0** | 5.0 | (5,0,5) |
| BUILDING_FOCUS | WHARF(1.0)+UNIVERSITY(3.0)+HOSPICE(3.0) | **7.0** | 5.0 | (5,0,7) |

> 모든 전략이 Step 4에서 WHARF(shipping=1.0)를 추가로 채움!
> Step 2(strategy buildings) 이후 남은 colonist로 Step 3(production) + Step 4(spillover) 진행.

#### 수동 배치 벡터 (현재):

| 수동 배치 | 활성 건물 | V_eff | 가장 가까운 전략 | 기대값 |
|----------|----------|-------|-----------------|--------|
| Trade manual | OFFICE(2.0)+FACTORY(2.0) | **4.0** | CAPTAIN(거리0) ❌ | TRADE(1) |
| Building manual | UNIVERSITY(3.0)+HOSPICE(3.0) | **6.0** | TRADE/BUILDING(거리1) ❌ | BUILDING(2) |

#### 해결 방향:
수동 배치에 전략 시뮬레이션의 Step 4 spillover(WHARF 등)를 반영해야 함.
- Trade manual: OFFICE+FACTORY+**WHARF** 추가 → V_eff=2.0+2.0+1.0=5.0 → TRADE(5.0)와 거리=0 ✅
- Building manual: UNIVERSITY+HOSPICE+**WHARF** 추가 → V_eff=3.0+3.0+1.0=7.0 → BUILDING(7.0)와 거리=0 ✅

---

## 5. 남은 작업 목록

### Phase A: PuCo_RL 엔진 GREEN 완료 (현재)

| # | 작업 | 상태 | 설명 |
|---|------|------|------|
| A1 | test_mayor_strategy_mapping.py 수정 | 🔴 IN PROGRESS | 수동 배치에 WHARF spillover 반영 |
| A2 | PuCo_RL 전체 regression | ⏳ | 기존 test_engine, test_phase_edge_cases 등 확인 |

### Phase B: Backend 69-72 → 72-75 마이그레이션

| # | 파일 | 변경 내용 | 상태 |
|---|------|----------|------|
| B1 | `state_serializer.py` | Mayor action mask/slot_idx 72-75 shift | ⏳ |
| B2 | `mayor_orchestrator.py` | action translate 69→72, 72→75 등 | ⏳ |
| B3 | `action_translator.py` | action range 69-72→72-75 | ⏳ |
| B4 | `replay_logger.py` | Mayor action logging range update | ⏳ |
| B5 | `bot_service.py` | Mayor phase 분기 + adapter 연동 | ⏳ |
| B6 | `game_service.py` | Mayor batch broadcast suppress | ⏳ |
| B7 | 기타 backend 파일 (10+) | 하드코딩된 69-72 참조 전부 업데이트 | ⏳ |

### Phase C: Backend Adapter & Bot 연동

| # | 작업 | 상태 | 설명 |
|---|------|------|------|
| C1 | `mayor_strategy_adapter.py` 업데이트 | ⏳ | 현재 plan.md의 Task 3과 다른 접근법 → engine 직접 사용으로 단순화 가능 |
| C2 | `bot_service.py` Mayor 분기 | ⏳ | Bot이 69-71 선택 → engine.step()이 직접 처리 |
| C3 | `test_mayor_strategy_adapter.py` 수정 | ⏳ | 현재 6개 테스트 중 5개 실패 |
| C4 | `test_bot_mayor_adapter_integration.py` 수정 | ⏳ | 현재 4개 전부 실패 |

### Phase D: Agent & Registry

| # | 작업 | 상태 | 설명 |
|---|------|------|------|
| D1 | `agent_registry.py` 확장 | ⏳ | rule_based, advanced_rule 등록 |
| D2 | rule_based agents 추가 | ⏳ | upstream에서 가져올 agent 파일들 |
| D3 | `/api/bot-types` 응답 확장 | ⏳ | 새 agent type 노출 |

### Phase E: Frontend

| # | 작업 | 상태 | 설명 |
|---|------|------|------|
| E1 | `App.tsx` action index 업데이트 | ⏳ | 69-72 → 72-75 |
| E2 | Mayor UI 컴포넌트 확인 | ⏳ | slot-by-slot UI 불변 확인 |

### Phase F: Regression

| # | 작업 | 상태 | 설명 |
|---|------|------|------|
| F1 | PuCo_RL 전체 테스트 | ⏳ | 기존 114개 + 신규 49개 |
| F2 | Backend 전체 테스트 | ⏳ | 기존 335개 + 신규 |
| F3 | Frontend 빌드 확인 | ⏳ | TypeScript 컴파일 오류 없음 확인 |

---

## 6. 기존 실패 테스트 (Dual-Mayor와 무관한 기존 이슈)

| 테스트 | 원인 | 대응 |
|--------|------|------|
| `test_hppo_agent.py` | ImportError: `HierarchicalAgent` 미존재 | 기존 이슈 (hppo agent 미구현) |
| `test_agent_edge_cases.py::test_mcts_progressive_widening` | `fast_clone` 미구현 | 기존 이슈 |
| `test_mayor_sequential.py` | assertion fail | **조사 필요**: 69-72→72-75 변경 영향? |
| `test_phase_edge_cases.py::TestMayorPhase` (4개) | 69+amount → 72+amount shift 미반영 | Phase B 작업 후 수정 |
| `test_phase_edge_cases.py::TestBuilderPhase` (2개) | city board full 로직 | 기존 이슈 |
| `test_pr_env.py::test_pettingzoo_api` | obs dict dtype 이슈 | 기존 이슈 |
| `test_todo_priority1_task1_mayor_contract.py` (1개) | serializer slot_idx 불일치 | Phase B에서 해결 |

---

## 7. 설계 결정 기록 (Decision Log)

| # | 결정 | 대안 | 이유 |
|---|------|------|------|
| D1 | ControlMode를 게임 생성 시 고정 | 런타임 변경 가능 | 안전성, RL 학습 일관성 |
| D2 | 69-71=Strategy, 72-75=Sequential | 69-72 유지 + 별도 flag | Action semantics 고정 = learning contract |
| D3 | V_eff에 카테고리 가중치 적용 | 단순 개수 | 전략 간 벡터 차별화 필수 |
| D4 | map_human_to_strategy는 deepcopy 기반 | 분석적 계산 | 정확성 보장, 성능은 로깅용이므로 문제 없음 |
| D5 | NOISE_THRESHOLD=5.0 | 동적 임계값 | 시작값으로 충분, 운영 데이터 후 조정 |
| D6 | V_eff 가중치: Shipping=1, Trading=2, Building=3 | 균일 가중치 | MAYOR_STRATEGY_BUILDINGS 카테고리와 직접 대응 |

---

## 8. 핵심 코드 참조

### Action Space (pr_env.py)
```
0-7:     Role Selection
8-14:    Settler - Select Plantation
15-67:   Builder - Build Building
68:      Pass (Captain Store, Craftsman, Settler, Trader)
69-71:   Mayor Strategy (Bot only: S0/S1/S2)
72-75:   Mayor Sequential (Human only: place 0/1/2/3)
76-80:   Trader - Sell Good
81-105:  Captain - Load Ship
106-110: Craftsman Privilege Good
111-199: Reserved
```

### BoardEvaluator V_eff Category Weights
```python
_CATEGORY_WEIGHTS = {
    WHARF: 1.0, HARBOR: 1.0, SMALL_WAREHOUSE: 1.0, LARGE_WAREHOUSE: 1.0,  # Shipping
    OFFICE: 2.0, LARGE_MARKET: 2.0, SMALL_MARKET: 2.0, FACTORY: 2.0,       # Trading
    UNIVERSITY: 3.0, HOSPICE: 3.0, CONSTRUCTION_HUT: 3.0, HACIENDA: 3.0,   # Building
}
```

### Strategy Algorithm (engine.py action_mayor_strategy)
```
Step 1: Large VP Buildings (GUILDHALL→RESIDENCE→FORTRESS→CUSTOMS_HOUSE→CITY_HALL)
Step 2: Strategy Buildings (MAYOR_STRATEGY_BUILDINGS[strategy])
Step 3: Production Pairs (Coffee→Tobacco→Sugar→Indigo→Corn, min(plantation, building))
Step 4: Remaining → empty buildings → empty plantations
```

---

## 9. Docker 테스트 명령어

```bash
# PuCo_RL 테스트 (hppo 제외)
docker compose exec backend python -m pytest /PuCo_RL/tests/ -v --tb=short \
  --ignore=/PuCo_RL/tests/test_hppo_agent.py

# 특정 파일
docker compose exec backend python -m pytest /PuCo_RL/tests/test_board_evaluator.py -v
docker compose exec backend python -m pytest /PuCo_RL/tests/test_engine_dual_mayor.py -v
docker compose exec backend python -m pytest /PuCo_RL/tests/test_mayor_strategy_mapping.py -v

# Backend 테스트
docker compose exec backend python -m pytest /app/tests/ -v --tb=short
```

---

## 10. 파일 의존성 그래프

```
configs/constants.py (ControlMode, MayorStrategy, ...)
         ↓
    env/engine.py (action_mayor_strategy, map_human_to_strategy)
         ↓
    env/pr_env.py (dual mask, dual dispatch)
         ↓
    utils/board_evaluator.py (V_prod, V_vp, V_eff)
         ↓
backend/app/services/
    ├── state_serializer.py (obs → frontend state)
    ├── mayor_orchestrator.py (human Mayor flow)
    ├── action_translator.py (frontend action → engine action)
    ├── bot_service.py (bot turn execution)
    └── game_service.py (game lifecycle + broadcast)
         ↓
frontend/src/App.tsx (action index display)
```
