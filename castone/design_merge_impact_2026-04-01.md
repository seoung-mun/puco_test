# PuCo_RL upstream2 병합 영향도 분석 및 설계 보고서

**날짜:** 2026-04-01  
**병합 커밋:** `9480f39` (Merge remote-tracking branch 'upstream2/main')  
**작성 기준:** Senior Fullstack + MLOps 관점 통합 분석  
**핵심 원칙:** PuCo_RL 내부 코드 수정 금지 — 모든 대응은 `backend/` 어댑터 계층에서 흡수

---

## 0. 핵심 수치 검증 (Ground Truth)

```
관측 공간 (3-player, 플랫 벡터 기준):
  global_state  : 43 dim (정렬된 키 순서)
    ├── cargo_ships_good   [0-2]   = 3
    ├── cargo_ships_load   [3-5]   = 3
    ├── colonists_ship     [6]     = 1
    ├── colonists_supply   [7]     = 1
    ├── current_phase      [8]     = 1
    ├── current_player     [9]     = 1
    ├── face_up_plantations[10-13] = 4
    ├── goods_supply       [14-18] = 5  ← 주의: governor_idx 위치 변경!
    ├── governor_idx       [19]    = 1
    ├── mayor_slot_idx     [20]    = 1
    ├── quarry_stack       [21]    = 1
    ├── role_doubloons     [22-29] = 8
    ├── roles_available    [30-37] = 8
    ├── trading_house      [38-41] = 4
    └── vp_chips           [42]    = 1  ← 제거 대상 (학습 모델 210-dim 기준)
  per_player (×3): 56 dim
    ├── city_buildings     = 12
    ├── city_colonists     = 12
    ├── doubloons          = 1
    ├── goods              = 5
    ├── island_occupied    = 12
    ├── island_tiles       = 12
    ├── unplaced_colonists = 1
    └── vp_chips           = 1
  
  총합: 43 + (56 × 3) = 211 dim  ← 현재 엔진 출력
  학습 모델 기대 dim: 210 (vp_chips@42 제외)
  wrappers.py의 index 42 제거: ✅ 수학적으로 올바름
```

---

## 1. 병합 변경사항 카탈로그 (What Changed)

### 1-A. 보상 함수 전면 재설계 (PBRS 도입)

**파일:** `PuCo_RL/env/pr_env.py`

**변경 전:** 게임 종료 시 승/패 단발성 리워드만 존재  
**변경 후:** 매 스텝 잠재 함수 기반 Dense Reward 추가

```python
# 기존: 게임 끝에만 리워드
# 신규: 매 스텝 PBRS (Potential-Based Reward Shaping)
SHAPING_GAMMA = 0.99
shaping_reward = (SHAPING_GAMMA * new_potential) - old_potential
```

**잠재 함수 구성요소 (_compute_potential):**

| 구성 요소 | 계수 | 설명 |
|---|---|---|
| chip_vp | ×1.0 | 보유 VP 칩 |
| building_vps | ×1.0 | 건물 기본 승점 |
| dynamic_large_vp | ×1.0 | 대형 건물 동적 보너스 |
| infrastructure_value | ×0.15/일꾼 | 배치된 일꾼 수 × 0.15 |
| doubloon_value | ×0.33×(1-progress) | 더블룬 (후반 감가상각) |
| goods_value | ×0.1/재화 | 보유 재화 |
| **전체 스케일링** | ×0.01 | Critic 폭발 방지 |

**종료 리워드:** `±1.0 (승/패) + (score_diff × 0.02)`

**조절 파라미터:** `w_ship`, `w_bldg`, `w_doub`, `potential_mode="option3"`  
`EngineWrapper`는 기본값으로 env를 생성 → **서빙 환경은 기본값 사용 중**

---

### 1-B. Mayor 페이즈 순차 배치 로직 개편

**파일:** `PuCo_RL/env/engine.py`, `PuCo_RL/env/pr_env.py`

**핵심 변경:** Mayor 페이즈가 "총량 배치" → "슬롯별 순차 배치"로 전환

