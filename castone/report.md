# 에이전트 시스템 아키텍처 개선 및 버그 해결 설계 보고서 (TDD Edition)

**날짜:** 2026-04-01
**상태:** 최종 (MLOps & Governor Fix 통합)
**목표:** 관측 스키마 불일치 해결, 페이즈 인덱스 오류 방지, 주지사 랜덤 배정 및 TDD 기반 견고한 서빙 구조 구축

---

## 1. 이해 관계 요약 (Understanding Summary)

*   **문제 핵심:** 
    1.  **Schema Drift:** 학습(210차원)과 서빙(211차원) 환경 불일치로 PPO 모델 크래시.
    2.  **Phase ID Out of Bounds:** `phase_id=9` 입력 시 임베딩 레이어 인덱스 에러.
    3.  **Fixed Governor:** 방장이 항상 주지사가 되는 로직으로 게임 공정성 저해.
*   **해결 전략:** 
    1.  **EngineWrapper Adapter:** `PuCo_RL`을 수정하지 않고 `backend/app/engine_wrapper/wrapper.py`에서 관측값(211→210) 및 페이즈(0~8)를 정제하여 에이전트에 전달.
    2.  **Service-level Shuffle:** `GameService.start_game` 시 플레이어 리스트를 무작위로 섞어 주지사 배정을 랜덤화.
*   **제약 조건:** `PuCo_RL/` 내부 코드는 절대 수정하지 않음.

## 2. 엣지 케이스 분석 (Edge Case Analysis)

| 상황 (Scenario) | 예상되는 문제 | 대응 전략 (Strategy) |
|-----------------|---------------|----------------------|
| **211차원 관측값 수입** | 구형 모델(210차원) 추론 시 행렬 연산 에러 | `idx 42 (vp_chips)`를 제거하여 210차원으로 강제 변환 |
| **Phase ID = 9 (Fallback)** | `IndexError` 발생 | `min(max(0, phase_id), 8)` 로 클램핑하여 안전한 값 전달 |
| **플레이어 3인 미만** | 게임 시작 불가 | `start_game` 도입부에서 검증 후 예외 처리 |
| **액션 마스크 All Zeros** | 유효 액션 없음 (NaN 발생 가능) | `pass (15)` 액션을 강제로 활성화하여 세션 유지 |

---

## 3. 상세 설계 및 TDD 전략

### A. EngineWrapper 어댑터 고도화 (MLOps Fix)
*   **Test Case:** `test_observation_dim_reduction`
    *   *Goal:* 211차원 입력을 주었을 때 `get_safe_observation(210)`이 정확히 210차원을 반환하는지 확인.
*   **Test Case:** `test_phase_id_clamping`
    *   *Goal:* `phase_id=9`를 입력했을 때 `get_safe_phase_id()`가 `8`을 반환하는지 확인.

### B. 주지사 랜덤 배정 (Logic Fix)
*   **Test Case:** `test_governor_is_randomized`
    *   *Goal:* 동일한 플레이어 세트로 게임을 여러 번 시작했을 때, 주지사(0번 인덱스)가 통계적으로 고르게 배정되는지 확인.

---

## 4. 구현 계획 (Concise Planning)

- [ ] **Phase 1: EngineWrapper 강화 (MLOps Defense)**
    - [ ] `backend/app/engine_wrapper/wrapper.py` 수정: `get_safe_observation`, `get_safe_phase_id` 메서드 추가.
    - [ ] `bot_service.py`에서 위 메서드들을 호출하여 모델에 안전한 데이터 주입.
- [ ] **Phase 2: GameService 로직 수정 (Governor Fix)**
    - [ ] `backend/app/services/game_service.py`의 `start_game` 메서드에 `random.shuffle(room.players)` 적용.
    - [ ] 셔플된 플레이어 리스트가 DB와 엔진에 일관되게 반영되는지 확인.
- [ ] **Phase 3: 통합 검증 및 테스트**
    - [ ] `tests/test_agent_compatibility.py`: 차원 및 페이즈 변환 통합 테스트.
    - [ ] `tests/test_governor_randomization.py`: 주지사 무작위 배정 테스트.
    - [ ] 실제 봇전 실행을 통한 동작 확인.

---

## 5. 주요 가정 및 제약 (Assumptions & Constraints)

*   `PuCo_RL`은 외부 라이브러리로 간주하며, 모든 변환 로직은 `backend/` 영역에 국한함.
*   주지사 랜덤화는 게임의 재미와 공정성을 위해 필수적이며, 방장의 권한은 유지하되 게임 내 순서만 섞음.
*   변환 로직으로 인한 지연 시간(Latency)은 1ms 미만으로 유지함.
