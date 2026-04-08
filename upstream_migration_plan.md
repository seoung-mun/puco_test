# Upstream 전량 반영 + Wrapper 호환 계층 마이그레이션 계획

작성일: 2026-04-06 (최종 갱신: 2026-04-07)
기준 문서:
- [contract.md](/Users/seoungmun/Documents/agent_dev/castest/castone/contract.md)
- [2026-04-06_puco_upstream_fetch_report.md](/Users/seoungmun/Documents/agent_dev/castest/castone/error_report/2026-04-06_puco_upstream_fetch_report.md)

실행 계획: `.claude/plans/cozy-enchanting-tome.md` — Task 1~10으로 분리된 실행 가능한 작업 목록

---

## 1. 핵심 설계 결정

### 엔진은 sequential Mayor를 유지한다

upstream이 Mayor를 strategy-based one-shot으로 바꾼 이유는 **봇 학습 효율** 때문이다.
sequential 방식은 한 번의 Mayor 턴에 슬롯 수만큼 step을 소모하므로 학습에서 비효율적이다.
하지만 인간 플레이어에게는 slot-by-slot 배치가 자연스러운 경험이고, 이걸 바꿀 이유가 없다.

따라서:

```
엔진(engine.py, pr_env.py)  →  sequential Mayor 유지 (현재 로컬 그대로)
봇 전용 adapter              →  MayorStrategyAdapter (strategy→sequential 변환)
인간 플레이어                 →  기존 /mayor-distribute API 그대로
```

### 장점

1. **phase 정합성이 단순** — 엔진은 한 가지 Mayor 규칙만 알면 됨
2. **인간 UX 불변** — frontend, mayor_orchestrator, REST API 모두 그대로
3. **봇은 새 모델 사용 가능** — strategy action(69-71)을 adapter가 sequential action(69-72) 연속 호출로 풀어줌
4. **mixed game 안전** — 인간이든 봇이든 엔진 입장에서는 동일한 sequential action sequence

---

## 2. 현재 상태 비교

### 2.1 Local vs Upstream 핵심 차이

| 항목 | 현재 로컬 | upstream main |
|------|----------|---------------|
| Mayor 모델 | sequential (slot cursor 0-23) | strategy one-shot (3가지) |
| Mayor 액션 | 69-72 (place 0/1/2/3) | 69-71 (3 strategies) |
| auto-action | 없음 | `_execute_auto_actions()` 있음 |
| PBRS | 항상 on | `use_pbrs` 토글 |
| Hacienda | 수동 선택 (action 105) | 자동 사용 |
| potential 계산 | 6개 컴포넌트 (확장됨) | 3개 컴포넌트 |
| observation | global_state에 `mayor_slot_idx` 포함 | `mayor_slot_idx` 없음 |
| `unplaced_colonists` 범위 | Discrete(20) | Discrete(50) |
| agent 종류 | PPO, HPPO, Random | + rule_based, advanced_rule_based, factory_rule_based |
| `__init__` | `num_players, max_game_steps, w_*, potential_mode` | + `use_pbrs: bool = True` |

### 2.2 Non-Mayor Phase 호환성 (95% 동일)

| 비교 항목 | 동일? | 비고 |
|-----------|-------|------|
| action 0-68 매핑 | YES | Settler/Builder/Trader/Captain 전부 동일 |
| action 93-110 매핑 | YES | Craftsman/Hacienda/Warehouse 동일 |
| Settler masking | YES | (Hacienda 자동화 제외) |
| Builder masking | YES | |
| Trader masking | YES | |
| Captain masking | YES | |
| Craftsman masking | YES | |
| Pass handling | YES | |
| Hacienda in Settler | NO | 로컬: 수동(action 105), upstream: 자동 |
| Potential 계산 | NO | 로컬: 6개 컴포넌트, upstream: 3개 |
| Auto-actions | NO | upstream에만 있음 |
| PBRS 토글 | NO | upstream에만 있음 |
| obs mayor_slot_idx | NO | 로컬에만 있음 |

### 2.3 upstream Mayor strategy 알고리즘 (adapter 구현에 필요)

strategy→배치 변환은 **4단계 우선순위**로 결정적(deterministic):