```python
# engine.py line 72
self.mayor_placement_idx = 0  # 0-23 슬롯을 순서대로 순회

# pr_env.py line 211-214: 액션 69-72는 현재 슬롯에 0~3명 배치
elif 69 <= action <= 72:
    amount = action - 69
    self.game.action_mayor_place(player_idx, amount)
```

**슬롯 매핑:** 0-11 = island board, 12-23 = city board  
**마스킹 로직:** 현재 슬롯의 용량(capacity)에 따라 69~72 중 유효한 것만 true  
**Pass 불가:** Mayor 순차 배치 중 Pass(15) 시 `ValueError` 발생 (pr_env.py line 304-306)

---

### 1-C. 신규 평가 도구 추가 (Non-Breaking)

`PuCo_RL/evaluate/`, `PuCo_RL/utils/evaluation/`, `PuCo_RL/logs/replay/` 디렉토리 추가  
→ 서빙/백엔드에 영향 없음, 학습/평가 파이프라인 용도

---

## 2. MLOps 리스크 분석

### 🔴 RISK-ML-01: Reward Distribution Shift (HIGH)

**상황:** 기존 학습 데이터(`transitions_*.jsonl`)의 reward는 `{0.0, -0.5 ~ +1.0}` 범위였으나,  
병합 이후 env는 매 스텝 PBRS 리워드를 생성 → `ml_logger.py`가 기록하는 transition 데이터의 리워드 분포가 완전히 달라짐

**리스크 유형:** Target Drift  
**서빙 영향:** 없음 (모델 추론에는 reward 불사용)  
**데이터 파이프라인 영향:** 있음 — 기존 로그와 신규 로그를 동일 모델로 학습하면 안 됨

**대응 방안:**
```
[BE] ml_logger.py에 reward_type 메타데이터 필드 추가
     예: "reward_type": "pbrs_option3" | "terminal_only"
     
[데이터] data/logs/ 디렉토리에 pre_merge / post_merge 구분 보관
```

---

### 🔴 RISK-ML-02: Model Load Integrity — ResidualAgent (HIGH)

**상황:** `ppo_agent.py`의 `Agent` 클래스는 이제 `ResidualBlock`(LayerNorm+2×Linear) 기반  
기존 학습 모델(`.pth`)이 구 아키텍처로 학습됐다면 `strict=True` 로드 시 `RuntimeError` 발생

**현재 factory.py 코드:**
```python
from agents.ppo_agent import Agent as ResidualAgent, PhasePPOAgent
model = ResidualAgent(obs_dim, action_dim, hidden_dim=512)
model.load_state_dict(state_dict, strict=True)  # 아키텍처 불일치 시 폭발
```

**체크 포인트:** 현재 `ppo_agent_update_100.pth`가 어떤 아키텍처로 학습됐는지 확인 필요

**대응 방안:**
```python
# factory.py 방어 코드 추가
try:
    model.load_state_dict(state_dict, strict=True)
except RuntimeError as e:
    logger.warning(f"Strict load failed ({e}), falling back to RandomAgentWrapper")
    return RandomAgentWrapper()
```

---

### 🟡 RISK-ML-03: Mayor Phase Masking 행동 분포 변화 (MEDIUM)

**상황:** Mayor 페이즈가 순차 배치로 변경 → 유효 액션 분포가 좁아짐  
기존 모델은 Mayor 페이즈를 비순차적으로 학습 → 현재 마스크와 학습 분포 불일치

**서빙 영향:** wrappers.py의 빈 마스크 폴백(Pass=15 강제 활성화)이 Mayor에선 `ValueError`  
→ `bot_service.py`에서 Mayor 페이즈 에러 시 게임이 Deadlock될 수 있음

**대응 방안 (상세는 섹션 3-C):**
```python
# wrappers.py: Mayor 페이즈에서 빈 마스크 시 Pass 강제 금지
# bot_service.py: Mayor 액션 실패 시 valid_actions[0] 폴백 추가
```

