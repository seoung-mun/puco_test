# Docker 테스트 보고서

작성일: 2026-04-05
시간대: Asia/Seoul
작업 경로: `/Users/seoungmun/Documents/agent_dev/castest/castone`

## 개요

이 문서는 `docker-compose.yml` 기준으로 Docker 환경에서 실제 테스트를 실행한 결과를 정리한 보고서입니다.

실행한 명령은 아래와 같습니다.

```bash
docker compose up -d --build
docker compose exec backend pytest -q
docker compose exec frontend npm test
```

## 환경 상태

- `docker compose up -d --build` 실행은 성공했습니다.
- Backend, Frontend, PostgreSQL, Redis, Adminer 컨테이너가 정상적으로 기동되었습니다.

## 전체 결과 요약

### 백엔드

- 실행 명령: `docker compose exec backend pytest -q`
- 결과: 실패
- 요약: `7 failed, 299 passed, 1 skipped, 9 warnings in 46.62s`

### 프론트엔드

- 실행 명령: `docker compose exec frontend npm test`
- 결과: 실패
- 요약: `1 failed suite, 3 passed suites, 15 passed tests in 6.49s`

## 백엔드 실패 항목

### 1. Legacy Mayor distribute 에러 계약 불일치

실패한 테스트:

- `tests/test_legacy_features.py::TestMayorDistributeErrorFormat::test_slot_capacity_error_returns_400`
- `tests/test_legacy_features.py::TestMayorDistributeErrorFormat::test_slot_capacity_error_detail_is_dict`
- `tests/test_legacy_features.py::TestMayorDistributeErrorFormat::test_slot_capacity_error_detail_has_slot_capacity`
- `tests/test_legacy_features.py::TestMayorDistributeErrorFormat::test_slot_capacity_error_detail_has_slot_info`
- `tests/test_legacy_features.py::TestMayorDistributeErrorFormat::test_slot_capacity_error_detail_has_distribution_received`
- `tests/test_legacy_features.py::TestMayorDistributeErrorFormat::test_slot_capacity_error_detail_has_unplaced_colonists`

관찰된 현상:

- 테스트는 `400 Bad Request`를 기대했습니다.
- 실제 응답은 `200 OK`였습니다.

기대 계약:

- 잘못된 mayor 슬롯 배치는 실패해야 하며, `detail` 필드에 구조화된 진단 정보가 들어 있어야 합니다.
- 테스트가 기대하는 핵심 필드는 아래와 같습니다.
  - `slot_capacity`
  - `slot_info`
  - `distribution_received`
  - `unplaced_colonists`

의미:

- Legacy 엔드포인트 `/api/action/mayor-distribute`가 더 이상 테스트 fixture가 보내는 distribution을 잘못된 입력으로 판단하지 않고 있습니다.
- 즉, legacy 테스트가 기대하는 mayor 슬롯 검증 규칙과 현재 엔진/액션 마스크 동작 사이에 계약 드리프트가 생긴 상태입니다.

관련 코드:

- `backend/app/api/legacy/actions.py`
- `backend/tests/test_legacy_features.py`

추정 원인:

- `action_mayor_distribute()`는 현재 액션 마스크 기준으로 invalid일 때만 에러를 발생시킵니다.
- 그런데 현재 mayor cursor 상태와 엔진 초기화 기준에서는 `[1] * 24` 분배안이 예전처럼 invalid로 처리되지 않고 그대로 통과하고 있습니다.
- 다시 말해, mayor 슬롯 진행 규칙이 바뀌었거나, legacy 테스트 fixture가 더 이상 “capacity=0 슬롯” 상황을 제대로 만들지 못하고 있을 가능성이 큽니다.

## 백엔드 실패 항목

### 2. Mayor serializer의 skip 가능 플래그 불일치

실패한 테스트:

- `tests/test_todo_priority1_task1_mayor_contract.py::test_mayor_serializer_slot_idx_matches_engine_cursor`

관찰된 현상:

- 기대값: `initial_state["meta"]["mayor_can_skip"] is True`
- 실제값: `False`

의미:

- 현재 직렬화된 상태가 테스트가 기대하는 mayor 계약과 맞지 않습니다.
- 단순 UI 표현 문제가 아니라, serializer와 엔진의 action mask 계약이 어긋난 상태로 볼 수 있습니다.

관련 코드:

- `backend/app/services/state_serializer.py`
- `backend/tests/test_todo_priority1_task1_mayor_contract.py`

추정 원인:

- `serialize_game_state_from_engine()`는 `action_mask[69]`를 보고 `mayor_can_skip`를 계산합니다.
- 그런데 테스트 fixture가 만든 초기 mayor 상태에서는 엔진이 skip 불가로 판단하고 있습니다.
- 즉, 테스트가 기대하는 mayor 배치 규칙과 현재 action mask 생성 규칙 사이에 드리프트가 존재합니다.

## 백엔드 경고

### 1. FastAPI startup 이벤트 deprecation 경고

관찰된 경고:

- `app/main.py:58`에서 `@app.on_event("startup")`를 사용하고 있습니다.

영향:

- 지금 당장 테스트를 깨는 문제는 아닙니다.
- 하지만 향후 FastAPI 업그레이드 시 lifecycle 처리 방식 변경에 대응해야 하므로, `lifespan` 기반으로 옮기는 편이 안전합니다.

관련 코드:

- `backend/app/main.py`

### 2. WebSocket 테스트에서 Redis listener mock 경고

관찰된 경고:

- `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited`

영향 범위:

- `tests/test_ws_disconnect.py`
- `backend/app/services/ws_manager.py`

영향:

- 현재 테스트는 통과하지만, mock이 `_redis_listener()`가 기대하는 async iterator 형태와 정확히 맞지 않는 것으로 보입니다.
- 이런 경고는 Redis pubsub 경로의 회귀를 테스트가 제대로 잡지 못하게 만들 수 있습니다.

## 프론트엔드 실패 항목

### 1. Node 환경 테스트에서 `localStorage`를 import 시점에 참조함

실패한 스위트:

- `vite.config.test.ts`

관찰된 오류:

```text
ReferenceError: localStorage is not defined
at src/i18n.ts:7
```

의미:

- 이 테스트는 Node 환경에서 실행됩니다.
- 그런데 `src/i18n.ts`가 import되는 순간 `localStorage.getItem('lang')`를 바로 호출하고 있어서, 테스트 본문이 실행되기도 전에 실패합니다.

관련 코드:

- `frontend/src/i18n.ts`
- `frontend/vite.config.test.ts`

추정 원인:

- `src/i18n.ts`가 브라우저 전역 객체가 항상 존재한다고 가정하고 있습니다.
- 하지만 테스트 스위트 중 일부는 Node 환경에서 돌기 때문에 `localStorage`가 없습니다.

권장 방향:

- `typeof window !== "undefined"` 또는 `typeof localStorage !== "undefined"` 가드로 보호해야 합니다.
- 또는 브라우저 전용 i18n 초기화와 Node 환경 설정 테스트를 분리하는 방식도 가능합니다.

## 실패 수치 정리

### 백엔드

- 실패: 7
- 성공: 299
- 스킵: 1
- 경고: 9

실패 분류:

- 6건: Legacy mayor distribute 계약 불일치
- 1건: Mayor serializer 계약 불일치

### 프론트엔드

- 실패한 스위트: 1
- 통과한 스위트: 3
- 통과한 테스트: 15

실패 분류:

- 1건: `vite.config.test.ts`

## 우선순위 관점 정리

### 높은 우선순위

- 백엔드 legacy mayor distribute 계약 불일치
- 백엔드 mayor serializer 계약 불일치
- 프론트 테스트 환경에서 `localStorage` 참조로 인한 즉시 실패

### 중간 우선순위

- FastAPI startup 이벤트 deprecation 대응
- Redis listener 테스트 mock 경고 정리

## 사전 코드 리뷰에서 발견한 추가 문제

아래 항목들은 이번 Docker 테스트 실행에서 직접 실패로 드러난 것은 아니지만, 그 전에 전체 코드베이스를 검토하면서 확인한 고위험 이슈들입니다.

이 섹션은 “테스트로 재현된 문제”와 “정적 코드 리뷰로 식별한 문제”를 구분하기 위해 별도로 정리했습니다.

### 1. 게임 시작 직후 로비 WebSocket 종료가 실제 leave로 처리되는 문제

관찰 내용:

- 프론트는 `GAME_STARTED`를 받으면 로비 WebSocket을 즉시 닫습니다.
- 백엔드 `lobby_websocket()`는 `finally`에서 항상 `handle_leave()`를 호출합니다.
- `handle_leave()`는 `PROGRESS` 상태에서도 `room.players`에서 플레이어를 제거합니다.

영향:

- 정상적으로 게임을 시작한 플레이어가 곧바로 active room에서 빠질 수 있습니다.
- 이후 `/action` 호출이 `403`으로 실패하거나, 실제 참가자 목록이 잘못 유지될 수 있습니다.

관련 코드:

- `frontend/src/App.tsx`
- `backend/app/api/channel/lobby_ws.py`
- `backend/app/services/lobby_manager.py`

### 2. 종료된 게임이 계속 액션을 받을 수 있는 문제

관찰 내용:

- 강제 종료 경로는 DB의 `games.status`만 `FINISHED`로 바꾸고 있습니다.
- 하지만 `/api/puco/game/{game_id}/action`은 `room.status`가 `FINISHED`인지 검사하지 않습니다.
- 메모리 안의 엔진이 살아 있으면 종료 후에도 액션을 계속 처리할 수 있습니다.

영향:

- DB 상태와 실제 엔진 상태가 분리됩니다.
- WebSocket 이벤트, replay 로그, 최종 점수, 실제 게임 진행이 서로 어긋날 수 있습니다.

관련 코드:

- `backend/app/services/ws_manager.py`
- `backend/app/api/channel/game.py`
- `backend/app/services/game_service.py`

### 3. 진행 중인 게임 상태가 프로세스 메모리에만 존재하는 문제

관찰 내용:

- 활성 게임 엔진은 `GameService.active_engines`라는 프로세스 메모리 딕셔너리에만 저장됩니다.
- 서버 시작 시 복구 로직은 `WAITING` 방만 정리하고, `PROGRESS` 게임을 복원하지 않습니다.

영향:

- 컨테이너 재시작, 프로세스 재기동, 멀티워커 배포 시 진행 중 게임이 사실상 복구 불가능합니다.
- DB에는 게임이 남아 있어도 `/action`, `/final-score`가 동작하지 않을 수 있습니다.

관련 코드:

- `backend/app/services/game_service.py`
- `backend/app/services/startup_cleanup.py`
- `backend/app/main.py`

MLOps/운영 관점:

- 현재 구조는 single-process 메모리 상태에 강하게 의존합니다.
- 수평 확장이나 장애 복구를 고려하면 상태 복원 전략 또는 authoritative store 재설계가 필요합니다.

### 4. ML 전이 로그(JSONL)가 DB 트랜잭션과 분리되어 기록되는 문제

관찰 내용:

- `MLLogger.log_transition()`는 DB commit 전에 백그라운드 task로 예약됩니다.
- 이후 DB 로그와 room 상태가 commit됩니다.

영향:

- DB commit이 실패하면 JSONL에는 남고 DB에는 없는 orphan transition이 생길 수 있습니다.
- 반대로 프로세스 종료 타이밍에 따라 DB에는 있는데 JSONL에는 없는 샘플도 생길 수 있습니다.
- 오프라인 재학습 데이터와 정본 운영 로그의 계보가 깨질 수 있습니다.

관련 코드:

- `backend/app/services/game_service.py`
- `backend/app/services/ml_logger.py`

MLOps 관점:

- 학습 데이터의 재현성, lineage, 감사 가능성을 떨어뜨리는 구조입니다.
- outbox 패턴이나 commit 이후 보장된 비동기 전달 방식이 더 적합합니다.

### 5. HPPO 학습 경로가 현재 코드 기준으로 깨져 있는 문제

관찰 내용:

- `PuCo_RL/train_hppo_selfplay_server.py`와 `PuCo_RL/train_hppo_league_server.py`, `PuCo_RL/tests/test_hppo_agent.py`는 `HierarchicalAgent`를 import합니다.
- 그러나 실제 `PuCo_RL/agents/ppo_agent.py`에는 `Agent`와 `PhasePPOAgent`만 정의되어 있습니다.

영향:

- HPPO 학습 및 평가 경로는 현재 코드 기준으로 실행 불가능하거나, 최소한 심볼 불일치 상태입니다.
- “지원하는 학습 경로”처럼 보이지만 실제로는 dead path일 가능성이 큽니다.

관련 코드:

- `PuCo_RL/train_hppo_selfplay_server.py`
- `PuCo_RL/train_hppo_league_server.py`
- `PuCo_RL/tests/test_hppo_agent.py`
- `PuCo_RL/agents/ppo_agent.py`

MLOps 관점:

- 학습 스크립트, 모델 정의, 테스트 코드가 동일한 인터페이스를 공유하지 못하고 있습니다.
- 이런 종류의 드리프트는 모델 운영보다 먼저 학습 파이프라인 자체의 신뢰도를 깨뜨립니다.

## 추가 문제 요약

사전 코드 리뷰로 확인한 고위험 항목은 아래와 같습니다.

1. 게임 시작 직후 정상 플레이어가 room에서 제거될 수 있음
2. 종료된 게임이 추가 액션을 계속 받을 수 있음
3. 진행 중 게임이 재시작/확장 시 복구되지 않음
4. ML 재학습용 로그와 정본 DB 로그의 일관성이 깨질 수 있음
5. HPPO 학습 경로가 심볼 드리프트로 인해 현재 깨져 있음

## 결론

Docker 환경 자체는 정상적으로 기동되고 재현도 가능합니다. 다만 현재 테스트 결과는 깨끗하지 않습니다.

이번 실행 기준으로 바로 손봐야 할 핵심 문제는 아래 세 가지입니다.

1. 백엔드 mayor 관련 계약이 legacy API와 serializer에서 어긋나 있습니다.
2. 프론트엔드는 브라우저 전역 객체를 import 시점에 참조해서 Node 기반 테스트가 깨집니다.
3. 당장 실패는 아니지만 startup lifecycle 처리와 Redis listener 테스트 mock 쪽에 유지보수 리스크가 남아 있습니다.

추가로, 테스트만으로는 드러나지 않았지만 운영과 MLOps 관점에서 더 위험한 구조적 문제도 존재합니다. 특히 게임 상태의 메모리 의존성, 종료 후 액션 허용, ML 로그 계보 불일치, HPPO 학습 경로 드리프트는 우선순위 높게 다루는 편이 좋습니다.