```
Step 1: Large VP Buildings (항상 최우선)
  → GUILDHALL, RESIDENCE, FORTRESS, CUSTOMS_HOUSE, CITY_HALL

Step 2: Strategy-Specific Buildings
  → CAPTAIN_FOCUS:        WHARF, HARBOR, LARGE_WAREHOUSE, SMALL_WAREHOUSE
  → TRADE_FACTORY_FOCUS:  OFFICE, LARGE_MARKET, SMALL_MARKET, FACTORY
  → BUILDING_FOCUS:       UNIVERSITY, HOSPICE, CONSTRUCTION_HUT, HACIENDA

Step 3: Production Pairs (Coffee > Tobacco > Sugar > Indigo > Corn 순서)
  → 각 재화별로: 농장 먼저, 그 다음 생산 건물
  → producible = min(빈 농장 수, 건물 용량)

Step 4: 남은 식민자 → 나머지 건물 → 나머지 농장/채석장
```

### 2.4 Backend 직접 의존 파일

| 파일 | import 대상 | 결합도 | Mayor 영향 |
|------|------------|--------|-----------|
| `engine_wrapper/wrapper.py` | `env.pr_env.PuertoRicoEnv` | VERY HIGH | LOW (sequential 유지) |
| `services/state_serializer.py` | `configs.constants.*`, engine 속성 30+ | VERY HIGH | LOW (sequential 유지) |
| `services/action_translator.py` | `configs.constants.Role/Good/BuildingType/TileType` | MODERATE | LOW |
| `services/model_registry.py` | `env.pr_env`, `utils.env_wrappers`, `agents.ppo_agent` | MODERATE | MEDIUM (새 모델) |
| `services/agent_registry.py` | `agents.base`, `agents.wrappers` | HIGH | MEDIUM (새 agent) |
| `services/bot_service.py` | `utils.env_wrappers`, `env.pr_env` | MODERATE | HIGH (adapter 연동) |
| `services/mayor_orchestrator.py` | `configs.constants.*` | MODERATE | NONE (인간 전용, 불변) |
| `services/replay_logger.py` | `configs.constants.*` | LOW | LOW |

---

## 3. 무엇을 가져오고, 무엇을 유지하는가

### 3.1 Upstream에서 가져올 것

| 항목 | 파일 | 이유 |
|------|------|------|
| MayorStrategy enum + 상수 | `configs/constants.py` | adapter가 strategy→배치 매핑에 사용 |
| rule-based agents | `agents/rule_based_agent.py` 등 | 새 agent 생태계 |
| league/evaluate 스크립트 | `evaluate/run_league.py` | 평가 인프라 |
| web/report 자산 | `web/`, `report/` | upstream mirror |
| advanced training script 개선 | `train/` | 실험 관리 개선 |

### 3.2 Upstream과 다르게 유지할 것

| 항목 | 현재 파일 | 이유 | 팀원에게 설명할 내용 |
|------|----------|------|---------------------|
| Mayor: sequential placement | `engine.py` | 인간 UX 유지 + phase 단순성 | "엔진의 Mayor는 sequential 그대로 둡니다. 봇은 adapter가 strategy→sequential로 풀어줍니다" |
| Mayor action space: 69-72 | `pr_env.py` | 기존 action index 계약 유지 | "action 69-72는 기존 의미(place 0-3) 그대로입니다. MayorStrategyAdapter가 번역합니다" |
| obs에 mayor_slot_idx 유지 | `pr_env.py` | serializer 호환, 인간 UI용 | "upstream에 없는 필드지만 우리 frontend가 필요합니다" |
| Potential 계산 6개 컴포넌트 | `pr_env.py` | 더 풍부한 reward signal | "upstream보다 potential이 확장돼 있습니다. 성능 비교 후 결정" |
| Hacienda 수동 선택 | `pr_env.py` | 인간에게 선택권 유지 | "upstream은 auto인데 우리는 인간 조작이 있어서 수동 유지합니다" |

### 3.3 새로 만들 것

| 항목 | 위치 | 역할 |
|------|------|------|
| `MayorStrategyAdapter` | `backend/app/services/mayor_strategy_adapter.py` | 봇의 strategy action(69-71) → sequential action(69-72) 연속 호출 변환 |

---

## 4. MayorStrategyAdapter 상세 설계

### 4.1 역할

```
봇 추론 → action 69 (CAPTAIN_FOCUS)
  → MayorStrategyAdapter.expand(strategy=0, game, player_idx)
    → 4단계 우선순위로 배치 계획 생성
    → [{slot_idx: 3, amount: 1}, {slot_idx: 7, amount: 2}, ...]
    → sequential action 시퀀스로 변환
    → [69, 69, 70, 69, 71, ...] (slot마다 69+amount)
  → 엔진에 순차 적용
```

