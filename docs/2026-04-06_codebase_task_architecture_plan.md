# 현재 코드베이스 문제 정의 및 태스크 설계 계획서

작성일: 2026-04-06

기준 문서:

- `docs/2026-04-05_error_priority_tdd_architecture_plan.md`
- `docs/2026-04-06_mayor_docker_runtime_tdd_report.md`
- `docs/2026-04-06_web_release_readiness_brainstorm_report.md`

추가 반영 기준:

- 2026-04-06 현재 워크트리의 실제 코드 상태
- 최근 Docker 기반 검증에서 반영된 로비/봇/인증 수정 사항

## 목적

이 문서는 세 개의 기존 보고서를 현재 코드베이스 기준으로 다시 정리해,

- 이미 해결된 문제
- 아직 해결되지 않은 문제
- 지금 바로 착수해야 하는 태스크
- 중기 아키텍처 설계 과제

를 한 문서에서 추적할 수 있도록 만든 실행 계획서다.

핵심 원칙은 다음과 같다.

1. 문서의 과거 진단을 그대로 반복하지 않는다.
2. 현재 코드에 이미 반영된 수정은 `해결됨`으로 명확히 분리한다.
3. 남은 문제는 작업 단위로 쪼개고, 각 태스크마다 설계 방향과 검증 기준을 적는다.

## 현재 상태 요약

### 해결된 문제

1. 로비 WebSocket 종료가 게임 시작 직후 `leave`로 처리되던 문제는 해결됐다.
   - `backend/app/api/channel/lobby_ws.py`에서 `WAITING` 상태일 때만 `handle_leave()`를 호출한다.
   - 결과적으로 `GAME_STARTED` 이후 로비 소켓 종료는 화면 전환으로 처리된다.

2. Mayor modern runtime 계약 문제는 해결됐다.
   - `backend/app/services/mayor_orchestrator.py`와 `backend/app/services/state_serializer.py`가 동일한 `slot_id` 규칙을 사용한다.
   - `island:corn:0` 형태의 프론트 payload가 orchestrator에서 그대로 통과하는 방향으로 정렬되었다.

3. 봇 삭제 후 재추가 시 `최대 3명까지 참가할 수 있습니다`가 뜨던 문제는 해결됐다.
   - 원인은 프론트가 봇을 로컬 상태에서만 제거하고 서버의 `room.players`는 그대로 두던 것이었다.
   - 현재는 `DELETE /api/puco/game/{game_id}/bots/{slot_index}`가 추가되어 서버 상태와 UI 상태가 일치한다.

4. 로그인 시 기존 `test` 계정으로 다시 붙는 현상은 해결됐다.
   - 원인은 `logout()` 경로에서 `localStorage.access_token`이 지워지지 않던 것이었다.
   - 현재는 인증 세션 정리 함수가 별도로 분리되어 로그아웃 시 토큰과 사용자 상태를 함께 비운다.

### 해결되었지만 후속 정리가 필요한 항목

1. Mayor 계약은 런타임 기준으로 정렬되었지만, shared contract utility로 더 명시화할 여지는 남아 있다.
2. 로비/게임 상태 경계는 한 차례 정리됐지만, 세션 생명주기 전체를 하나의 정책 함수로 통합한 상태는 아니다.

### 아직 남아 있는 핵심 문제

1. 종료된 게임이 여전히 action을 받을 수 있는 구조다.
   - `backend/app/api/channel/game.py`의 `/action`과 `/mayor-distribute`는 현재 `room.status == "PROGRESS"`를 강제하지 않는다.
   - `GameService.process_action()`도 서비스 레벨에서 종료 상태를 hard guard 하지 않는다.

2. disconnect timeout 또는 사용자 종료 후 DB와 in-memory engine이 분리될 수 있다.
   - `backend/app/services/ws_manager.py`는 timeout 시 DB status만 `FINISHED`로 바꾸고 `GameService.active_engines` 정리나 봇 task 정리를 하지 않는다.

3. ML transition logging이 DB commit 이전에 예약된다.
   - `backend/app/services/game_service.py`에서 `MLLogger.log_transition()`은 `self.db.commit()`보다 먼저 background task로 스케줄된다.
   - 이 구조는 lineage 오염 가능성을 남긴다.

