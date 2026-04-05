# 2026-04-05 Bot Game UI + Random Governor Design Report

## 1. 요청 요약

이번 작업 목표는 두 가지였습니다.

1. 봇전 방 생성 시 `random x 3` 고정이 아니라, 3개 슬롯 각각의 bot type을 선택할 수 있게 만들기
2. 게임 시작 시 주지사(governor)를 host/player_0로 강제하지 않고, 엔진이 자연스럽게 랜덤하게 정하도록 바꾸기

추가로, UI에서 변경 사항을 바로 확인하기 어렵기 때문에 실제 변경 내역과 검증 결과를 문서로 남기는 것도 요구 사항에 포함되었습니다.

---

## 2. 문제 정의

### 2-1. 봇전 생성 UX 문제

기존에는 backend API가 이미 `bot_types` payload를 받을 수 있었지만, frontend `RoomListScreen`은 그냥 `봇전` 버튼만 제공하고 있었습니다.

즉 실제 상태는 아래와 같았습니다.

- backend: `POST /api/puco/rooms/bot-game` 에 `bot_types` 전달 가능
- frontend: 항상 body 없이 호출
- 결과: 실제 UI에서는 항상 `random, random, random` 만 생성되는 것처럼 보임

### 2-2. governor 강제 고정 문제

`EngineWrapper` 가 생성 시 `env.reset()` 를 반복 호출해서 `governor_idx == 0` 인 상태만 채택하고 있었습니다.

이 방식의 문제는 다음과 같습니다.

- 실제 엔진 규칙과 UI/서버 계약이 다름
- host/player_0가 시작 플레이어라는 잘못된 가정이 코드에 퍼질 수 있음
- 테스트도 player_0 고정 가정을 따라가기 쉬움
- 실전 bot-vs-bot 관전에서 시작 조건 다양성이 사라짐

---

## 3. 설계 결정

## 3-1. 봇전 생성은 `UI selectable`, API 계약은 유지

핵심 결정:

- backend API는 그대로 사용
- frontend에서만 `bot game setup` modal을 추가
- 사용자는 3개 슬롯 각각에 대해 bot type을 고를 수 있음
- 최종 요청 body는 `{ "bot_types": ["ppo", "random", "ppo"] }` 형태로 전달

장점:

- 기존 backend 계약을 재활용 가능
- 로비의 `bot-types` 조회 패턴을 그대로 사용할 수 있음
- 이후 `candidate`, `benchmark` 같은 label이 생겨도 UI 확장 포인트가 유지됨

## 3-2. governor는 `env.reset(seed=...)` 기반 자연 랜덤 시작

핵심 결정:

- `EngineWrapper`에서 `governor_idx=0` 강제 루프 제거
- 기본 동작은 `self.env.reset(seed=game_seed)` 한 번 호출
- 즉 시작 governor는 `PuertoRicoGame` 이 정한 랜덤 값 사용

장점:

- 엔진 규칙과 wrapper 규칙이 일치
- 랜덤 초기 상태가 자연스럽게 유지
- governor 기반 초기 plantation 분배도 엔진이 만든 상태 그대로 사용

## 3-3. 특정 governor 지정 기능은 `post-hoc mutation` 대신 `consistent reset retry`

사용자 아이디어로는 `env.game.governor_idx = ...` 식의 사후 지정도 가능했지만, 그대로 적용하면 초기 plantation 분배와 governor 값이 불일치할 수 있습니다.

왜냐하면 `PuertoRicoGame._setup_players()` 는 governor를 기준으로 시작 plantation을 배분하기 때문입니다.

그래서 이번 구현에서는:

- `governor_idx` 옵션이 주어지면
- `env.reset(seed=...)` 를 반복 수행하면서
- 엔진 자체가 해당 governor를 선택한 초기 상태를 채택

이 방식으로 바꾸었습니다.

의미:

- `governor_idx` 와 초기 상태가 항상 일관됨
- 나중에 디버그/리플레이 재현에도 더 안전함

---

## 4. 실제 구현 범위

### 4-1. Frontend

대상 파일:

- `frontend/src/components/RoomListScreen.tsx`
- `frontend/src/App.tsx`
- `frontend/src/locales/ko.json`
- `frontend/src/locales/en.json`
- `frontend/src/locales/it.json`
- `frontend/src/test/setup.ts`
- `frontend/src/components/__tests__/RoomListScreen.test.tsx`

구현 내용:

