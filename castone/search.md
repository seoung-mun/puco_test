# MLOps 엔지니어 분석 및 아키텍처 설계 보고서

**작성자:** MLOps Engineer (Gemini CLI)
**날짜:** 2026-04-01
**상태:** 승인 대기 (통합 설계안)
**목표:** 관측 스키마(Observation Schema) 불일치 및 런타임 예외로 인한 모든 에이전트(PPO, HPPO)의 장애 원인 분석 및 견고한 서빙 아키텍처 설계

---

## 1. 장애 현황 및 원인 분석 (Root Cause Analysis)

현재 프로덕션 환경에서 PPO 및 HPPO 봇이 정상적으로 작동하지 않으며, 공통적으로 "초기 역할 선택" 단계에서 `15(Pass)` 액션만 반환하며 게임을 고착화시키고 있습니다.

### 1.1 차원 불일치 (Schema Drift)
- **증상:** `mat1 and mat2 shapes cannot be multiplied (1x211 and 210x256)`
- **원인:** 학습 당시의 환경(210차원)과 현재 서빙 환경(211차원) 간의 불일치. 최근 추가된 `vp_chips` 필드가 알파벳 순 정렬에 의해 `global_state` 블록의 마지막(인덱스 42)에 삽입됨.
- **영향:** 레거시 PPO 뿐만 아니라 210차원 시절에 학습된 초기 HPPO 모델들 또한 모두 이 에러에 직면하여 추론이 실패함.

### 1.2 위상 인덱스 초과 (Phase Embedding Out of Bounds)
- **증상:** HPPO 모델이 추론 단계에서 크래시 발생 및 Fallback(Pass) 선택.
- **원인:** `PhasePPOAgent`의 임베딩 레이어는 9개의 클래스(`0~8`)만 허용하도록 설계됨(`nn.Embedding(9, 16)`). 그러나 `wrappers.py`와 `bot_service.py` 내부에서 페이즈 판별 실패 시 기본값(Fallback)으로 `9`를 전달함.
- **영향:** `phase_id=9`가 입력되는 즉시 `IndexError` 발생. 첫 턴(역할 선택) 등 게임 상태 초기화 직후 `current_phase` 매핑이 모호할 때 빈번히 발생함.

---

## 2. 엣지 케이스 분석 (Edge Case Scenarios)

현 아키텍처에서 발생할 수 있는 잠재적 위험 요소를 MLOps 관점에서 도출했습니다.

| 엣지 케이스 (Edge Case) | 발생 가능 상황 | 현재 결과 | 해결 방안 (Mitigation) |
| :--- | :--- | :--- | :--- |
| **차원 축소 (211 → 210)** | 210차원 모델이 211차원 입력 수신 | 행렬 연산 에러 후 Crash | **[Universal Adapter]** 입력 벡터의 `shape[-1]`을 검사하여 `idx 42`를 안전하게 제거. |
| **차원 확장 (210 → 211)** | 211차원 모델이 구형 210차원 데이터 수신 | 행렬 연산 에러 후 Crash | **[Strict Dim Guard]** 래퍼에서 `expected_dim`을 검증, 불가능한 확장이면 `RandomAgent`로 즉시 Fallback. |
| **Phase ID = 9 (Fallback)** | 게임 초기화 지연으로 `current_phase` 판독 실패 | 임베딩 인덱스 에러 (`IndexError`) | **[Phase Clamping]** 래퍼에서 `min(max(0, phase_id), 8)` 처리. 알 수 없을 땐 `8(END_ROUND/Role Select)`로 유도. |
| **모든 액션 마스킹됨 (All Zeros)** | 엔진 버그로 `valid_mask`가 모두 0 | Logit이 모두 `-1e8` → NaN 발생 | **[Mask Validator]** 래퍼에서 마스크의 합을 검사. 모두 0일 경우 엔진 기본 Pass(15) 강제 반환. |
| **의도치 않은 Tensor 형태** | 배치 차원(`unsqueeze`) 누락 | Shape 차원으로 인한 런타임 에러 | **[Tensor Sanitizer]** `act()` 도입부에서 `.dim() == 1`일 경우 `unsqueeze(0)` 강제 적용. |