4. 프론트 빌드에 `VITE_INTERNAL_API_KEY`가 여전히 포함되는 구조다.
   - `frontend/src/App.tsx`의 `apiFetch()`가 브라우저에서 `X-API-Key`를 넣는다.
   - `frontend/Dockerfile`도 해당 값을 빌드 인자로 받는다.

5. `frontend/src/i18n.ts`는 import 시점에 `localStorage`를 직접 읽는다.
   - Node/test 환경에서 깨질 수 있는 구조이며, 문서에 적힌 테스트 취약점이 아직 코드상 남아 있다.

6. FastAPI startup은 여전히 `@app.on_event("startup")`를 사용한다.
   - 현재 Docker 검증에서도 deprecation warning이 반복된다.

7. 장기적으로 상태 정본과 복구 전략이 아직 분리되지 않았다.
   - 현재 구조는 `DB + Redis + in-memory engine + replay/jsonl`가 동시에 존재하지만, 복구와 정합성 정책은 부분적이다.

### 명시적 비우선순위 / 제외

1. HPPO 경로 drift 문제는 현재 제품/운영 우선순위에서 제외한다.
   - 기존 문서에도 “더 이상 사용되지 않아도 된다”는 방향이 반영되어 있다.
   - 학습 파이프라인을 다시 활성화하기 전까지는 release blocker로 취급하지 않는다.

2. 공개 매치메이킹, 고급 통계 대시보드, 관전자 모드 고도화는 현 단계 범위에서 제외한다.

## 우선순위 재정의

| 우선순위 | 상태 | 문제 | 이유 |
| --- | --- | --- | --- |
| P0 | 미해결 | 종료된 게임 action 차단 부재 | 상태 정본 불변식이 깨짐 |
| P0 | 미해결 | 종료 후 engine/task 정리 부재 | DB와 런타임 상태 분리 위험 |
| P0 | 미해결 | 브라우저 internal key 구조 | 공개 배포 부적합 |
| P1 | 미해결 | i18n import-time `localStorage` 접근 | 프론트 테스트/비브라우저 환경 취약 |
| P1 | 미해결 | ML logging commit 이전 예약 | 데이터 lineage 오염 위험 |
| P1 | 해결됨 | 로비 WS close != leave | 핵심 멀티플레이 blocker 제거 완료 |
| P1 | 해결됨 | Mayor slot_id 계약 drift | human Mayor runtime blocker 제거 완료 |
| P1 | 해결됨 | 봇 삭제 후 재추가 409 | 로비 서버 상태 정합성 회복 |
| P1 | 해결됨 | 로그아웃 후 test 계정 고정 | 인증 세션 정리 완료 |
| P2 | 미해결 | FastAPI startup deprecation | 유지보수성 문제 |
| P2 | 미해결 | engine recovery / replay 기반 복구 부재 | 중기 아키텍처 과제 |

## 태스크 설계

## Task 1. Action Lifecycle Guard 도입

### 목표

게임이 `PROGRESS` 상태일 때만 action write path가 실행되도록 강제한다.

### 설계

1. API route guard 추가
   - `/api/puco/game/{id}/action`
   - `/api/puco/game/{id}/mayor-distribute`
   - 필요 시 `/start`에도 상태 전이 검증을 더 명시화

2. 서비스 레벨 guard 추가
   - `GameService.process_action()`
   - `GameService.process_mayor_distribution()` 경유 경로

3. 공통 정책 함수로 추출
   - 예: `ensure_room_is_actionable(room)`
   - route와 service에서 동일 규칙을 사용

### 대상 파일

- `backend/app/api/channel/game.py`
- `backend/app/services/game_service.py`
- 관련 테스트 파일

### 완료 조건

- `WAITING`/`FINISHED` 상태에서 action 요청이 명시적으로 거부된다.
- disconnect timeout 후에도 추가 action이 수락되지 않는다.

### 검증

- route test: `409 Game is not accepting actions`
- service test: engine이 살아 있어도 `FINISHED`면 거부