---

### 🟢 RISK-ML-04: Observation Dimension 검증 (LOW — 이미 정상)

**검증 결과:** 병합 후에도 관측 차원 = **211** (3-player 기준)  
`wrappers.py`의 index 42 제거 로직은 수학적으로 **정확** (vp_chips = sorted key 기준 마지막)  
별도 수정 불필요

---

## 3. Backend 리스크 분석

### 🔴 RISK-BE-01: Mayor 페이즈 Pass 처리 충돌 (CRITICAL)

**현재 wrappers.py (line 66-69):**
```python
if mask.sum() == 0:
    logger.warning("Empty action mask received. Forcing 'Pass' (15)")
    mask[0, 15] = 1.0  # ← Mayor 순차 배치 중엔 Pass가 ValueError!
```

**pr_env.py (line 304-306):**
```python
# Mayor sequential placement doesn't use Pass action.
raise ValueError("Cannot pass in Mayor phase sequential placement.")
```

**충돌 경로:**
```
빈 마스크 → Pass(15) 강제 → bot_service.process_action(15) →
engine.step() → _handle_pass() → ValueError → 게임 Deadlock
```

**해결 설계:**
```python
# wrappers.py _sanitize_input 수정
if mask.sum() == 0:
    phase_id = safe_phase  # 현재 페이즈 확인
    if phase_id == 1:  # Phase.MAYOR
        # Mayor: 강제 배치 - valid_action_mask에서 69-72 중 하나 선택
        mayor_actions = [69, 70, 71, 72]
        for a in mayor_actions:
            mask[0, a] = 1.0
            break  # 최소 1개 활성화
    else:
        mask[0, 15] = 1.0  # 기존 Pass 폴백
```

---

### 🟡 RISK-BE-02: EngineWrapper — mayor_slot_idx 직렬화 누락 (MEDIUM)

**현재 state_serializer.py:** `mayor_slot_idx` 필드를 `meta` 또는 `common_board`에 포함하는지 확인 필요  
`engine.mayor_placement_idx`가 증가하는 동안 프론트가 현재 슬롯을 알 수 없으면  
Mayor UI가 어느 슬롯에 배치 중인지 표시 불가 → 플레이어 혼란

**해결 설계:**
```python
# state_serializer.py build_meta() 또는 phase_context에 추가
"mayor_context": {
    "slot_idx": game.mayor_placement_idx,   # 0-23 현재 슬롯
    "is_island_slot": game.mayor_placement_idx < 12,
    "slot_capacity": engine._mayor_slot_capacity(current_player_idx, game.mayor_placement_idx)
}
```

---

### 🟡 RISK-BE-03: PBRS 파라미터 - EngineWrapper 기본값 고정 (MEDIUM)

**현재 EngineWrapper (wrapper.py):**
```python
self.env = PuertoRicoEnv(num_players=num_players)
# w_ship, w_bldg, w_doub, potential_mode 미전달 → 기본값 사용
```

**리스크:** 학습 환경(`potential_mode="option3"`)과 서빙 환경이 동일 기본값을 쓰는지 보장 필요  
서빙에서는 reward 계산이 이루어지지만(step() 내부에서), 이 값이 게임 승패에 영향을 주지 않으므로  
**기능적 리스크는 낮음** — 그러나 전환 로그 기록 시 reward 값이 학습 환경과 다를 수 있음

**대응:** `EngineWrapper.__init__`에 명시적 파라미터 전달 옵션 노출 (선택적)

---

### 🟡 RISK-BE-04: ml_logger 전환 데이터 reward 타입 혼재 (MEDIUM)

**현재 ml_logger.py:** reward를 그대로 float로 저장  
병합 전후 데이터가 서로 다른 reward 분포를 가져 학습 시 혼재 위험

**해결 설계:**
```python
# ml_logger.py 전환 데이터 스키마에 필드 추가
{
    "reward": float,
    "reward_schema": "pbrs_v1",  # NEW: 버전 태깅
    "game_progress": float,      # NEW: PBRS 계산에 사용된 게임 진행도
}
```

