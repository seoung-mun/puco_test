# Engine-First Cutover Task Breakdown

작성일: 2026-04-08  
기준 문서: `design/2026-04-08_error_log_driven_design_report.md`

## 제한 사항

- test는 docker에서 진행할 것
- red 테스트를 할때, import 에러 같은 간단한 상태 오류를 하지말고
- 단순한 존재 확인이나 구문 에러가 아닌, **비즈니스 핵심 규칙과 예외 상황(Edge Case)을 검증하는 유의미한 실패 테스트(Red)
- 코드의 구현 확인이 아니라 기능 명세를 정의하는 관점에서, 다양한 입력값에 대한 기대 동작을 담은 Red 테스트부터 단계별로 보여줘.


## 1. 목적

이 문서는 위 설계 보고서를 실제 실행 가능한 task 단위로 쪼갠 backlog다.

핵심 원칙:
- `PuCo_RL` upstream를 먼저 canonical engine으로 고정한다.
- backend/frontend는 그 엔진 계약에 맞춘 wrapper와 UI로 정렬한다.
- human Mayor도 bot과 동일하게 strategy-first로 전환한다.
- legacy Mayor 파일/계약은 남기지 않는다.
- 각 단계는 독립적으로 테스트 가능해야 한다.

이 계획은 기존 `design/task_status_detailed.md`의 dual-mode Mayor 전제를 대체한다.

---

## 2. 전체 순서

```text
P0 연결관계 맵 작성
 -> P1 upstream 반영 및 PuCo_RL 고정
 -> P2 contract 재정의
 -> P3 backend wrapper 컷오버
 -> P4 frontend human Mayor strategy UI 전환
 -> P5 MLOps/평가 게이트 추가
 -> P6 cleanup/refactor
 -> P7 최종 검증 및 문서 정리
```

병렬 가능 구간:
- `P3` 일부 backend 정리와 `P4` 프론트 UI 전환은 contract가 고정된 뒤 병렬 가능
- `P5` MLOps gate는 backend contract가 안정된 뒤 병렬 가능

---

## 3. 작업 단위 정의

각 task는 다음 조건을 만족해야 한다.

- 하나의 명확한 산출물이 있다.
- 완료/미완료를 테스트나 diff로 구분할 수 있다.
- 실패 시 rollback 범위가 작다.
- 다음 task의 입력으로 쓰일 수 있다.

상태 표기:
- `TODO`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

---

## 4. Phase 0 — 연결관계 맵 작성

목표: upstream 반영 전에 현재 코드가 `PuCo_RL`에 어디까지 직접 묶여 있는지 명시한다.

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P0-T1 | DONE | backend direct import inventory 작성 | `backend/app`, `backend/tests`의 `PuCo_RL` 직접 import 목록 | 없음 | `design/2026-04-08_engine_cutover_phase0_map.md`에 direct import / path coupling 목록 정리 |
| P0-T2 | DONE | frontend action/phase coupling inventory 작성 | `frontend/src/App.tsx`, 타입, Mayor UI 의존점 목록 | 없음 | `design/2026-04-08_engine_cutover_phase0_map.md`에 action index/phase/meta coupling 정리 |
| P0-T3 | DONE | breakage matrix 작성 | upstream 교체 시 깨질 가능성이 높은 파일 우선순위표 | P0-T1, P0-T2 | `design/2026-04-08_engine_cutover_phase0_map.md`에 backend/frontend/테스트 우선순위표 정리 |
| P0-T4 | DONE | cutover contract freeze 문서 작성 | Mayor, action space, GameState 최소 계약 요약 | P0-T1, P0-T2 | `design/2026-04-08_engine_cutover_phase0_map.md`에 유지 계약/변경 계약 분리 |

추천 출력 위치:
- `design/2026-04-08_engine_cutover_phase0_map.md`

---

## 5. Phase 1 — upstream 반영 및 `PuCo_RL` 고정

목표: `PuCo_RL`을 upstream 기준 canonical engine으로 확정한다.

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P1-T1 | DONE | `initial import` 기준점 확인 | 기준 커밋 해시와 rollback 절차 메모 | P0-T3 | `design/2026-04-08_engine_cutover_phase1_lock.md`에 rollback anchor와 절차 메모 고정 |
| P1-T2 | DONE | upstream mirror 반영 | 최신 upstream 내용이 `PuCo_RL`에 반영된 작업 트리 | P1-T1 | `design/2026-04-08_engine_cutover_phase1_lock.md`에 overlay 범위와 보존 local delta 정리 |
| P1-T3 | DONE | `PuCo_RL` read-only 규칙 명시 | 문서/리뷰 규칙/작업 원칙 | P1-T2 | `design/2026-04-08_engine_cutover_phase1_lock.md`에 read-only 규칙 문서화 |
| P1-T4 | DONE | engine import smoke test | 최소 import/engine create/step smoke 결과 | P1-T2 | `design/2026-04-08_engine_cutover_phase1_lock.md`에 docker smoke 결과 기록 |
| P1-T5 | DONE | upstream 버전 fingerprint 기록 | upstream commit, branch, source URL 기록 | P1-T2 | `design/2026-04-08_engine_cutover_phase1_lock.md`에 source URL/branch/commit 고정 |

