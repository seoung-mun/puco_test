# Castone Contract Document

작성일: 2026-04-06  
범위: `frontend` / `backend` / `PuCo_RL` / 모델 서빙 / Redis / DB / 파일 로그  
목적: 이 저장소의 컴포넌트 사이에서 실제로 유지되어야 하는 계약(contract)을 코드 기준으로 정리한다.

## 1. 문서 목적

이 문서는 다음 질문에 답하기 위해 만든다.

- 프론트엔드가 어떤 REST/WebSocket 계약에 의존하는가?
- 백엔드는 어떤 상태 스키마를 프론트에 보장해야 하는가?
- 백엔드와 엔진은 어떤 액션/상태/턴 계약으로 연결되는가?
- 봇 서빙과 모델 메타데이터는 어떤 형식으로 연결되는가?
- Redis, PostgreSQL, JSONL, replay JSON은 각각 무엇을 저장하며 어떤 역할을 가지는가?

이 문서는 "설명"보다 "유지보수용 합의문"에 가깝다.  
즉, 아래 계약 중 하나를 바꾸면 관련 계층을 같이 수정하고 테스트해야 한다.

## 2. 시스템 구성과 책임 경계

### 2.1 계층

- `frontend/`
  - 사용자 인터페이스
  - 인증 토큰 보관
  - 방/로비/게임 화면 전환
  - 액션 인덱스 전송
  - WebSocket 수신 상태 렌더링
- `backend/`
  - 인증
  - 방 관리
  - 게임 세션 관리
  - 엔진 호출
  - Redis 브로드캐스트
  - DB 및 파일 로그 저장
- `PuCo_RL/`
  - Puerto Rico 규칙 엔진
  - PettingZoo 환경
  - 액션 마스크 계산
  - 봇 추론 입력의 기준 상태
- `vis/`
  - 저장된 DB/JSONL/replay를 사람이 읽기 좋은 리포트로 변환

### 2.2 상태의 위치

한 판의 게임 상태는 한 군데에만 존재하지 않는다.

- 실제 진행 상태의 1차 소스
  - `GameService.active_engines[game_id]`
- 실시간 전달용 캐시
  - Redis `game:<game_id>:state`
- 운영 메타 정본
  - PostgreSQL `games`, `game_logs`
- ML/리플레이 보조 원본
  - `data/logs/games/<game_id>.jsonl`
  - `data/logs/replay/<game_id>.json`

### 2.3 소스 오브 트루스

- 게임 규칙/합법 액션 판단의 최종 소스
  - `PuCo_RL/env/pr_env.py`
  - `PuCo_RL/env/engine.py`
- 프론트가 받는 rich state 형식의 최종 소스
  - `backend/app/services/state_serializer.py`
- 프론트 타입 선언의 기대값
  - `frontend/src/types/gameState.ts`
- 액션 인덱스 체계의 실질적 소스
  - 엔진 action space
  - `backend/app/services/action_translator.py`
  - `frontend/src/App.tsx`의 `channelActionIndex`

## 3. 인증 계약

### 3.1 Google 로그인

프론트는 Google Sign-In에서 받은 `credential`을 아래 엔드포인트로 보낸다.

- `POST /api/puco/auth/google`

요청 body:

```json
{
  "credential": "<google-id-token>"
}
```