### 4.2 구현 스펙

```python
class MayorStrategyAdapter:
    """봇의 Mayor strategy 선택을 기존 sequential placement로 변환"""

    STRATEGY_BUILDINGS = {
        0: [BuildingType.WHARF, BuildingType.HARBOR, ...],      # CAPTAIN_FOCUS
        1: [BuildingType.OFFICE, BuildingType.LARGE_MARKET, ...], # TRADE_FACTORY_FOCUS
        2: [BuildingType.UNIVERSITY, BuildingType.HOSPICE, ...],  # BUILDING_FOCUS
    }

    LARGE_VP_BUILDINGS = [BuildingType.GUILDHALL, ...]

    GOOD_VALUE_ORDER = [Good.COFFEE, Good.TOBACCO, Good.SUGAR, Good.INDIGO, Good.CORN]

    def expand(self, strategy: int, game, player_idx: int) -> list[int]:
        """
        strategy (0/1/2) → sequential action list (각 action은 69+amount)

        반환값: 엔진의 action_mayor_place()에 순차 전달할 amount 리스트
        리스트 길이 = mayor_placement_idx가 순회하는 슬롯 수 (빈 슬롯 skip됨)
        """
        player = game.players[player_idx]
        available = player.unplaced_colonists

        # 1. 전체 슬롯 목록 생성 (island 0-11, city 12-23)
        slots = self._build_slot_list(game, player_idx)

        # 2. 4단계 알고리즘으로 각 슬롯에 배치할 수량 결정
        allocation = self._compute_allocation(strategy, game, player_idx, slots, available)

        # 3. sequential action 시퀀스로 변환
        actions = []
        for slot in slots:
            if slot.is_empty:
                continue  # engine도 skip하므로 action 불필요
            amount = allocation.get(slot.idx, 0)
            actions.append(69 + amount)  # 69=0개, 70=1개, 71=2개, 72=3개

        return actions

    def _compute_allocation(self, strategy, game, player_idx, slots, available):
        """upstream의 4단계 알고리즘을 배치 계획으로 변환"""
        allocation = {}
        remaining = available

        # Step 1: Large VP buildings
        for bt in self.LARGE_VP_BUILDINGS:
            if remaining <= 0: break
            slot = self._find_city_slot(slots, bt, unfilled=True)
            if slot:
                fill = min(slot.capacity - slot.colonists, remaining)
                allocation[slot.idx] = fill
                remaining -= fill

        # Step 2: Strategy-specific buildings
        for bt in self.STRATEGY_BUILDINGS[strategy]:
            if remaining <= 0: break
            slot = self._find_city_slot(slots, bt, unfilled=True)
            if slot:
                fill = min(slot.capacity - slot.colonists, remaining)
                allocation[slot.idx] = fill
                remaining -= fill

        # Step 3: Production pairs (Good value order)
        for good in self.GOOD_VALUE_ORDER:
            if remaining <= 0: break
            # ... min(farms, building_capacity) 로직

        # Step 4: Remaining → other buildings → other farms
        # ...

        return allocation
```

### 4.3 adapter가 보장해야 할 것

1. **upstream strategy와 동일한 결과** — 같은 보드 상태에서 같은 strategy를 고르면 upstream의 `action_mayor_strategy()`와 동일한 최종 배치
2. **sequential action 정합성** — 생성된 action sequence를 engine에 순차 적용하면 에러 없이 Mayor phase 완료
3. **결정적(deterministic)** — 같은 입력이면 항상 같은 출력

### 4.4 adapter가 책임지지 않는 것

- 인간 플레이어의 Mayor 처리 (기존 mayor_orchestrator가 담당)
- engine 내부 Mayor 로직 수정
- action space 변경

---

## 5. bot_service 연동 변경

### 5.1 현재 봇 Mayor 흐름

```
bot_service.get_action()
  → agent_wrapper.act(obs, mask)
  → action (69-72 중 하나)
  → game_service.process_action(action)
  → engine.action_mayor_place(player_idx, amount)
  → mayor_placement_idx 전진
  → (반복) 다시 get_action() 호출
```

봇이 슬롯 수만큼 action을 반복해야 하므로 비효율적.

### 5.2 변경 후 봇 Mayor 흐름

