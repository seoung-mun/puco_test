# 에러 로그 작업 준비 문서

> **실행 방식:** 이후 구현은 `dev` 브랜치에서 진행한다. 현재 dirty 상태의 `prod` 워크트리에서는 구현하지 않는다. 실제 구현 단계에서는 `superpowers:subagent-driven-development`를 사용한다.

**원본 입력:** `/Users/seoungmun/Documents/agent_dev/castest/castone/error_logs.md`

**목표:** `error_logs.md`에 섞여 있는 여러 종류의 작업을, 먼저 처리할 것과 나중으로 미룰 것을 분리하고, 가능한 한 적은 수정으로 문제를 해결하는 순서로 재정렬한다.

---

## 1. 전제

이번 정리의 핵심 전제는 두 가지다.

1. **구현은 `dev` 브랜치에서 한다.**
2. **우선순위는 “최대한 일을 덜 하는 방향”으로 잡는다.**

즉, 큰 구조개편이나 장기 정리는 뒤로 미루고, 먼저 작업 시작을 안전하게 만드는 정리와 실제 장애를 가장 적은 수정으로 막는 순서를 택한다.

---

## 2. 현재 코드 기준 빠른 판단

코드를 대조해 보니 지금 바로 섞으면 안 되는 작업이 많다.

- 멀티플레이 버그 수정
- git/브랜치 정리
- 배포용 슬림화
- 전체 UI 리디자인
- 레거시/문서 재배치
- AWS 운영 정리

이걸 한 번에 잡으면 변경 범위가 너무 커져서, 실제 멀티플레이 장애 원인 파악과 검증이 더 어려워진다.

또 하나 중요한 점은, 새로고침 복구 경로는 이미 일부 들어가 있다는 것이다.

관련 파일:

- `frontend/src/lib/activeGameSession.ts`
- `frontend/src/hooks/useAuthBootstrap.ts`
- `backend/tests/test_active_game_session.py`
- `frontend/src/__tests__/App.refresh-rejoin.test.tsx`

그래서 1차 구현의 중심은 “새로고침 복구를 새로 만드는 것”보다는 아래 쪽에 더 가깝다.

- 턴 소유권 정합성
- 다른 플레이어 UI 노출 차단
- 역할 선택/진행 handoff 안정화
- 좌석/순서 랜덤화 여부

---

## 3. 우선순위

### 1순위: Git 정리

가장 먼저 할 일은 **구현을 시작할 수 있는 최소한의 git 정리**다.

여기서 중요한 건 “대청소”가 아니라 “작업 시작을 안전하게 만드는 정리”다.

먼저 할 것:

1. `prod`에서 직접 구현하지 않기
2. `dev` 브랜치 기준으로 작업 시작
3. 필요하면 worktree/작업 브랜치 분리
4. 현재 dirty 변경분과 이후 구현 변경분이 섞이지 않게 만들기

지금 하지 않을 것:

1. 원격 브랜치 전부 삭제
2. 배포 브랜치 정책 전면 개편
3. 파일 대량 삭제
4. 테스트/문서/학습 자산 대청소

즉, 1순위의 의미는 **“큰 git 개편”이 아니라 “구현 들어가기 전 최소 정리”**다.

---

### 2순위: 다른 플레이어 UI 노출 문제

이건 비교적 적은 수정으로 잡힐 가능성이 높다.

대상 증상:

- 다른 사람 플레이어의 UI가 보이는 문제
- 예: 생산자 추가 선택 UI, 역할별 추가 행동 UI 노출

우선 이걸 먼저 두는 이유:

1. 프론트 단 게이팅 문제일 가능성이 높다
2. 수정 범위가 상대적으로 작을 수 있다
3. 잘못 보이는 UI만 막아도 체감 오류가 크게 줄어든다

우선 확인 파일:

- `frontend/src/App.tsx`
- `frontend/src/components/GameScreen.tsx`

---

### 3순위: 잘못된 알림/표시 문제

대상 증상:

- 내가 생산자를 누르지 않았는데 생산자 알림이 뜨는 문제

이건 2순위와 붙어 있을 가능성이 높다.  
즉, “누가 실제 행동 중인가”와 “누가 역할 소유자인가”를 프론트에서 혼동할 가능성이 있다.

현재 의심 포인트:

1. `state.meta.active_player`
2. `state.decision.player`
3. `state.common_board.roles[*].taken_by`

이 셋이 UI에서 서로 다른 의미로 섞여 쓰이면, 알림 주체가 틀어질 수 있다.

우선 확인 파일:

- `frontend/src/App.tsx`
- `frontend/src/components/GameScreen.tsx`
- `backend/app/services/state_serializer.py`

---

### 4순위: 역할 진행 handoff / 건축가 구매 문제

대상 증상:

1. 방장이 건축가를 고른 뒤 다른 플레이어가 건물을 구매하지 못함
2. 사람 1이 역할 선택 후 사람 2 차례에서 새로고침 전까지 선택이 안 되는 문제