응답 body:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "user": {
    "id": "uuid-string",
    "nickname": "string|null",
    "email": "string|null",
    "total_games": 0,
    "win_rate": 0.0,
    "needs_nickname": true
  }
}
```

계약:

- JWT의 `sub`는 내부 `users.id`여야 한다.
- 프론트는 JWT를 `localStorage.access_token`에 저장한다.
- 닉네임이 없으면 `needs_nickname=true`를 받아 후속 설정 화면을 띄운다.

관련 파일:

- `backend/app/api/channel/auth.py`
- `backend/app/schemas/auth.py`
- `frontend/src/App.tsx`

### 3.2 현재 사용자 조회

- `GET /api/puco/auth/me`
- 헤더: `Authorization: Bearer <jwt>`

계약:

- 프론트의 앱 초기화는 이 응답 성공 여부에 의존한다.
- 실패 시 프론트는 로컬 토큰을 제거하고 로그인 화면으로 돌아간다.

### 3.3 닉네임 설정

- `PATCH /api/puco/auth/me/nickname`

요청 body:

```json
{
  "nickname": "2~20자, 영문/한글/숫자/_/-"
}
```

계약:

- DB 유니크 제약과 스키마 검증을 동시에 만족해야 한다.
- 같은 값으로 재설정은 idempotent로 취급한다.

## 4. 방(Room) 계약

채널 모드의 방 관련 REST API는 `/api/puco/rooms/*` 아래에 있다.

### 4.1 방 생성

- `POST /api/puco/rooms/`

요청 body:

```json
{
  "title": "room title",
  "is_private": false,
  "password": null
}
```

응답 body:

```json
{
  "id": "room-uuid",
  "title": "room title",
  "status": "WAITING",
  "is_private": false,
  "current_players": 1,
  "max_players": 3,
  "player_names": [
    {
      "display_name": "nickname",
      "is_bot": false
    }
  ]
}
```

계약:

- 생성 직후 `players`에는 host의 user id가 들어간다.
- 상태는 반드시 `WAITING`으로 시작한다.
- 현재 최대 플레이어 수는 항상 3이다.
- 비밀방이면 비밀번호는 4자리 숫자 문자열이어야 한다.

### 4.2 방 목록 조회

- `GET /api/puco/rooms/`

계약:

- 인증된 사용자만 조회할 수 있다.
- `status == "WAITING"`인 방만 노출한다.
- 프론트 `RoomListScreen`은 `player_names[].display_name`과 `is_bot`에 의존한다.

### 4.3 방 참가

- `POST /api/puco/rooms/{room_id}/join`

요청 body:

```json
{
  "password": null
}
```

계약:

- 이미 시작된 게임은 참가 불가다.
- 비밀방은 비밀번호 일치가 필요하다.
- 이미 방에 있는 사용자가 다시 join하면 idempotent하게 성공 응답한다.

### 4.4 방 나가기

- `POST /api/puco/rooms/{room_id}/leave`

계약:

- 실제 로직은 `handle_leave()`가 수행한다.
- WAITING 방과 PROGRESS 방에서 동작이 다르다.
- 이 로직은 로비 WebSocket disconnect 경로와 공유된다.

관련 파일:

- `backend/app/api/channel/room.py`
- `backend/app/services/lobby_manager.py`
- `frontend/src/components/RoomListScreen.tsx`

### 4.5 즉시 시작 봇전 생성

- `POST /api/puco/rooms/bot-game`

요청 body:

```json
{
  "bot_types": ["random", "ppo", "random"]
}
```

응답 body:

```json
{
  "game_id": "room-uuid",
  "state": { "...rich GameState..." }
}
```

계약:

- 이 엔드포인트는 room 생성과 game start를 한 번에 수행한다.
- `players`에는 인간이 아니라 `BOT_<type>` actor id만 들어간다.
- `host_id`는 인간 사용자 id이지만 실제 게임 플레이어 목록에는 포함되지 않을 수 있다.
- 현재 프론트는 이 경로를 "관전자 모드 시작"처럼 사용한다.

## 5. 로비 WebSocket 계약

### 5.1 접속

- 경로: `ws://<host>/api/puco/ws/lobby/{room_id}`
- 접속 직후 첫 메시지로 JWT 전송

첫 메시지 예시:

```json
{
  "token": "<jwt>"
}
```

계약:

- 서버는 5초 안에 인증 메시지를 받지 못하면 연결을 닫는다.
- room 상태가 `WAITING`이 아니거나, 사용자가 해당 room의 `players`에 없으면 접속 거부한다.

### 5.2 서버 -> 클라이언트 메시지

`LOBBY_STATE` / `LOBBY_UPDATE`

```json
{
  "type": "LOBBY_STATE",
  "players": [
    {
      "name": "nickname",
      "player_id": "uuid-or-bot-id",
      "is_bot": false,
      "is_host": true,
      "connected": true
    }
  ],
  "host_id": "host-user-id"
}
```

`ROOM_DELETED`

```json
{
  "type": "ROOM_DELETED"
}
```

`GAME_STARTED`

```json
{
  "type": "GAME_STARTED",
  "state": { "...rich GameState..." }
}
```

계약:

- 프론트는 `GAME_STARTED` 수신 시 로비 소켓을 닫고 게임 화면으로 전환한다.
- 프론트의 `host` 판단은 `players[].is_host`에서 계산된다.
- `connected`는 로비 UI의 시작 가능 조건 계산에 사용된다.

관련 파일:

- `backend/app/api/channel/lobby_ws.py`
- `backend/app/services/lobby_manager.py`
- `frontend/src/App.tsx`
- `frontend/src/components/LobbyScreen.tsx`

## 6. 게임 WebSocket 계약

### 6.1 접속

- 경로: `ws://<host>/api/puco/ws/{game_id}`
- 첫 메시지는 반드시 JWT 인증이어야 한다.

첫 메시지 예시:

```json
{
  "token": "<jwt>"
}
```

서버의 인증 성공 응답:

```json
{
  "type": "auth_ok",
  "player_id": "<user-id>"
}
```

계약:

- 프론트 `useGameWebSocket()`는 접속 직후 첫 메시지로 토큰을 전송한다.
- 서버는 URL query가 아니라 first-message auth 방식을 사용한다.
- 인증 실패 시 close code `1008`로 닫는다.
- 인증 성공 후에도 해당 사용자는 이 게임의 player 또는 host여야 한다.
- bot-only 관전 게임에서는 host spectator가 허용된다.

### 6.2 서버 -> 클라이언트 메시지

`STATE_UPDATE`

```json
{
  "type": "STATE_UPDATE",
  "data": { "...rich GameState..." }
}
```

또는 legacy/fallback 경로에서:

```json
{
  "type": "STATE_UPDATE",
  "data": { "...rich GameState..." },
  "action_mask": [0, 1, 0, 1]
}
```

`GAME_ENDED`

```json
{
  "type": "GAME_ENDED",
  "reason": "player_request|player_disconnect_timeout|..."
}
```

`PLAYER_DISCONNECTED`

```json
{
  "type": "PLAYER_DISCONNECTED",
  "player_id": "<user-id>",
  "message": "Player ... has disconnected.",
  "options": ["end_game", "wait"],
  "timeout_seconds": 600
}
```

계약:

- 프론트는 `STATE_UPDATE` 중복 수신을 JSON 직렬화 기준으로 dedupe한다.
- `action_mask`는 top-level에 오거나 `data.action_mask` 안에 포함될 수 있다.
- disconnect 경고 메시지는 멀티휴먼 게임에서만 `options`와 `timeout_seconds`를 가진다.

### 6.3 클라이언트 -> 서버 메시지

현재 명시적으로 처리하는 클라이언트 메시지:

```json
{
  "type": "END_GAME_REQUEST"
}
```

계약:

- 서버는 이 메시지를 받으면 DB 상태를 `FINISHED`로 바꾸고 `GAME_ENDED`를 브로드캐스트한다.

관련 파일:

- `backend/app/api/channel/ws.py`
- `backend/app/services/ws_manager.py`
- `frontend/src/hooks/useGameWebSocket.ts`

## 7. GameState 계약

프론트가 렌더링하는 핵심 상태는 `rich GameState JSON`이다.

실제 런타임 소스:

- `backend/app/services/state_serializer.py`

프론트 타입 기대값:

- `frontend/src/types/gameState.ts`

### 7.1 상위 구조

```json
{
  "meta": { "...meta..." },
  "common_board": { "...common board..." },
  "players": {
    "player_0": { "...player..." },
    "player_1": { "...player..." }
  },
  "decision": { "...decision..." },
  "history": [],
  "bot_players": {
    "player_1": "ppo"
  },
  "result_summary": null,
  "action_mask": [0, 1, 1]
}
```

계약:

- 채널 API의 실제 응답에는 `action_mask`가 포함된다.
- 프론트 `GameState` 타입은 `action_mask?: number[]`를 포함한다.
- `players`의 key는 항상 `player_{idx}` 형식이다.
- `meta.active_player`, `meta.governor`, `meta.player_order[]`는 모두 같은 naming scheme을 따라야 한다.

### 7.2 meta 계약

주요 필드:

- `game_id`
- `round`
- `step_count`
- `num_players`
- `player_order`
- `governor`
- `phase`
- `phase_id`
- `active_role`
- `active_player`
- `end_game_triggered`
- `end_game_reason`
- `vp_supply_remaining`
- `captain_consecutive_passes`
- `bot_thinking`
- `mayor_slot_idx`
- `mayor_can_skip`
- `pass_action_index`
- `hacienda_action_index`

계약:

- `phase`는 프론트가 문자열 phase 이름으로 UI 분기한다.
- `active_player`는 반드시 `player_n` 형식이어야 한다.
- `pass_action_index` 기본값은 `15`다.
- `hacienda_action_index` 기본값은 `105`다.
- `mayor_can_skip`는 현재 action mask의 69번 인덱스 해석에 의존한다.

### 7.3 common_board 계약

핵심 필드:

- `roles`
- `colonists`
- `trading_house`
- `cargo_ships`
- `available_plantations`
- `available_buildings`
- `quarry_supply_remaining`
- `goods_supply`

계약:

- 사용 가능한 role/building/face_up plantation에는 가능한 경우 `action_index`를 싣는다.
- 프론트는 가능한 한 이 `action_index`를 직접 사용해야 하며, 이름 기반 계산보다 서버 값을 신뢰하는 편이 안전하다.

### 7.4 players 계약

각 플레이어 객체는 다음을 포함한다.

- `display_name`
- `display_number`
- `is_governor`
- `doubloons`
- `vp_chips`
- `goods`
- `island`
- `city`
- `production`
- `warehouse`
- `captain_first_load_done`
- `wharf_used_this_phase`
- `hacienda_used_this_phase`

계약:

- `display_name`은 프론트에 표시되는 이름이다.
- `display_number`는 governor 기준 회전 순서다.
- island/city 내부의 `slot_id`는 Mayor 배치 API에서 사용되는 식별자와 연결된다.

### 7.5 history 계약

프론트 기대 타입:

```json
{
  "ts": 1712345678,
  "action": "select_role",
  "params": {
    "player": "name",
    "role": "builder"
  }
}
```

계약:

- 프론트 팝업/히스토리 렌더링은 `action`과 `params` 문자열 키에 의존한다.
- history action 이름을 바꾸면 i18n 키와 UI 팝업도 같이 수정해야 한다.

## 8. 액션 인덱스 계약

가장 중요한 계약 중 하나다.  
프론트 버튼, 백엔드 검증, 엔진 action mask, RL 모델의 행동 의미가 모두 같은 정수 인덱스를 가리켜야 한다.

### 8.1 인덱스 범위

- `0-7`: role 선택
- `8-13`: face-up plantation 선택
- `14`: quarry 선택
- `15`: pass
- `16-38`: build
- `39-43`: trader sell
- `44-58`: captain load ship
- `59-63`: captain wharf
- `64-68`: captain windrose 저장
- `69-80`: mayor island slot toggle/amount
- `81-92`: mayor city slot toggle
- `93-97`: craftsman privilege
- `105`: hacienda draw
- `106-110`: captain warehouse 저장

실질적 관련 파일:

- `PuCo_RL` 엔진 action space
- `backend/app/services/action_translator.py`
- `backend/app/services/state_serializer.py`
- `frontend/src/App.tsx`

### 8.2 프론트 규칙

프론트는 두 가지 방식으로 action index를 얻는다.

1. 서버가 state 안에 내려준 `action_index`
2. 프론트의 `channelActionIndex` 계산 함수

권장 계약:

- role/build/building/face-up plantation처럼 서버가 `action_index`를 내려주는 경우 그 값을 우선 사용한다.
- sell/load/warehouse처럼 파생 계산이 필요한 경우 프론트 계산 함수는 백엔드 번역기와 같은 규칙을 유지해야 한다.

### 8.3 변경 시 같이 수정해야 하는 곳

액션 공간을 바꾸면 반드시 같이 점검해야 한다.

- `PuCo_RL/env/pr_env.py`
- `backend/app/services/action_translator.py`
- `backend/app/services/state_serializer.py`
- `frontend/src/App.tsx`
- 관련 테스트 전체

## 9. Mayor 계약

Mayor는 일반 액션보다 별도 계약이 많다.

### 9.1 slot_id 계약

서버 serializer는 Mayor 슬롯 식별자를 아래처럼 만든다.

- island: `island:<tile_type>:<index>`
- city: `city:<building_name>:<index>`

생성 함수:

- `backend/app/services/mayor_orchestrator.py`

프론트는 이 `slot_id`를 그대로 `mayor-distribute` API에 보내야 한다.

### 9.2 modern API

- `POST /api/puco/game/{game_id}/mayor-distribute`

요청 body:

```json
{
  "placements": [
    {
      "slot_id": "island:corn:0",
      "count": 1
    }
  ]
}
```

계약:

- `slot_id`는 반드시 현재 플레이어의 현재 Mayor 슬롯 카탈로그에 있어야 한다.
- `count`는 `0 <= count <= 3`
- 각 `slot_id`는 중복되면 안 된다.
- 총 배치 수는 현재 플레이어의 `unplaced_colonists`를 초과하면 안 된다.
- 실제 엔진 적용은 `translate_plan_to_actions()`를 거쳐 Mayor action sequence로 변환된다.

### 9.3 legacy API

- `POST /api/action/mayor-distribute`

요청 body:

```json
{
  "player": "P0",
  "distribution": [0, 1, 0, ... 24개]
}
```

계약:

- legacy는 길이 24의 배열을 사용한다.
- channel API 프론트는 이 계약을 직접 쓰지 않는다.
- 하지만 테스트와 일부 진단 흐름에서 아직 중요하다.

## 10. 게임 액션 REST 계약

### 10.1 일반 액션

- `POST /api/puco/game/{game_id}/action`

요청 body:

```json
{
  "payload": {
    "action_index": 39
  }
}
```

응답 body:

```json
{
  "status": "success",
  "state": { "...rich GameState..." },
  "action_mask": [0, 1, 0]
}
```

계약:

- caller는 반드시 해당 game의 `players` 목록 안에 있어야 한다.
- 실제 현재 턴 플레이어 검증은 `GameService.process_action()`에서 수행한다.
- 액션 요청의 주체는 요청을 보낸 사용자 자신이 아니라 `state.meta.active_player`와 매칭되는 actor여야 한다.
- 혼합 방에서는 `active_player`가 봇일 수 있으므로, 프론트/테스트는 "방장/처음 로그인한 유저가 첫 턴"이라고 가정하면 안 된다.
- action은 현재 action mask에서 valid여야 한다.

### 10.2 게임 시작

- `POST /api/puco/game/{game_id}/start`

계약:

- host만 시작할 수 있다.
- 최소 3 player가 있어야 한다.
- 시작 시 엔진이 생성되고 `games.status`는 `PROGRESS`가 된다.
- `/start` 응답의 `action_mask`는 시작 요청자의 것이 아니라 시작 직후 `state.meta.active_player`에게 유효한 마스크다.
- 동시에 lobby WS에는 `GAME_STARTED`가 전송된다.

### 10.3 봇 추가

- `POST /api/puco/game/{game_id}/add-bot`

요청 body:

```json
{
  "bot_type": "ppo"
}
```

계약:

- host만 호출 가능
- `WAITING` 상태에서만 가능
- 최대 player 수 3 제한을 따른다

### 10.4 최종 점수 조회

- `GET /api/puco/game/{game_id}/final-score`

계약:

- player 또는 host만 조회 가능하다.
- 응답은 `compute_score_breakdown()` 형식을 따른다.
- 프론트는 `state.result_summary`가 비어 있을 때만 이 API를 후속 호출한다.

## 11. 프론트 화면 전이 계약

### 11.1 screen 상태

프론트는 명시적 라우터 대신 내부 screen state를 사용한다.

- `loading`
- `login`
- `home`
- `rooms`
- `join`
- `lobby`
- `game`

계약:

- 인증 성공 후 기본 진입 화면은 `rooms`
- room 생성/참가 후 `lobby`
- `GAME_STARTED` 또는 start 응답 성공 후 `game`
- leave/back 후 `rooms`

관련 파일:

- `frontend/src/App.tsx`

### 11.2 내 턴 판별 계약

프론트는 아래 조건으로 사용자의 행동 가능 여부를 판단한다.

- 멀티플레이 중이고
- `myPlayerId === state.meta.active_player`

계약:

- `myPlayerId`는 `GameState.players`를 순회하며 `display_name === myName`으로 추론하는 경로가 있다.
- 따라서 `display_name` 중복은 현재 프론트 식별에 취약할 수 있다.
- `JoinScreen`의 spectator 선택 UI는 존재하지만, 현재 channel API에서는 실질적으로 완전 지원되지 않는다.

## 12. 봇 서빙 계약

### 12.1 bot_type

공식 bot type:

- `ppo`
- `hppo`
- `random`

등록 위치:

- `backend/app/services/agent_registry.py`

계약:

- room/session에는 실제 actor id가 `BOT_<bot_type>` 형태로 저장된다.
- 프론트/백엔드 API는 bot type 문자열만 알면 된다.
- 실제 checkpoint 해석은 agent registry가 담당한다.

### 12.2 모델 메타데이터

백엔드가 서빙용 모델을 해석할 때 요구하는 메타:

- `family`
- `policy_tag`
- `artifact_name`
- `checkpoint_filename`
- `architecture`
- `obs_dim`
- `action_dim`
- `num_players`

우선순위:

1. sidecar JSON
2. 제한적 bootstrap derived metadata
3. 일부 family는 static fallback

관련 파일:

- `backend/app/services/model_registry.py`
- `backend/app/services/agent_registry.py`

계약:

- `obs_dim`은 현재 flatten된 env observation과 일치해야 한다.
- `action_dim`은 현재 200을 기대한다.
- `architecture`는 wrapper가 이해하는 family와 호환되어야 한다.

### 12.3 런타임 model_versions snapshot

게임 시작 시 `games.model_versions`에 player별 snapshot을 저장한다.

예시:

```json
{
  "player_0": {
    "actor_type": "human",
    "player_id": "uuid"
  },
  "player_1": {
    "actor_type": "bot",
    "bot_type": "ppo",
    "family": "ppo",
    "policy_tag": "champion",
    "artifact_name": "PPO_PR_Server_...",
    "checkpoint_filename": "PPO_PR_Server_....pth",
    "architecture": "ppo_residual",
    "metadata_source": "sidecar"
  }
}
```

계약:

- replay JSON과 rich state는 이 스냅샷을 노출한다.
- 게임 시작 후 모델 버전 추적은 이 snapshot 기준으로 한다.

## 13. 엔진 래퍼 계약

`EngineWrapper`는 FastAPI 서비스와 PettingZoo 엔진 사이의 경계다.

### 13.1 제공 메서드

- `get_state()`
- `get_action_mask()`
- `step(action)`

### 13.2 `step()` 반환 계약

```json
{
  "state_before": {},
  "action": 39,
  "action_mask": [0, 1, 0],
  "state_after": {},
  "reward": 0.0,
  "done": false,
  "terminated": false,
  "truncated": false,
  "info": {
    "current_phase_id": 3,
    "current_player_idx": 1,
    "step_count": 12,
    "round": 2,
    "step": 12
  }
}
```

계약:

- `reward`는 float 또는 float list로 직렬화 가능해야 한다.
- `action_mask`는 action 적용 전의 mask다.
- `current_phase_id`, `current_player_idx`, `step_count`는 후속 로그/봇 추론에 사용된다.

관련 파일:

- `backend/app/engine_wrapper/wrapper.py`

## 14. Redis 계약

### 14.1 키

- `game:<game_id>:state`
  - 최신 rich state JSON
- `game:<game_id>:events`
  - pub/sub channel
- `game:<game_id>:meta`
  - hash
  - `status`, `human_count`, `num_players`
- `game:<game_id>:players`
  - hash
  - `<player_id> -> connected|disconnected`

### 14.2 TTL

- 진행 중 상태
  - 보통 900초
- 종료 후 상태
  - 보통 300초

계약:

- Redis는 캐시/브로드캐스트 레이어이지 정본 저장소가 아니다.
- WebSocket listener는 `game:<game_id>:events`의 `STATE_UPDATE`를 받아 fan-out한다.

관련 파일:

- `backend/app/services/game_service.py`
- `backend/app/services/ws_manager.py`
- `backend/app/core/redis.py`

## 15. PostgreSQL 계약

### 15.1 `users`

- 인증 사용자 정본

핵심 필드:

- `id`
- `google_id`
- `email`
- `nickname`
- `total_games`
- `win_rate`

### 15.2 `games`

한 room/game session의 메타데이터 정본

핵심 필드:

- `id`
- `title`
- `status`
- `num_players`
- `is_private`
- `password`
- `players`
- `model_versions`
- `winner_id`
- `host_id`

### 15.3 `game_logs`

액션 단위 감사 로그

핵심 필드:

- `game_id`
- `round`
- `step`
- `actor_id`
- `action_data`
- `available_options`
- `state_before`
- `state_after`
- `state_summary`

계약:

- `state_summary`는 Adminer에서 읽기 쉬운 compact summary다.
- 정밀 분석은 `state_before`/`state_after` 또는 JSONL 로그를 사용한다.

관련 파일:

- `backend/app/db/models.py`

## 16. 파일 로그 계약

### 16.1 JSONL transition 로그

경로:

- `data/logs/games/<game_id>.jsonl`

레코드 형식:

```json
{
  "timestamp": "2026-04-06T00:00:00Z",
  "game_id": "uuid",
  "actor_id": "uuid-or-bot-id",
  "state_before": {},
  "action": 39,
  "reward": 0.0,
  "done": false,
  "state_after": {},
  "info": {},
  "action_mask_before": [],
  "phase_id_before": 3,
  "current_player_idx_before": 1,
  "model_info": {}
}
```

계약:

- ML 재학습/lineage 추적용 원본이다.
- DB와 달리 per-step raw transition을 더 직접적으로 보존한다.

관련 파일:

- `backend/app/services/ml_logger.py`

### 16.2 replay JSON

경로:

- `data/logs/replay/<game_id>.json`

format:

- `backend-replay.v1`

상위 필드:

- `game_id`
- `title`
- `status`
- `host_id`
- `num_players`
- `players`
- `model_versions`
- `initial_state_summary`
- `total_steps`
- `final_scores`
- `result_summary`
- `entries`

`entries[]` 핵심 필드:

- `step`
- `round`
- `player`
- `actor_id`
- `actor_name`
- `phase`
- `phase_id`
- `action_id`
- `action`
- `reward`
- `done`
- `valid_action_count`
- `commentary`
- `state_summary_before`
- `state_summary_after`
- 선택적으로 `model_info`
- role 선택이면 `role_selected`

관련 파일:

- `backend/app/services/replay_logger.py`

## 17. legacy API 계약

현재 프론트의 주 경로는 channel API이지만, 일부 보조 호출은 아직 legacy API를 쓴다.

### 17.1 현재 프론트에서 쓰는 legacy 경로

- `GET /api/bot-types`

계약:

- 응답 형식:

```json
[
  { "type": "ppo", "name": "PPO Bot" },
  { "type": "random", "name": "Random Bot" }
]
```

프론트 사용처:

- `RoomListScreen`
- `LobbyScreen`

### 17.2 legacy write endpoint의 인증

일부 legacy write endpoint는 `X-API-Key` 헤더를 요구한다.

관련:

- `backend/app/api/legacy/deps.py`
- `frontend/src/App.tsx`의 `apiFetch()`

계약:

- `INTERNAL_API_KEY`가 서버에 설정되어 있으면 일치 검증을 수행한다.
- 현재 프론트는 `VITE_INTERNAL_API_KEY`를 번들에 넣는 구조를 갖고 있어, 외부 공개 전 재검토가 필요하다.

## 18. 변경 시 체크리스트

### 18.1 액션 공간 변경

반드시 같이 점검:

- `PuCo_RL` action space
- `backend/app/services/action_translator.py`
- `backend/app/services/state_serializer.py`
- `frontend/src/App.tsx`
- 프론트/백엔드 테스트

### 18.2 rich state 필드 변경

반드시 같이 점검:

- `backend/app/services/state_serializer.py`
- `frontend/src/types/gameState.ts`
- 실제 렌더링 컴포넌트
- replay/DB summary 영향 여부

### 18.3 WebSocket 메시지 타입 변경

반드시 같이 점검:

- `backend/app/api/channel/ws.py`
- `backend/app/api/channel/lobby_ws.py`
- `backend/app/services/ws_manager.py`
- `frontend/src/hooks/useGameWebSocket.ts`
- `frontend/src/App.tsx`

### 18.4 모델 메타데이터 스키마 변경

반드시 같이 점검:

- `backend/app/services/model_registry.py`
- `backend/app/services/agent_registry.py`
- sidecar 생성 흐름
- 실제 checkpoint와 obs/action dimension 호환성

## 19. 현재 알려진 주의점

이 문서는 계약을 정리한 문서이지만, 현재 코드베이스에서 계약 드리프트 위험이 있는 부분도 같이 명시한다.

- Mayor legacy contract와 current engine behavior 사이에 테스트 드리프트가 있다.
- `frontend/src/i18n.ts`는 import 시점 `localStorage` 접근이 있어 비브라우저 테스트 환경에서 깨질 수 있다.
- 로비 WS 종료와 `handle_leave()`가 같은 경로를 사용하므로, 게임 시작 직후 로비 소켓 종료가 실제 leave처럼 동작하지 않도록 주의해야 한다.
- 종료 상태는 DB, Redis, 메모리 엔진, replay가 모두 함께 일관되게 마감되어야 한다.

## 20. 문서 갱신 원칙

아래 중 하나를 변경했다면 이 문서를 같이 갱신하는 것을 권장한다.

- API path / payload
- WebSocket message type / payload
- GameState field shape
- action index meaning
- bot_type / model metadata schema
- Redis key / TTL policy
- replay / JSONL schema

이 문서가 최신이 아니면, 새로운 유지보수자가 가장 먼저 잘못 이해하는 지점은 거의 항상 "프론트가 기대하는 상태 모양"과 "실제 엔진이 보장하는 액션 의미"다.