```
bot_service.get_action()
  → agent_wrapper.act(obs, mask)
  → action 69/70/71 (strategy 선택)
  → MayorStrategyAdapter.expand(strategy, game, player_idx)
  → [69, 69, 70, 69, 71, ...] (sequential action list)
  → game_service에 batch apply
  → engine이 sequential로 처리
  → Mayor turn 완료
```

봇은 한 번의 추론으로 Mayor 전체 turn을 처리.

### 5.3 변경 필요 파일

| 파일 | 변경 내용 |
|------|----------|
| `bot_service.py` | Mayor phase일 때 adapter 경유 로직 추가 |
| `game_service.py` | batch action apply 메서드 추가 (또는 기존 process_action 반복 호출) |
| `agent_registry.py` | 새 agent 타입 등록 |

### 5.4 변경 불필요 파일 (인간 경로)

| 파일 | 이유 |
|------|------|
| `mayor_orchestrator.py` | 인간 전용, 불변 |
| `state_serializer.py` | sequential 유지이므로 mayor_slot_idx 등 그대로 |
| `action_translator.py` | Mayor 외 action 매핑 동일 |
| `frontend/*` | Mayor UI 불변 |
| `contract.md 9절` | mayor-distribute API 불변 |

---

## 6. Upstream 코드 동기화 전략

### 6.1 PuCo_RL/ 안에서 유지할 차이점

upstream과 달라지는 파일 목록 (최소화 목표):

| 파일 | 차이 내용 | 이유 |
|------|----------|------|
| `env/engine.py` | `action_mayor_place()` 유지, `action_mayor_strategy()` 미포함 | sequential Mayor 유지 |
| `env/pr_env.py` | Mayor action 69-72 유지, `mayor_slot_idx` obs 유지, auto-action/use_pbrs 미포함 | 기존 action space + 인간 UX |
| `configs/constants.py` | `MayorStrategy` enum 추가 (adapter용), 나머지 상수도 추가 | adapter가 참조 |

### 6.2 팀원에게 설명할 변경 요약

> "upstream의 env/engine/pr_env 코드를 거의 그대로 가져오되, Mayor 부분만 기존 sequential 방식을 유지합니다. 이유는 인간 플레이어의 slot-by-slot UI가 그대로 동작해야 하고, 봇 학습 효율 문제는 MayorStrategyAdapter로 해결합니다. upstream에서 추가된 MayorStrategy 상수, rule-based agents, league 스크립트 등은 그대로 가져옵니다."

### 6.3 차후 upstream sync 시 diff 관리

upstream이 Mayor 외 영역을 수정하면 → 그대로 반영 가능
upstream이 Mayor 영역을 수정하면 → adapter 로직만 업데이트, 엔진 Mayor는 sequential 유지

---

## 7. 새 모델 호환성 점검

### 7.1 봇이 새 모델을 쓸 때 확인 필요 사항

| 항목 | 확인 내용 | 위험 |
|------|----------|------|
| obs_dim | 새 모델이 기대하는 obs shape vs 우리 env의 obs shape | HIGH — mayor_slot_idx 추가, potential 확장으로 차이 가능 |
| action_dim | 새 모델이 200 action space를 기대하는지 | MEDIUM — Mayor 69-71 vs 69-72 차이 |
| Mayor action mask | 새 모델은 69-71만 valid 기대, 우리 env는 69-72 valid | HIGH — mask 불일치 시 봇 행동 오류 |
| Hacienda handling | 새 모델은 Hacienda auto 기대, 우리는 manual | MEDIUM |
| PBRS 유무 | 새 모델이 use_pbrs=False로 학습됐을 수 있음 | LOW — 추론 시에는 reward 무관 |

### 7.2 obs shape 호환 방안

두 가지 접근 가능:

**A. 우리 env의 obs를 upstream shape으로 변환** (bot_service에서)
- `mayor_slot_idx` 제거
- potential 차이는 추론에 영향 없음 (obs에 포함 안 됨)

**B. 새 모델을 우리 env에 맞춰 재학습**
- 가장 깨끗하지만 시간 소요

→ 새 모델의 실제 obs 요구사항을 측정한 후 결정

### 7.3 action mask 호환 방안

봇 Mayor turn에서:
- 새 모델은 action 69-71 중 하나를 선택
- 우리 env의 mask는 69-72가 valid
- **bot_service에서 Mayor phase일 때 mask를 69-71만 valid로 변환**하여 모델에 전달
- 모델이 69/70/71 중 선택 → adapter가 sequential expansion

### 7.4 strategy→sequential 결과 검증