주의:
- 이 단계에서는 backend/frontend를 크게 만지지 않는다.
- 먼저 엔진 기준점만 고정한다.

---

## 6. Phase 2 — 계약 재정의

목표: 코드 수정 전에 “무엇이 바뀌는지”를 문서와 테스트 이름으로 먼저 고정한다.

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P2-T1 | DONE | `contract.md` Mayor 계약 업데이트 | strategy-first Mayor contract | P1-T2 | human/bot 공통 Mayor strategy contract가 문서에 반영됨 |
| P2-T2 | DONE | action space 문서 갱신 | supported action ranges와 의미 재정의 | P1-T2 | sequential Mayor range 설명이 제거됨 |
| P2-T3 | DONE | serializer/meta 필수 필드 재정의 | 프론트가 의존할 최소 meta 필드 표 | P2-T1 | `design/2026-04-08_engine_cutover_phase2_contract_followup.md`에 최소 meta/serializer 계약이 정리됨 |
| P2-T4 | DONE | 테스트 rename/삭제 계획 작성 | legacy test 제거 목록과 대체 테스트 목록 | P2-T1, P2-T2 | `design/2026-04-08_engine_cutover_phase2_contract_followup.md`에 삭제/대체 테스트가 명시됨 |

핵심 결정:
- `mayor-distribute` bulk sequential contract는 유지하지 않는다.
- `mayor_slot_idx`는 프론트 정식 계약에서 제거한다.

---

## 7. Phase 3 — backend wrapper 컷오버

목표: backend가 더 이상 sequential Mayor나 `PuCo_RL` 내부 구현 세부사항에 흩어져 의존하지 않게 만든다.

### P3-A. 통합 경계 만들기

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P3-T1 | DONE | `engine_gateway` 패키지 생성 | `backend/app/services/engine_gateway/` 또는 동등 패키지 | P1-T2 | 엔진 관련 import의 새 집합점이 생김 |
| P3-T2 | DONE | `create_game_engine` 경로 정리 | wrapper가 upstream engine 기준으로 동작 | P3-T1 | 엔진 생성 경로가 한 파일로 수렴함 |
| P3-T3 | DONE | PuCo direct import 이동 | 서비스/API의 `configs/constants`, `env.*`, `agents.*` 직접 import 축소 | P3-T1 | active backend app code의 direct import가 gateway/wrapper/legacy 바깥에서 제거됨 |

### P3-B. Mayor 컷오버

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P3-T4 | DONE | sequential Mayor endpoint 제거 | `mayor_orchestrator.py`, 관련 route 제거 또는 비활성화 | P2-T1 | backend public contract에서 sequential Mayor가 사라짐 |
| P3-T5 | DONE | `game_service.py` Mayor flow 정리 | human/bot 모두 strategy action 처리 | P3-T4 | Mayor 처리 경로가 단일 action 기반으로 동작함 |
| P3-T6 | DONE | `bot_service.py` Mayor special-case 정리 | strategy action only 처리 | P3-T5 | bot Mayor가 adapter 없이 canonical engine action `69-71`만 사용함 |
| P3-T7 | DONE | `state_serializer.py` Mayor meta 정리 | strategy-first UI에 필요한 데이터만 노출 | P3-T5 | `mayor_slot_idx`, pending sequential 정보 제거 또는 deprecated 제거 완료 |
| P3-T8 | DONE | `action_translator.py` 정리 | sequential Mayor 번역 코드 제거 | P3-T5 | Mayor 관련 helper가 strategy-only 의미를 갖게 됨 |

### P3-C. backend 테스트 갱신

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P3-T9 | DONE | Mayor contract 테스트 추가 | `backend/tests/test_mayor_strategy_contract.py` | P3-T5, P3-T7 | human/bot 공통 strategy contract가 RED-GREEN으로 검증됨 |
| P3-T10 | DONE | legacy Mayor 테스트 삭제/교체 | obsolete tests 제거, 대체 tests 추가 | P2-T4, P3-T9 | legacy Mayor 테스트 삭제와 strategy contract 대체 테스트가 반영됨 |
| P3-T11 | DONE | import-guard 테스트 추가 | backend non-gateway direct import 금지 테스트 | P3-T3 | `backend/tests/test_engine_gateway_import_guard.py`가 허용 위치 밖 direct import를 차단함 |