---

## 4. Frontend 리스크 분석

### 🟡 RISK-FE-01: Mayor 순차 배치 UI 상태 부재 (MEDIUM)

**현재 gameState.ts:** `mayor_slot_idx?: number` 필드 있음  
**문제:** `mayor_context` (current slot, capacity) 데이터가 없어 UI가  
"지금 몇 번 슬롯에 몇 명까지 배치 가능한가"를 알 수 없음

**해결:** 백엔드 serializer에서 `mayor_context` 추가 후 타입 정의 확장
```typescript
// gameState.ts 추가
mayor_context?: {
  slot_idx: number;       // 현재 배치 중인 슬롯 (0-23)
  is_island_slot: boolean;
  slot_capacity: number;  // 해당 슬롯에 최대 배치 가능 인원
};
```

---

### 🟢 RISK-FE-02: 기존 타입 호환성 (LOW — 이상 없음)

`vp_chips`, `colonists`, `action_mask`, 페이즈명 등 기존 필드는 변경 없음  
TypeScript 컴파일 오류 없을 것으로 예상

---

## 5. TDD 구현 전략 (Test-Driven Development)

### Phase 1: Mayor Pass 충돌 수정 (CRITICAL 우선)

**RED 단계 — 실패 테스트 작성:**
```python
# backend/tests/test_mayor_sequential_bot.py

def test_bot_does_not_pass_in_mayor_phase():
    """Mayor 순차 배치 중 Pass(15) 액션을 선택하지 않는다."""
    wrapper = create_ppo_wrapper_with_mock_model()
    obs = make_211_dim_obs()
    # Mayor 페이즈 마스크: 오직 action 70만 유효
    mask = [0] * 200
    mask[70] = 1
    action = wrapper.act(obs, mask, phase_id=1)  # phase_id=1 = Mayor
    assert action == 70
    assert action != 15

def test_empty_mayor_mask_fallback_uses_mayor_actions():
    """Mayor 페이즈에서 빈 마스크 수신 시 Pass 대신 Mayor 액션(69-72) 폴백."""
    wrapper = create_ppo_wrapper_with_mock_model()
    obs = make_211_dim_obs()
    mask = [0] * 200  # 완전 빈 마스크
    action = wrapper.act(obs, mask, phase_id=1)
    assert 69 <= action <= 72  # Mayor 액션 범위
    assert action != 15        # Pass 절대 금지
```

**GREEN 단계 — 최소 구현:**
```python
# wrappers.py BasePPOWrapper._sanitize_input 수정
if mask.sum() == 0:
    if safe_phase == 1:  # Phase.MAYOR
        for a in [69, 70, 71, 72]:
            mask[0, a] = 1.0
            break
    else:
        mask[0, 15] = 1.0
```

---

### Phase 2: factory.py 방어적 모델 로딩 (HIGH 우선)

**RED 단계:**
```python
# backend/tests/test_agent_compatibility.py 추가

def test_factory_falls_back_on_architecture_mismatch():
    """아키텍처 불일치 시 RandomAgentWrapper로 폴백한다."""
    # 잘못된 obs_dim으로 저장된 체크포인트 시뮬레이션
    bad_checkpoint = {"model_state_dict": {}}  # 빈 state_dict
    with patch("torch.load", return_value=bad_checkpoint):
        agent = AgentFactory.get_agent("nonexistent_path.pth")
    assert isinstance(agent, RandomAgentWrapper)

def test_factory_logs_warning_on_strict_load_failure():
    """strict load 실패 시 경고 로그를 남긴다."""
    with patch("backend.app.services.agents.factory.logger") as mock_log:
        # ... 아키텍처 불일치 로드 유도
        mock_log.warning.assert_called_once()
```

**GREEN 단계:**
```python
# factory.py _create_agent 수정
try:
    model.load_state_dict(state_dict, strict=True)
except RuntimeError as e:
    logger.warning(f"[AgentFactory] strict load failed: {e}. Falling back to Random.")
    return RandomAgentWrapper()
```