adapter가 올바르게 동작하는지 확인하는 방법:

```python
# 검증 테스트 pseudo-code
def test_strategy_expansion_matches_upstream():
    # 1. 동일한 게임 상태 생성
    game_state = create_test_game_at_mayor_phase()

    # 2. upstream: strategy 직접 적용
    upstream_result = upstream_engine.action_mayor_strategy(player_idx, strategy=0)

    # 3. adapter: strategy → sequential expansion → sequential 적용
    actions = adapter.expand(strategy=0, game, player_idx)
    for action in actions:
        our_engine.action_mayor_place(player_idx, action - 69)

    # 4. 최종 배치 비교
    assert our_engine.players[player_idx].island_board == upstream_result.island_board
    assert our_engine.players[player_idx].city_board == upstream_result.city_board
```

---

## 8. auto-action / PBRS / Hacienda 처리

### 8.1 auto-action

**결정**: 현재는 도입하지 않음

이유:
- 인간 플레이어에게 "선택지가 1개여도 직접 클릭" 경험이 더 자연스러움
- step count 변경으로 인한 replay/JSONL 호환성 문제 회피
- 봇은 이미 빠르게 응답하므로 auto-action의 이점이 제한적

차후 도입 시: wrapper level에서 봇 전용으로만 적용 가능

### 8.2 PBRS 토글

**결정**: `use_pbrs` 파라미터를 env에 추가하되, 기본값 True 유지

이유:
- 새 모델이 PBRS off로 학습됐을 수 있으므로 옵션은 열어둠
- 서빙 환경에서는 reward가 직접 사용되지 않으므로 True/False 무관
- 하지만 학습 파이프라인에서 필요할 수 있음

→ 이건 upstream 코드를 가져올 때 자연스럽게 포함됨

### 8.3 Hacienda

**결정**: 수동 유지 (현재 로컬 그대로)

이유:
- 인간에게 선택권 유지
- 봇은 어차피 action 105를 mask에서 보고 선택 가능

---

## 9. 단계별 실행 계획

### Phase 0: 사전 측정 (코드 변경 없음)

- [ ] upstream env에서 `PuertoRicoEnv` 생성 → obs shape 측정
- [ ] 새 모델의 기대 obs_dim / action_dim 확인
- [ ] obs shape 차이 목록 확정 (mayor_slot_idx, unplaced_colonists 범위 등)
- [ ] strategy→sequential 변환 검증 테스트 시나리오 3개 이상 설계

### Phase 1: MayorStrategyAdapter 구현 (TDD)

**RED**:
```
test_adapter_captain_focus_produces_correct_placement.py
test_adapter_trade_factory_focus_produces_correct_placement.py
test_adapter_building_focus_produces_correct_placement.py
test_adapter_result_matches_upstream_strategy.py
test_adapter_returns_valid_sequential_actions.py
test_adapter_handles_no_colonists.py
test_adapter_handles_full_board.py
```

**GREEN**:
- `backend/app/services/mayor_strategy_adapter.py` 구현
- upstream의 4단계 알고리즘을 배치 계획으로 변환하는 로직

**REFACTOR**:
- 상수를 configs에서 가져오도록 정리

### Phase 2: bot_service Mayor 연동

**RED**:
```
test_bot_mayor_uses_adapter_for_strategy_action.py
test_bot_mayor_mask_shows_69_71_only.py
test_bot_mayor_completes_in_one_inference.py
test_mixed_game_human_sequential_bot_strategy.py
```

**GREEN**:
- `bot_service.py`에 Mayor phase 분기 로직 추가
- Mayor phase일 때 mask를 69-71로 제한 → 모델 추론 → adapter expansion → sequential apply

### Phase 3: Upstream 코드 동기화

- [ ] `configs/constants.py` — MayorStrategy enum, 새 상수 추가
- [ ] `agents/` — rule-based agents 가져오기
- [ ] `evaluate/`, `report/`, `web/` — upstream mirror
- [ ] `train/` — 개선된 training script
- [ ] `env/engine.py` — Mayor 외 변경사항 반영 (Mayor는 sequential 유지)
- [ ] `env/pr_env.py` — Mayor 외 변경사항 반영, use_pbrs 추가 가능
- [ ] sync 기준 commit hash 문서화

### Phase 4: Agent Registry 확장

