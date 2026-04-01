# 에이전트 시스템 아키텍처 개선 및 버그 해결 설계 보고서 (TDD Edition)

**날짜:** 2026-04-01
**상태:** 최종 (TDD 가이드 포함)
**목표:** 에이전트 모델 아키텍처 불일치 해결 및 TDD 기반의 견고한 서빙 구조 구축

---

## 1. 이해 관계 요약 (Understanding Summary)

*   **문제 핵심:** 모델 아키텍처 불일치로 인한 봇 기능 마비 및 유지보수 어려운 구조.
*   **해결 전략:** 백엔드(Serving) 레이어에서 래퍼(Wrapper)와 팩토리(Factory)를 통해 모델을 추상화하고, MLOps 관점의 메타데이터 검증 도입.
*   **TDD 접근:** 모든 핵심 컴포넌트는 "실패하는 테스트"를 먼저 작성하여 요구사항을 정의하고 구현함.

## 2. 엣지 케이스 분석 (Edge Case Analysis)

구현 시 반드시 고려해야 할 예외 상황들입니다.

| 상황 (Scenario) | 예상되는 문제 | 대응 전략 (Strategy) |
|-----------------|---------------|----------------------|
| **메타데이터 부재** | 모델 아키텍처를 알 수 없음 | 하위 호환을 위해 `legacy_ppo`로 간주하되 경고 로그 출력 |
| **차원(Dimension) 불일치** | 가중치 로드 시 Shape mismatch 에러 | Pydantic으로 로드 전 검증, 실패 시 `RandomAgent`로 폴백 |
| **가중치 파일(.pth) 손상** | `torch.load` 실패 | 예외 캡처 후 `RandomAgent`로 폴백하여 게임 세션 유지 |
| **액션 마스크 불능** | 모든 액션이 0(유효 액션 없음)인 경우 | 엔진의 `pass` 액션(인덱스 15)을 강제 선택하거나 에러 처리 |
| **디바이스 미지원** | CUDA 설정인데 GPU가 없는 환경 | `Auto Device` 로직으로 `cpu` 자동 전환 |
| **런타임 모델 교체** | 게임 중 환경변수 변경 | 팩토리 내 싱글톤/캐싱 로직을 통해 안정적인 인스턴스 관리 |

---

## 3. 상세 설계 및 TDD 전략

### A. 모델 식별 및 로딩 (Step 1-3)
*   **Test Case:** `test_factory_returns_random_on_invalid_path`
    *   *Red:* 존재하지 않는 경로 입력 시 예외 발생.
    *   *Green:* `RandomAgentWrapper`를 반환하도록 수정.
*   **Test Case:** `test_legacy_ppo_strict_load`
    *   *Red:* 기존 `ppo_agent_update_100.pth` 로드 시 키 불일치 에러.
    *   *Green:* `LegacyPPOAgent` 클래스 구현으로 `strict=True` 성공.

### B. 액션 결정 및 인터페이스 (Step 4)
*   **Test Case:** `test_wrapper_act_respects_mask`
    *   *Red:* 마스크가 0인 인덱스를 봇이 선택함.
    *   *Green:* `act()` 내부에서 마스킹 로직(Logits manipulation) 검증.

---

## 4. 구현 계획 (Concise Planning) - [TDD FINAL]

- [ ] **Phase 1: 인프라 및 레거시 검증 (Red-Green)**
    - [ ] `backend/app/services/agents/` 디렉토리 구성.
    - [ ] `legacy_models.py` 구현 및 `ppo_agent_update_100.pth` 로드 테스트 통과.
- [ ] **Phase 2: 래퍼 및 팩토리 고도화 (Edge Case Handling)**
    - [ ] `wrappers.py` 구현: `RandomAgent` 포함 3종 래퍼 완성.
    - [ ] `factory.py` 구현: Pydantic 검증 로직 및 `Safe Loading` (폴백) 로직 추가.
    - [ ] **Model Caching:** `factory.py` 내 모델 캐싱(Singleton) 로직 구현으로 중복 로딩 방지.
    - [ ] **Advanced Logging:** 폴백 발생 시 상세 원인(Exception chain) 로깅 기능 추가.
    - [ ] **Edge Case Test:** 잘못된 JSON 형식을 주었을 때 `RandomAgent`가 나오는지 확인.


- [ ] **Phase 3: 서비스 통합 및 최종 검증**
    - [ ] `BotService` 리팩토링: `AgentFactory` 주입 및 딜레이 조정.
    - [ ] **Integration Test:** 실제 게임 루프에서 봇이 2.0s~3.0s 간격으로 유효한 액션을 수행하는지 확인.

---

## 5. 주요 가정 및 제약 (Assumptions & Constraints)

*   `RandomAgent` 폴백은 "게임이 멈추는 것보다 무작위로라도 진행되는 것이 낫다"는 원칙에 따름.
*   모든 모델 가중치는 `backend/app/engine_wrapper/models/` 또는 지정된 경로에 보관됨.
*   TDD 환경을 위해 Pytest를 사용하며, 비동기 테스트를 지원함.