## Task 2. 종료 상태 통합 및 Engine Cleanup

### 목표

게임 종료 시 DB, Redis, in-memory engine, bot task가 한 번에 정리되도록 만든다.

### 설계

1. 종료 경로를 공통화한다.
   - normal finish
   - disconnect timeout finish
   - `END_GAME_REQUEST`

2. 공통 종료 함수에서 다음을 수행한다.
   - `room.status = "FINISHED"`
   - 종료 사유 기록
   - `GameService.active_engines.pop(game_id, None)`
   - 관련 bot task / watchdog 정리
   - Redis meta/status 정리
   - 최종 replay append 일관화

3. 종료 후 read-only 정책을 명시한다.
   - final score는 허용
   - action/write는 금지

### 대상 파일

- `backend/app/services/ws_manager.py`
- `backend/app/services/game_service.py`
- `backend/app/api/channel/game.py`

### 완료 조건

- 어떤 종료 경로로 들어가든 active engine이 남지 않는다.
- 종료 후 replay/DB 상태가 서로 일치한다.

### 검증

- disconnect timeout 후 active engine 제거 테스트
- `END_GAME_REQUEST` 후 action 거부 테스트

## Task 3. ML Logging Outbox / Commit-After Publish 구조화

### 목표

ML transition 로그가 DB commit에 종속되도록 만들어 데이터 계보를 보존한다.

### 설계

1. 현재 문제
   - `MLLogger.log_transition()`이 commit 이전에 background task로 예약된다.

2. 단기 해결
   - commit 성공 후에만 ML logging enqueue
   - 실패 시 기록하지 않음

3. 중기 구조
   - DB outbox table 또는 durable queue 도입
   - publisher가 outbox를 읽어 JSONL/replay/추가 artifact를 반영

### 대상 파일

- `backend/app/services/game_service.py`
- `backend/app/services/ml_logger.py`
- 필요 시 migration / outbox 모델

### 완료 조건

- rollback된 action은 ML transition에 남지 않는다.
- 한 게임의 DB log와 ML log를 `game_id + step` 기준으로 안정적으로 대조할 수 있다.

### 검증

- DB commit 실패 시 ML log 미생성 테스트
- 정상 commit 시에만 ML log 생성 테스트

## Task 4. Frontend Storage Safety 및 Test Stabilization

### 목표

프론트가 브라우저 외 환경에서도 안전하게 초기화되도록 만든다.

### 설계

1. `localStorage` 직접 접근을 storage helper로 감싼다.
   - `typeof window !== "undefined"`
   - 실패 시 기본값 반환

2. 우선 적용 대상
   - `frontend/src/i18n.ts`
   - 인증 토큰 초기화 코드
   - 언어 저장/복원 코드

3. import-time side effect를 최소화한다.
   - module import 시 바로 브라우저 API를 읽지 않도록 조정

### 대상 파일

- `frontend/src/i18n.ts`
- `frontend/src/App.tsx`
- 필요 시 테스트 설정 파일

### 완료 조건

- `npm test` / Vitest 환경에서 `localStorage is not defined`가 재발하지 않는다.

### 검증

- 프론트 테스트 실행
- 언어 기본값/저장값 복원 회귀 테스트

## Task 5. Browser Internal Key 제거

### 목표

브라우저 번들에 내부 키가 포함되지 않도록 인증/레거시 호출 구조를 정리한다.

### 설계

1. `apiFetch()`의 `X-API-Key` 자동 주입을 제거한다.
2. 현재 key가 필요한 레거시 endpoint를 채널 API 또는 공개 read-only endpoint로 옮긴다.
3. 프론트에서 사용하는 실제 read/write endpoint 목록을 정리해, 브라우저에서 internal secret이 전혀 필요 없게 만든다.

### 대상 파일

- `frontend/src/App.tsx`
- `frontend/Dockerfile`
- `frontend/README.md`
- 레거시 API 의존 구간

### 완료 조건

- 프론트 빌드 산출물에서 internal key가 사라진다.
- 브라우저 요청이 JWT/일반 공개 endpoint만 사용한다.