- [ ] `agent_registry.py` — rule_based, advanced_rule_based 등 등록
- [ ] `model_registry.py` — checkpoint 없는 agent 로딩 경로
- [ ] `/api/bot-types` — 새 타입 노출
- [ ] `games.model_versions` — rule-based snapshot 형식

### Phase 5: 테스트 정비

- [ ] wrapper compatibility test — adapter 검증
- [ ] application contract test — contract.md 계약 불변 검증
- [ ] 기존 43+ 테스트 전체 통과 확인
- [ ] frontend vitest 통과

### Phase 6: 문서 갱신

- [ ] contract.md — 봇 Mayor adapter 관련 내용 추가
- [ ] upstream_migration_plan.md — 결과 기록

---

## 10. 에러 발생 예측

### 이 설계에서 에러가 나지 않는 곳

| 영역 | 이유 |
|------|------|
| Mayor frontend UI | 불변 |
| mayor_orchestrator | 인간 전용, 불변 |
| state_serializer (Mayor) | sequential 유지이므로 mayor_slot_idx 등 그대로 |
| action_translator (Mayor) | 69-72 의미 불변 |
| 인증/방/로비 | engine과 무관 |
| WebSocket | engine과 무관 |
| Redis/PostgreSQL 스키마 | 불변 |

### 에러 가능 지점

| 지점 | 원인 | 심각도 | 대응 |
|------|------|--------|------|
| adapter 배치 결과 불일치 | 4단계 알고리즘 구현 오류 | HIGH | upstream과 비교하는 검증 테스트로 사전 확인 |
| 봇 obs shape 불일치 | mayor_slot_idx 추가 필드, unplaced_colonists 범위 | HIGH | bot_service에서 obs 정규화 |
| 봇 action mask 불일치 | 69-72 vs 69-71 | HIGH | bot_service에서 Mayor phase mask 변환 |
| 새 agent import 실패 | rule-based agent 의존성 | MEDIUM | agent 코드 동기화 시 확인 |
| use_pbrs 파라미터 | EngineWrapper가 전달 안 하면 기본값 사용 | LOW | 기본값 True로 안전 |

### 기존 테스트 영향

| 테스트 | 영향 | 이유 |
|--------|------|------|
| Mayor 관련 4개 | 살아남음 | sequential 유지이므로 기존 assertion 유효 |
| action index 테스트 | 살아남음 | 69-72 의미 불변 |
| phase edge case 테스트 | 살아남음 | Mayor 규칙 불변 |
| bot_service 테스트 | 수정 필요 | Mayor adapter 경유 로직 추가 |

---

## 11. 미해결 질문

### 반드시 확정 필요

1. **새 모델의 obs_dim / action_dim 값은?**
   → Phase 0에서 측정

2. **새 모델이 mayor_slot_idx를 obs에서 기대하는지?**
   → upstream에는 없으므로 기대하지 않을 가능성 높음
   → 확인 후 bot_service에서 제거하고 전달

3. **potential 계산 차이가 새 모델 추론에 영향 주는지?**
   → potential은 reward에만 영향, obs에는 포함 안 됨 → 영향 없음 (확인 필요)

### Phase 진행 중 확정 가능

4. **rule-based agent의 canonical name / bot_types 응답 형식**
5. **upstream web/report 자산 활용 여부**
6. **auto-action 차후 도입 시점**

---

## 12. 검증 계획

### 단위 검증

- [ ] MayorStrategyAdapter: 3가지 strategy 각각에 대해 다양한 보드 상태에서 배치 결과 검증
- [ ] adapter 결과를 upstream `action_mayor_strategy()`와 비교 (동일 보드에서 동일 결과)
- [ ] bot_service: Mayor phase에서 adapter 경유로 한 번의 추론에 turn 완료
- [ ] bot_service: Mayor phase mask가 69-71만 valid
- [ ] mixed game: 인간(sequential) + 봇(adapter) 혼합 시 phase 정상 전환

### 통합 검증

- [ ] docker-compose up → 전체 서비스 정상 기동
- [ ] 인간 vs 봇 게임 → Mayor phase에서 인간 slot-by-slot 정상
- [ ] 봇 vs 봇 관전 → Mayor phase에서 strategy adapter 정상
- [ ] 게임 완료 → replay/JSONL 정상 기록
- [ ] `/api/bot-types` → 새 agent 타입 노출

### Regression 검증

- [ ] 기존 43+ 테스트 전체 통과
- [ ] frontend vitest 통과
- [ ] Mayor 관련 테스트 4개 통과 (sequential 유지 확인)
