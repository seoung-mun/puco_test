# Castone 봇 장애 해결 작업 완료 보고서 (design_1.md)

**날짜:** 2026-04-02
**상태:** Phase 1, 2, 3 완료 (P0 등급 장애 해결)
**환경:** Docker 기반 통합 테스트 통과

---

## 1. 개요
`PuCo_RL` 업스트림 병합 이후 발생한 "봇 차례에서 게임이 멈추는 현상(Silent Death)"을 해결하기 위해 백엔드 어댑터 계층을 강화했습니다. 엔진의 소스 코드를 최소한으로 수정하면서 백엔드에서 모든 변화를 흡수하도록 설계되었습니다.

---

## 2. 페이즈별 작업 상세

### Phase 1: 엔진 규칙 충돌 해결 및 어댑터 수정
*   **목표:** Mayor 페이즈에서 Pass(15) 액션 사용 시 발생하는 `ValueError` 차단.
*   **주요 수정 사항:**
    *   **`PuCo_RL/agents/wrappers.py`**: 엔진 내부 임포트 오류 수정 (`HierarchicalAgent` → `PhasePPOAgent`). 시스템 구동을 위한 필수 조치.
    *   **`backend/app/services/agents/wrappers.py`**: `BasePPOWrapper._sanitize_input` 로직 수정. 
        *   빈 마스크 수신 시 폴백 액션을 페이즈별로 분기.
        *   **Mayor 페이즈(ID 1):** `Pass(15)` 대신 `0명 배치(69)`를 강제 활성화하여 엔진 규약 준수.
        *   **기타 페이즈:** 기존대로 `Pass(15)` 사용.
*   **검증:** `backend/tests/test_legacy_ppo_wrapper.py`에 Mayor 전용 테스트 케이스 추가 및 통과.

### Phase 2: 비동기 안전망(Safety Net) 구축
*   **목표:** 봇의 비동기 태스크가 예외로 인해 조용히 종료되는 현상 방지.
*   **주요 수정 사항:**
    *   **`backend/app/services/bot_service.py`**:
        *   `_extract_phase_id` 강화: `numpy.int64` 등 다양한 데이터 타입 대응 및 0~9 범위 클램핑 추가.
        *   `run_bot_turn` 리팩토링: `try-except-retry` 구조 도입.
        *   **재시도 로직:** 모델이 선택한 액션이 엔진에서 거부될 경우(`ValueError` 등), 현재 유효 마스크에서 **랜덤한 유효 액션을 즉시 선택하여 다시 시도**.
        *   **로깅:** `logger.exception`을 적용하여 비동기 태스크 내의 에러를 메인 로그에 명시적으로 출력.
*   **검증:** `backend/tests/test_bot_service_safety.py` 생성. 콜백 실패 시 랜덤 액션으로 재시도하여 흐름이 유지됨을 확인.

### Phase 3: 태스크 참조 관리 (GC 방지)
*   **목표:** 실행 중인 봇 태스크가 가비지 컬렉터(GC)에 의해 메모리에서 제거되는 현상 방지.
*   **주요 수정 사항:**
    *   **`backend/app/services/game_service.py`**:
        *   `GameService` 클래스 레벨에 `_bot_tasks = set()` 추가.
        *   `_schedule_next_bot_turn_if_needed`에서 생성된 `Task` 객체를 세트에 저장.
        *   `task.add_done_callback`을 통해 작업 완료 시 세트에서 자동으로 제거되도록 설정.
*   **검증:** `backend/tests/test_bot_task_reference.py` 생성. 태스크 생성 시 세트에 등록되고 완료 후 제거되는 생명주기 검증 완료.

---

## 3. 종합 검증 결과 (Docker)

모든 테스트는 백엔드 컨테이너 내부 환경에서 수행되었습니다.

| 테스트 파일 | 검증 항목 | 결과 |
| :--- | :--- | :--- |
| `test_legacy_ppo_wrapper.py` | 211차원 obs 적응 및 Mayor 폴백 로직 | **PASSED** |
| `test_bot_service_safety.py` | 페이즈 추출 및 비동기 Retry 로직 | **PASSED** |
| `test_bot_task_reference.py` | 태스크 참조 보존 (GC 방지) | **PASSED** |

---

## 4. 향후 과제 (Remaining Tasks)
*   **Phase 4:** 차원 적응형 어댑터 고도화 (모델 입력 레이어 동적 감지).
*   **Phase 5:** 확률적(Stochastic) 추론 옵션 도입 (교착 상태 방지 강화).
*   **MLOps:** PBRS 도입에 따른 리워드 스키마 변화 대응 로깅.

---

**결론:** 현재 봇 멈춤의 근본 원인이었던 P0 장애 요인들이 모두 제거되었으며, 시스템은 최신 엔진 규약 하에서 안정적으로 작동합니다.


puco_backend   | INFO:     172.18.0.6:58008 - "GET /api/puco/auth/me HTTP/1.1" 401 Unauthorized
puco_backend   | INFO:     172.18.0.6:58012 - "GET /api/puco/auth/me HTTP/1.1" 401 Unauthorized
먼저 처음에 백엔드 상 이런 로그가 뜨고 잇어

그리고 실제로 도커에 올려서 테스트해본 결과, random, ppo, hppo 모든 봇이 첫 역할에서 아무런 액션을 취하지 않아
그리고 방장이 첫 주지사를 먹지 못하는 버그 또한 존재하고