- `RoomListScreen` 에 `봇전 구성` modal 추가
- `/api/bot-types` 를 로드해 3개의 select 슬롯에 bot type 표시
- `onCreateBotGame(botTypes)` 형태로 prop 계약 확장
- `App.handleCreateBotGame` 이 `bot_types` body를 포함해 API 호출하도록 변경
- 다국어 문구 추가
- component test 추가

### 4-2. Backend

대상 파일:

- `backend/app/engine_wrapper/wrapper.py`
- `backend/tests/test_governor_assignment.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_game_action.py`
- `backend/tests/test_gamelog_vp_doubloon.py`

구현 내용:

- `EngineWrapper` 에서 player_0 강제 governor 루프 제거
- `game_seed`, `governor_idx` 옵션 추가
- `governor_idx` 지정 시 reset retry 방식으로 일관된 초기 상태 확보
- 테스트를 player_0 고정 가정 대신 `state.meta.active_player` 기준으로 수정

---

## 5. TDD 관점에서의 체크포인트

이번 변경에서 고정한 테스트 관점은 다음과 같습니다.

### 5-1. UI 계약

- 사용자가 3개 bot slot을 선택할 수 있는가
- confirm 시 선택한 순서가 그대로 `onCreateBotGame([...])` 로 전달되는가

### 5-2. Engine 초기화 계약

- 같은 seed면 같은 governor/초기 setup이 재현되는가
- 여러 seed에서 governor가 한 사람으로 고정되지 않는가
- governor player가 엔진 규칙에 맞는 초기 plantation을 받는가
- 특정 governor override를 요청했을 때 일관된 초기 상태를 얻는가

### 5-3. 액션 API 회귀

- 시작 플레이어가 랜덤이어도 auth/action/logging 흐름이 유지되는가
- 액션 테스트가 더 이상 `player_0` 고정에 의존하지 않는가

---

## 6. 검증 결과

### 6-1. Frontend

실행:

- `npm test -- src/components/__tests__/RoomListScreen.test.tsx`
- `npm run build`

결과:

- component test 통과
- production build 통과

### 6-2. Backend

실행:

- focused regression:
  - `test_governor_assignment.py`
  - `test_auth.py`
  - `test_game_action.py`
  - `test_gamelog_vp_doubloon.py`
  - `test_phase_action_edge_cases.py`
  - `test_model_registry_bootstrap.py`
  - `test_model_version_snapshot.py`
  - `test_ml_logger.py`

결과:

- `81 passed`

추가 실행:

- `test_lobby_ws.py -k create_bot_game`

결과:

- `8 passed`

참고:

- `test_lobby_ws` 전체를 넓게 돌리면 `leave` 시 host transfer 관련 기존 실패 1건이 남아 있었음
- 이 실패는 이번 `bot-game selection` / `random governor` 변경과 직접 연결된 증상은 아님

---

## 7. 사용자 관점에서 바뀌는 실제 동작

### 봇전 생성

이전:

- `봇전` 버튼 클릭
- 무조건 `random, random, random`

이후:

- `봇전` 버튼 클릭
- modal에서 3개 슬롯 각각의 bot type 선택
- 예: `ppo`, `random`, `ppo`
- 그대로 관전용 bot game 생성

### 게임 시작 governor

이전:

- host/player_0가 사실상 항상 시작 governor

이후:

- 엔진이 랜덤하게 governor를 결정
- 시작 플레이어/초기 plantation 분배도 그 governor 기준으로 자연스럽게 결정

---

## 8. 남겨둔 확장 포인트

이번 설계는 장기적으로 실험형 구조로 가기 쉽게 열어두었습니다.

- 현재 UI는 `bot type` 을 고르지만, 나중에는 `policy tag` 또는 `model alias` 선택으로 확장 가능
- `EngineWrapper(game_seed=..., governor_idx=...)` 는 replay/debug 재현에 활용 가능
- governor를 특정 플레이어로 강제하는 디버그 모드가 필요할 때도 현재 구조를 재사용 가능

---

## 9. 결론

이번 작업으로 다음 두 가지가 해결되었습니다.

- 봇전 생성이 더 이상 `random x 3` 고정이 아니라 실제 조합 선택 가능한 UI가 됨
- 주지사 시작이 더 이상 host/player_0 고정이 아니라 엔진 규칙에 맞는 랜덤 시작으로 바뀜

동시에 테스트도 `player_0` 가정에서 벗어나도록 정리했기 때문에, 앞으로 bot/gameplay 실험을 할 때 시작 플레이어 랜덤화가 더 이상 숨은 회귀 포인트가 되지 않도록 기반을 맞춘 상태입니다.