### 검증

- 프론트 build 후 env 주입 경로 점검
- 네트워크 호출 smoke test

## Task 6. FastAPI Lifespan 전환

### 목표

startup/shutdown 정책을 deprecation 없는 구조로 이전한다.

### 설계

1. `@app.on_event("startup")`를 lifespan context manager로 교체한다.
2. 시작 시점 책임을 아래처럼 정리한다.
   - DB/Redis health probe
   - stale room cleanup
   - 이후 필요 시 shutdown cleanup hook 추가

### 대상 파일

- `backend/app/main.py`

### 완료 조건

- Docker 실행 로그에서 startup deprecation warning이 사라진다.

### 검증

- backend boot smoke test
- health endpoint 정상 동작 확인

## Task 7. Engine Recovery Architecture 초안 수립

### 목표

현재의 `in-memory engine` 의존 구조를 복구 가능한 형태로 발전시키기 위한 중기 설계 초안을 만든다.

### 설계

1. 정본 정의
   - 1차 정본: PostgreSQL game/session/log
   - 2차 복구 재료: replay/event log
   - 메모리 엔진: 실행 캐시

2. 복구 전략
   - 서버 재기동 시 `PROGRESS` 게임 탐색
   - replay/event log로 engine 복원
   - 복원 실패 시 game 상태를 보호 모드로 전환

3. 단계적 도입
   - Phase A: 종료 cleanup 보강
   - Phase B: 재기동 시 orphan progress game 탐지
   - Phase C: replay 기반 engine rebuild

### 대상 파일

- `backend/app/services/game_service.py`
- `backend/app/services/replay_logger.py`
- DB schema / recovery utility 신규 파일

### 완료 조건

- 설계 문서 + spike 구현 + 최소 복구 테스트 확보

### 검증

- restart simulation test
- progress game recovery smoke test

## 권장 실행 순서

### Phase 1. Release Blocker 정리

1. Task 1. Action Lifecycle Guard
2. Task 2. 종료 상태 통합 및 Engine Cleanup
3. Task 5. Browser Internal Key 제거
4. Task 4. Frontend Storage Safety

### Phase 2. 데이터 정합성 강화

1. Task 3. ML Logging Outbox / Commit-After Publish
2. Mayor shared utility follow-up 정리

### Phase 3. 유지보수 및 복구 설계

1. Task 6. FastAPI Lifespan 전환
2. Task 7. Engine Recovery Architecture 초안 수립

## Scope

- In:
  - 멀티플레이 lifecycle 안정화
  - action 종료 불변식
  - 로그/엔진 정합성
  - 프론트 테스트 안정성
  - 배포 보안 구조 개선

- Out:
  - 랭킹/매치메이킹
  - 공개 관전자 기능
  - 시각화 대시보드 고도화
  - HPPO 학습 경로 정리

## Validation Matrix

| 검증 종류 | 필수 여부 | 목적 |
| --- | --- | --- |
| backend pytest targeted | 필수 | lifecycle / mayor / bot 관리 회귀 검증 |
| frontend build | 필수 | 타입/번들 회귀 확인 |
| frontend test | 필수 | storage-safe boot 확인 |
| docker smoke playthrough | 필수 | 방 생성 → 봇 추가/삭제 → 시작 → 종료 흐름 검증 |
| replay/log inspection | 권장 | game_id 단위 정합성 확인 |

## 최종 판단

현재 코드베이스는 세 문서 작성 시점보다 분명히 안정화가 진행되었다. 특히,

- Mayor runtime blocker
- 로비 WS 종료 처리 오류
- 봇 삭제/재추가 불일치
- 로그아웃 세션 잔존

은 현재 기준 해결된 범주로 볼 수 있다.

하지만 공개 배포 readiness 관점에서 보면 아직 다음 세 가지가 남아 있다.

1. 종료 상태 불변식 강제
2. 종료 후 engine/log 정합성 확보
3. 브라우저 internal key 제거 및 프론트 테스트 안정화

즉, 지금의 다음 단계는 “새 기능 추가”보다 “상태 전이와 운영 신뢰성 고정”이다.