---

## 8. Phase 4 — frontend human Mayor strategy UI 전환

목표: 사람 플레이어도 Mayor phase에서 strategy choice를 하도록 UI와 상태 관리를 바꾼다.

### P4-A. 상태/타입 정리

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P4-T1 | DONE | `GameState` 타입 갱신 | strategy-first Mayor 관련 타입 | P2-T3, P3-T7 | 프론트 타입이 sequential Mayor meta를 더 이상 요구하지 않음 |
| P4-T2 | DONE | `App.tsx` Mayor local state 제거 | `mayorPending`, slot toggle 상태 제거 | P4-T1 | 프론트 로컬 상태에 sequential Mayor 분배 로직이 남아 있지 않음 |
| P4-T3 | DONE | auth bootstrap 분리 시작 | `bootstrapAuth` / `AuthGate` 골격 | P2-T3 | `useAuthBootstrap`와 `AppScreenGate`로 auth bootstrap이 분리됨 |

### P4-B. Mayor UI 구현

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P4-T4 | DONE | `MayorStrategyPanel` 컴포넌트 구현 | strategy 카드/버튼 UI | P4-T1 | 3개 전략 선택 UI가 렌더됨 |
| P4-T5 | DONE | strategy preview 표시 | 전략 설명/예상 배치 프리뷰 | P4-T4, P3-T7 | 사용자에게 선택 근거가 보임 |
| P4-T6 | DONE | action dispatch 연결 | 선택 시 backend에 strategy action 1회 전송 | P4-T4, P3-T5 | human Mayor action이 단일 strategy action으로 전송됨 |
| P4-T7 | DONE | legacy Mayor UI 제거 | slot-by-slot 버튼/토글 UI 삭제 | P4-T6 | UI 코드에서 sequential Mayor 흔적이 제거됨 |

### P4-C. frontend 테스트 갱신

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P4-T8 | DONE | `MayorStrategyPanel` 테스트 추가 | `frontend/src/components/__tests__/MayorStrategyPanel.test.tsx` | P4-T4 | 전략 카드 렌더/선택/disabled 상태가 검증됨 |
| P4-T9 | DONE | App auth-flow 테스트 보완 | 기존 auth flow 테스트 유지/보완 | P4-T3 | `frontend/src/__tests__/App.auth-flow.test.tsx`가 split 이후 flow를 검증함 |
| P4-T10 | DONE | App integration smoke | Mayor phase 진입 시 strategy UI 노출 테스트 | P4-T6 | `frontend/src/__tests__/App.mayor-flow.test.tsx`가 strategy UI 노출을 검증함 |

---

## 9. Phase 5 — MLOps / 평가 게이트

목표: “학습에서는 이기는데 실제에서는 진다” 문제를 코드/메타데이터/평가 게이트로 방지한다.

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P5-T1 | DONE | artifact fingerprint 필드 추가 | model metadata/replay metadata 확장 | P1-T5, P3-T5 | action_space/mayor_semantics/env fingerprint가 기록됨 |
| P5-T2 | DONE | `model_registry.py` fingerprint 노출 | sidecar 우선/metadata 보강 | P5-T1 | serving 시 모델 식별 정보가 일관되게 노출됨 |
| P5-T3 | DONE | replay parity 정보 저장 | replay logger에 모델/엔진 fingerprint 추가 | P5-T1 | visualization과 offline eval 비교 가능한 데이터가 남음 |
| P5-T4 | DONE | scenario regression harness 추가 | Trader 과선호/5 doubloon role/Mayor 전략 검증 | P3-T9 | `backend/app/services/scenario_regression.py`와 대응 테스트로 알려진 이상 행동을 자동 검출함 |
| P5-T5 | DONE | promotion gate 문서화 | 승격 기준과 실행 절차 | P5-T2, P5-T4 | `design/2026-04-08_engine_cutover_promotion_gate.md`에 승격 규칙과 최소 실행 세트가 문서화됨 |

---

## 10. Phase 6 — cleanup / 리팩토링