이건 2, 3순위보다 더 중요할 수는 있지만, “일을 덜 하는 순서”로 보면 먼저 화면 노출/표시 쪽을 정리한 뒤 보는 편이 낫다.

이유:

1. 실제 원인이 프론트 턴 판정일 수도 있고
2. 백엔드 actor 검증/직렬화 문제일 수도 있어서
3. 범위가 더 넓고 테스트도 더 필요하다

주요 점검 축:

1. `GameService.process_action()`의 actor 검증
2. 직렬화된 `meta.active_player`
3. 직렬화된 `decision.player`
4. 프론트의 `isMyTurn` 판정

우선 확인 파일:

- `backend/app/services/game_service.py`
- `backend/app/services/game_service_support.py`
- `backend/app/services/state_serializer.py`
- `backend/app/api/channel/game.py`
- `frontend/src/App.tsx`
- `frontend/src/components/GameScreen.tsx`

관련 테스트 후보:

- `backend/tests/test_game_service_turn_validation.py`
- `frontend/src/components/__tests__/GameScreen.test.tsx`
- `frontend/src/__tests__/App.action-index-contract.test.tsx`

---

### 5순위: 좌석/순서 랜덤화

대상 증상:

- 순서가 방장 -> 다른 사람 -> ppo 로 사실상 고정되는 문제
- 첫 주지사만 랜덤이고 실제 순환 순서는 고정되는 문제

이건 작업량이 상대적으로 크다.

이유:

1. 단순히 `governor_idx`만 랜덤으로 주는 문제인지
2. 아예 좌석 배치 자체를 섞어야 하는지
3. 사람/봇 actor id, 리플레이, 상태 직렬화까지 같이 맞춰야 하는지

를 먼저 정해야 한다.

즉, “최대한 일을 덜 하는 순서” 기준에서는 앞선 멀티플레이 장애보다 뒤로 미루는 게 맞다.

우선 확인 파일:

- `backend/app/api/channel/room.py`
- `backend/app/api/channel/game.py`
- `backend/app/services/game_service.py`
- `backend/app/services/game_service_support.py`
- `backend/tests/test_governor_assignment.py`

---

### 6순위: 새로고침 관련 잔여 이슈 재검증

로그상 새로고침 이슈는 “처음 한 번만 그랬고 이후엔 재현이 애매하다”는 성격이 있다.

그래서 처음부터 이걸 독립 과제로 크게 잡기보다:

1. 2~4순위 수정 후
2. 같은 시나리오를 다시 검증하고
3. 그래도 남으면 별도 버그로 승격

하는 편이 작업량이 적다.

현재로서는 “독립 1순위 버그”로 보기보다, 멀티플레이 턴 정합성 문제의 파생 증상일 가능성이 더 크다.

---

## 4. 지금 당장 하지 않을 것

아래는 중요할 수는 있지만, 지금 섞으면 일만 커지는 항목들이다.

### 보류 1: 배포 브랜치/원격 브랜치 대정리

- `main/dev/prod` 원격 정책 통일
- 원격 브랜치 대량 삭제

이건 git 1순위와 다르다.  
지금 필요한 건 “구현 시작 전 최소 정리”이고, 이건 “정책/구조 개편”이라 별도 작업이다.

### 보류 2: prod 슬림화

- tests 제거
- docs 제거
- train 자산 제거
- 배포 최소 파일셋 정리

이건 실제 버그 수정과 섞지 않는 게 좋다.

### 보류 3: 전체 UI 리디자인

- 색감 변경
- 휴양지 느낌 리브랜딩
- 전체 UX 개편

이건 완전 별도 프론트 프로젝트로 보는 게 맞다.

### 보류 4: 레거시 파일/문서 구조 재정리

- `.md` 파일 정책
- `docs` 하위 분류
- 레거시 파일 삭제 여부 판단

이건 운영/정리 작업이고, 실시간 게임 버그 수정과 분리해야 한다.

### 보류 5: AWS 운영 정리

- 로그 보는 법
- 현재 외부 통신 구조
- spot 전환 계획

이건 인프라 런북 작업이다.

---

## 5. dev 브랜치에서의 실제 시작 순서

이후 구현을 `dev` 브랜치에서 시작할 때는 아래 순서가 가장 부담이 적다.

1. `git` 최소 정리
2. UI 노출 문제 수정
3. 잘못된 알림 주체 수정
4. 역할 진행 handoff / 건축가 구매 문제 수정
5. 좌석 순서 랜덤화 검토 및 필요 시 구현
6. 마지막에 새로고침 잔여 증상 재검증

---

## 6. 한 줄 결론

지금 기준 최우선은 **git을 크게 갈아엎는 것**이 아니라, **`dev` 브랜치에서 안전하게 구현을 시작할 수 있게 최소 정리하는 것**이다.  
그 다음은 **적은 수정으로 효과가 큰 멀티플레이 UI/알림 오류**부터 잡고, **턴 ownership/건축가 흐름**, 마지막으로 **순서 랜덤화**를 보는 순서가 가장 일이 덜 커진다.