---

## 3. 통합 해결 설계도 (Universal Wrapper Architecture)

모든 문제를 단일 책임 원칙(SRP)에 따라 래퍼(Wrapper) 계층에서 해결합니다. 게임 엔진(`PuCo_RL`)이나 백엔드 비즈니스 로직을 건드리지 않고, 모델 서빙 직전의 **데이터 전처리(Pre-processing)** 단계에서 방어합니다.

### 3.1 BaseWrapper 설계 (공통 데이터 정제 레이어)
중복 코드를 줄이고 모든 에이전트(PPO, HPPO)에 동일한 방어 로직을 적용하기 위해 `BasePPOWrapper`를 도입합니다.

```python
class BasePPOWrapper(AgentWrapper):
    def __init__(self, model: torch.nn.Module, device: torch.device):
        self.model = model
        self.device = device
        self.model.eval()
        self._expected_dim = self._get_expected_dim(model)

    def _sanitize_input(self, obs: torch.Tensor, mask: torch.Tensor, phase_id: int):
        # 1. Tensor Dimension Ensure
        if obs.dim() == 1: obs = obs.unsqueeze(0)
        if mask.dim() == 1: mask = mask.unsqueeze(0)

        # 2. Universal Dimensionality Adapter (Schema Drift 해결)
        if obs.shape[-1] == 211 and self._expected_dim == 210:
            obs = torch.cat([obs[..., :42], obs[..., 43:]], dim=-1)
        elif obs.shape[-1] != self._expected_dim:
            # 복구 불가능한 차원 에러
            raise ValueError(f"Obs dim mismatch: Expected {self._expected_dim}, got {obs.shape[-1]}")

        # 3. Phase ID Clamping (IndexError 방지)
        safe_phase = min(max(0, phase_id), 8)

        # 4. Mask Validation (All Zeros 방지)
        if mask.sum() == 0:
            mask[0, 15] = 1.0  # Pass 액션을 강제 활성화

        return obs.to(self.device), mask.to(self.device), safe_phase
```

### 3.2 상속 구현 (HPPO & PPO)
```python
class PPOAgentWrapper(BasePPOWrapper):
    def act(self, obs, mask, phase_id=9):
        try:
            obs, mask, safe_phase = self._sanitize_input(obs, mask, phase_id)
            phase_tensor = torch.tensor([safe_phase], device=self.device)
            
            with torch.no_grad():
                if hasattr(self.model, "phase_heads"):
                    action, *_ = self.model.get_action_and_value(obs, mask, phase_ids=phase_tensor)
                else:
                    action, *_ = self.model.get_action_and_value(obs, mask)
            return int(action.item())
        except Exception as e:
            # 최종 방어선: 에러 로그 후 무작위(Random) 선택으로 Fallback
            return RandomAgentWrapper().act(obs, mask)
```

---

## 4. 기대 효과 (Expected Outcomes)

1.  **복원력(Resilience) 극대화:** 210차원 레거시 PPO와 HPPO 모두 소스 수정 없이 즉시 정상 작동합니다.
2.  **안전성(Safety):** 잘못된 `phase_id`나 비정상적인 `mask`가 모델로 유입되는 것을 원천 차단하여 서버 크래시를 방지합니다.
3.  **유지보수성(Maintainability):** 모델별로 산재되어 있던 예외 처리 로직이 하나의 `BasePPOWrapper`로 통합되어 코드 추적이 용이해집니다.

## 주지사는 랜덤으로 배정되어야 하는데 현재 방장이 항상 주지사를 잡게 game_sevice.py 쪽에 로직이 설계되어있음 그거 수정해야함