목표: 컷오버 후 남은 거대 파일과 잔여 결합을 줄인다.

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P6-T1 | DONE | `App.tsx` 분해 | auth/router/game/mayor 화면 오케스트레이션 분리 | P4-T10 | `useAuthBootstrap`, `AppScreenGate`, `GameScreen`으로 책임이 분리됨 |
| P6-T2 | DONE | `game_service.py` 분해 | room lifecycle / turn execution / replay 분리 | P3-T9 | `game_service_support.py`로 snapshot/state helper가 분리됨 |
| P6-T3 | DONE | `state_serializer.py` 분해 | mapper/presenter/meta serializer 분리 | P3-T7 | `state_serializer_support.py`로 serializer 지원 책임이 분리됨 |
| P6-T4 | DONE | dead file 제거 | legacy Mayor 관련 파일, 테스트, helper 삭제 | P3-T10, P4-T7 | legacy Mayor service/tests가 삭제되고 cleanup 문서에 반영됨 |
| P6-T5 | DONE | import path 정리 | `sys.path` 조작 최소화 또는 허용 위치 고정 | P3-T11 | `engine_gateway/bootstrap.py` 중심으로 path bootstrap 위치가 고정됨 |

---

## 11. Phase 7 — 최종 검증 및 문서 정리

목표: 컷오버 이후 팀이 같은 계약을 보고 일할 수 있게 마무리한다.

| ID | 상태 | 작업 | 주요 산출물 | 의존성 | 완료 조건 |
|---|---|---|---|---|---|
| P7-T1 | DONE | backend 전체 테스트 정리 실행 | pytest 결과 | P3, P5, P6 | `docker compose exec backend pytest -q` 기준 `327 passed, 2 skipped`로 green |
| P7-T2 | DONE | frontend 테스트 및 build 확인 | vitest/build 결과 | P4, P6 | `docker compose exec frontend npm test`와 `npm run build`가 green |
| P7-T3 | DONE | replay/manual smoke 실행 | human Mayor strategy flow, bot flow 확인 | P3, P4, P5 | `design/2026-04-08_engine_cutover_final_verification.md`에 human/bot Mayor smoke replay 근거가 기록됨 |
| P7-T4 | DONE | `contract.md` 최종 반영 | 최신 supported contract 문서 | P7-T1, P7-T2 | contract/tests/doc reference가 현재 strategy-first 코드와 일치함 |
| P7-T5 | DONE | old plan 문서 정리 | outdated dual-mode 문서 deprecate 표시 | P7-T4 | old dual-mode plan 문서에 deprecated banner가 반영됨 |

- 상향식으로 각 폴더의 컴포넌트에 모두 README.md 파일을 만들어 설계도, 의존성 등을 정리
- 상위 폴더는 하위 폴더의 문서를 참조하고, 설계도, 의존성을 정리하는 방향으로

---

## 12. 추천 실행 묶음

너무 잘게 끊으면 진행이 느려지므로, 실제 작업은 아래 묶음으로 진행하는 것이 좋다.

### Batch A — 사전 정리
- P0-T1
- P0-T2
- P0-T3
- P0-T4

### Batch B — 엔진 기준점 고정
- P1-T1
- P1-T2
- P1-T3
- P1-T4
- P1-T5

### Batch C — backend 컷오버 최소선
- P2-T1
- P2-T2
- P3-T1
- P3-T2
- P3-T4
- P3-T5
- P3-T7
- P3-T9

### Batch D — frontend human Mayor 전환
- P4-T1
- P4-T2
- P4-T4
- P4-T5
- P4-T6
- P4-T7
- P4-T8

### Batch E — 신뢰성/품질
- P5-T1
- P5-T2
- P5-T3
- P5-T4
- P7-T1
- P7-T2
- P7-T3

### Batch F — 구조 정리
- P6-T1
- P6-T2
- P6-T3
- P6-T4
- P6-T5
- P7-T4
- P7-T5

---

## 13. 가장 먼저 손댈 추천 5개

우선순위를 좁히면 아래 5개가 첫 스타트로 가장 좋다.

1. `P0-T1` backend direct import inventory 작성
2. `P0-T2` frontend Mayor/action coupling inventory 작성
3. `P1-T2` upstream 전체를 `PuCo_RL`에 반영
4. `P2-T1` `contract.md` Mayor 계약 strategy-first로 갱신
5. `P3-T5` `game_service.py`의 Mayor flow를 human/bot 공통 strategy action으로 통일

---

## 14. 완료 기준

이 backlog가 끝났다고 볼 수 있는 조건:

- `PuCo_RL`이 canonical engine으로 고정되어 있다.
- human/bot 모두 Mayor phase에서 strategy action만 사용한다.
- frontend에 sequential Mayor UI가 남아 있지 않다.
- backend public contract에서 sequential Mayor API가 제거되어 있다.
- model artifact fingerprint와 replay parity 정보가 남는다.
- 거대 파일들의 책임이 분리되어, 기능 수정 시 확인해야 할 파일 수가 지금보다 명확히 줄어든다.