---

### Phase 3: ml_logger reward 스키마 버전 태깅 (MEDIUM)

**RED 단계:**
```python
# backend/tests/test_ml_logger.py 추가

def test_transition_log_includes_reward_schema():
    """전환 로그에 reward_schema 필드가 포함된다."""
    log_entry = ml_logger.build_transition_entry(
        obs=..., action=..., reward=0.15, next_obs=...
    )
    assert "reward_schema" in log_entry
    assert log_entry["reward_schema"] == "pbrs_v1"
```

---

### Phase 4: mayor_context 직렬화 (MEDIUM)

**RED 단계:**
```python
# backend/tests/test_state_serializer_action_index.py 추가

def test_serialized_state_includes_mayor_context_during_mayor_phase():
    """Mayor 페이즈 중 직렬화된 상태에 mayor_context 필드가 포함된다."""
    engine = create_engine_at_mayor_phase()
    state = state_serializer.build_state(engine)
    assert "mayor_context" in state["meta"]
    assert "slot_idx" in state["meta"]["mayor_context"]
    assert "slot_capacity" in state["meta"]["mayor_context"]
```

---

## 6. 구현 우선순위 및 체크리스트

```
[P0 - CRITICAL, 즉시 수정]
  □ wrappers.py: Mayor 페이즈에서 Pass 폴백 제거 → 69-72 범위 폴백
  □ factory.py: strict load 실패 시 graceful fallback + 경고 로그

[P1 - HIGH, 이번 스프린트]
  □ backend/tests/test_mayor_sequential_bot.py: TDD 테스트 작성 후 수정
  □ backend/tests/test_agent_compatibility.py: 아키텍처 불일치 테스트 추가
  □ state_serializer.py: mayor_context 필드 추가
  □ frontend/src/types/gameState.ts: mayor_context 타입 추가

[P2 - MEDIUM, 다음 스프린트]
  □ ml_logger.py: reward_schema 버전 태깅 ("pbrs_v1")
  □ data/logs/: pre_merge / post_merge 구분 디렉토리 정리
  □ EngineWrapper: PBRS 파라미터 명시적 전달 옵션 노출

[P3 - LOW, 백로그]
  □ 4-player 게임 지원 시 obs_dim 동적 계산 (현재 3-player 고정)
  □ PBRS 파라미터 서빙 환경 설정 파일 관리
```

---

## 7. 주요 가정 및 불변 조건

| 가정 | 근거 |
|---|---|
| 게임은 항상 3-player | EngineWrapper 기본값, 현재 게임 서비스 로직 |
| obs_dim = 211이 서빙 표준 | 수학적 검증 완료 (43 global + 56×3 player) |
| index 42 = vp_chips | sorted key 기준 정렬 검증, 제거 로직 유효 |
| Phase ID 범위 0-8 | 병합 후에도 동일 (9 phases), 클램핑 로직 유효 |
| PuCo_RL 내부 수정 금지 | 모든 어댑터는 backend/에서 처리 |

---

## 8. 검증 체크리스트 (병합 후 확인)

```
통합 검증:
  □ pytest backend/tests/ -v --tb=short  → 전체 통과
  □ 봇전 1게임 완주 (Mayor 페이즈 포함)
  □ Mayor 페이즈에서 ValueError 미발생 확인
  □ ml_logger reward 값 범위 확인 (PBRS: [-0.5, +1.5] 예상)

MLOps 검증:
  □ AgentFactory: legacy_ppo, ppo, phase_ppo 세 타입 로드 성공
  □ LegacyPPOAgent 추론: 211 obs → index 42 제거 → 210 → 정상 추론
  □ 전환 로그 샘플 10개 reward_schema 필드 포함 여부

Frontend 검증:
  □ TypeScript 컴파일 에러 없음
  □ Mayor 페이즈 진입 시 mayor_context 수신 확인 (콘솔 로그)
```
