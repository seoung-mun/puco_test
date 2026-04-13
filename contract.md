# Castone Contract Document

작성일: 2026-04-09
범위: `frontend` / `backend` / `PuCo_RL` / Redis / PostgreSQL / replay/logging
목적: 현재 코드 기준으로 실제 유지해야 하는 supported contract만 정리한다.

보조 문서:

- `design/2026-04-08_engine_cutover_phase2_contract_followup.md`
- `design/2026-04-08_engine_cutover_batch_f_cleanup.md`

## 1. Source Of Truth

- 게임 규칙과 합법 액션의 최종 소스
  - `PuCo_RL/env/engine.py`
  - `PuCo_RL/env/pr_env.py`
- backend의 canonical engine 생성 경계
  - `backend/app/services/engine_gateway/factory.py`
  - `backend/app/services/game_service.py`
- 프론트에 전달되는 rich `GameState`의 최종 소스
  - serializer core: `backend/app/services/state_serializer.py`
  - channel state assembly: `backend/app/services/game_service_support.py`
- 액션 인덱스 번역의 최종 소스
  - `backend/app/services/action_translator.py`
- 프론트 타입 기대값
  - `frontend/src/types/gameState.ts`

계약이 충돌하면 엔진 규칙 > serializer / game service state assembly > 프론트 타입 순으로 맞춘다.

## 2. Supported Public Interfaces

### 2.1 Auth

- `POST /api/puco/auth/google`
  - 요청: `{ "credential": "<google-id-token>" }`
  - 응답: `{ "access_token": "...", "token_type": "bearer", "user": { ... } }`
- `GET /api/puco/auth/me`
- `PATCH /api/puco/auth/me/nickname`

계약:

- JWT `sub`는 내부 `users.id`다.
- `google` 로그인 응답과 `me` 응답의 `user`에는 `needs_nickname`이 포함된다.
- `needs_nickname=true`면 프론트는 닉네임 설정 UI를 띄운다.
- 닉네임은 전역 unique이며, 같은 값으로 다시 설정하는 요청은 idempotent하게 성공한다.

### 2.2 Rooms

- `POST /api/puco/rooms/`
- `GET /api/puco/rooms/`
- `POST /api/puco/rooms/{room_id}/join`
- `POST /api/puco/rooms/{room_id}/leave`
- `POST /api/puco/rooms/bot-game`

계약:

- 모든 채널 room REST는 bearer 인증이 필요하다.
- 최대 플레이어 수는 현재 3명이다.
- room title uniqueness는 `WAITING` 방에 대해서만, 대소문자 무시 기준으로 적용된다.
- 한 사용자는 동시에 하나의 `WAITING` 방만 host할 수 있다.
- private room 비밀번호는 4자리 숫자 문자열이다.
- room 응답의 `player_names[]`는 `{ display_name, is_bot }`를 가진다.
- `GET /rooms/`는 `WAITING` 방만 노출한다.
- `join`은 이미 방에 있는 사용자가 다시 호출하면 idempotent하게 현재 room 상태를 반환한다.
- `leave`는 현재 room에 없는 사용자가 호출해도 idempotent하게 `{ "status": "ok" }`를 반환할 수 있다.
- `/bot-game`은 즉시 시작되는 봇 전용 관전자형 게임 생성 경로다.
- `/bot-game`의 기본 `bot_types`는 `["random", "random", "random"]`이다.
- `/bot-game`으로 만들어진 room은 `players`에 인간 대신 `BOT_<bot_type>` actor id만 저장하고, `host_id`는 관전자 human id로 유지한다.

### 2.3 Lobby WebSocket

- 엔드포인트: `GET ws /api/puco/ws/lobby/{room_id}`
- 연결 직후 5초 안에 JWT가 든 첫 text message를 보내야 한다.
  - 지원 키: `token`, `accessToken`
- 이 소켓은 `WAITING` room의 실제 member만 연결할 수 있다.

주요 서버 발행 메시지:

- `LOBBY_STATE`
- `LOBBY_UPDATE`
- `GAME_STARTED`
- `ROOM_DELETED`
- `PING`

계약:

- `LOBBY_STATE` / `LOBBY_UPDATE` payload에는 `players[]`와 `host_id`가 포함된다.
- lobby payload의 bot 항목은 `is_bot`, `is_host`, `connected`를 포함한다.
- `GAME_STARTED`는 lobby WebSocket에서 발행되며, game WebSocket 메시지가 아니다.
- 게임 시작 후 lobby socket이 닫히는 것은 leave가 아니라 화면 전환으로 취급한다.

### 2.4 Game REST

- `POST /api/puco/game/{game_id}/start`
- `POST /api/puco/game/{game_id}/action`
- `POST /api/puco/game/{game_id}/add-bot`
- `DELETE /api/puco/game/{game_id}/bots/{slot_index}`
- `GET /api/puco/game/{game_id}/final-score`

계약:

- `start`는 host만 호출할 수 있다.
- `start`는 실제 `players` 길이가 3 이상일 때만 성공한다.
- bot-only spectator room에서는 host가 `players` 바깥에 있어도 `start`와 `final-score` 접근이 허용된다.
- 일반 액션은 `payload.action_index` 정수 하나로 전달한다.
- `action` 호출자는 room의 실제 `players` 멤버여야 하며, 현재 턴 actor와 일치해야 한다.
- Mayor는 human / bot 공통으로 `POST /action`에 slot-direct action index (`120-131` island, `140-151` city)를 보낸다. 한 번 호출에 colonist 1명씩 순차 배치한다.
- `add-bot` / `remove-bot`은 host만 가능하고 `WAITING` room에서만 허용된다.
- `add-bot`의 `bot_type` 기본값은 `random`이다.
- `final-score`는 player 또는 host만 조회 가능하며, active engine이 없으면 404가 날 수 있다.

### 2.5 Game WebSocket

- 엔드포인트: `GET ws /api/puco/ws/{game_id}`
- 연결 직후 5초 안에 첫 JSON 메시지로 JWT를 보내야 한다.
  - 지원 키: `token`, `accessToken`
- 인증 성공 시 서버는 `{ "type": "auth_ok", "player_id": "<user-id>" }`를 보낸다.

클라이언트 발행 메시지:

- `END_GAME_REQUEST`

주요 서버 발행 메시지:

- `STATE_UPDATE`
  - channel path shape: `{ "type": "STATE_UPDATE", "data": <GameState> }`
- `PLAYER_DISCONNECTED`
- `GAME_ENDED`

계약:

- game WebSocket은 room player 또는 host spectator만 연결할 수 있다.
- `STATE_UPDATE`의 canonical action mask는 `data.action_mask`다.
- legacy / fallback 경로는 top-level `action_mask`를 실어 보낼 수 있지만, 정식 channel contract는 rich state 내부 mask다.
- `PLAYER_DISCONNECTED`는 멀티휴먼 게임일 때만 `options`, `timeout_seconds`를 포함한다.
- disconnect timeout은 현재 600초다.

### 2.6 Legacy Compatibility

- `GET /api/bot-types`

계약:

- 프론트의 room / lobby 화면은 아직 이 경로를 사용한다.
- 응답 shape는 `[{ "type": "...", "name": "..." }]`다.
- 이 문서의 주 계약은 channel API이지만, `bot-types`는 현재 지원 중인 호환 경로로 유지한다.

## 3. GameState Contract

현재 channel rich state(`build_rich_state`)가 보장하는 top-level 키:

- `meta`
- `common_board`
- `players`
- `decision`
- `history`
- `bot_players`
- `result_summary`
- `action_mask`
- `model_versions`

참고:

- `state_serializer.py`의 core serializer는 위 구조 대부분을 만들고,
- `model_versions`는 `backend/app/services/game_service_support.py`가 마지막에 붙인다.

### 3.1 `meta`

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
- `players_acted_this_phase`
- `end_game_triggered`
- `end_game_reason`
- `vp_supply_remaining`
- `captain_consecutive_passes`
- `bot_thinking`
- `pass_action_index`
- `hacienda_action_index`

계약:

- `phase`는 현재 backend에서 아래 문자열만 emit한다.
  - `role_selection`
  - `settler_action`
  - `mayor_action`
  - `builder_action`
  - `craftsman_action`
  - `trader_action`
  - `captain_action`
  - `captain_discard`
  - `game_over`
- 프론트 타입의 `end_of_round`는 legacy union 잔재이며 현재 backend emit 값이 아니다.
- `active_player`, `governor`, `player_order[]`는 모두 `player_<idx>` naming scheme을 따른다.
- `phase_id`는 엔진 `Phase` enum 정수다.
- `pass_action_index`는 항상 `15`다.
- `hacienda_action_index`는 항상 `105`다.
- Mayor phase일 때 추가 convenience fields:
  - `mayor_phase_mode`: `"slot-direct"` (고정)
  - `mayor_remaining_colonists`: 현재 플레이어의 남은 배치 colonist 수
  - `mayor_legal_island_slots`: 합법 island slot index 배열 (예: `[0, 2, 5]`)
  - `mayor_legal_city_slots`: 합법 city slot index 배열 (예: `[1, 4]`)
- 과거 cursor용 `mayor_slot_idx`, `mayor_can_skip`는 포함되지 않는다.

### 3.2 `common_board`

주요 필드:

- `roles`
- `colonists`
- `trading_house`
- `cargo_ships`
- `available_plantations`
- `available_buildings`
- `quarry_supply_remaining`
- `goods_supply`

계약:

- 사용 가능한 `roles[*]`에는 `action_index`가 포함되며 범위는 `0-7`이다.
- `available_plantations.face_up[*]`는 문자열이 아니라 `{ type, action_index }` 객체다.
- 일반 plantation slot의 `action_index`는 `8-13`, quarry는 `14`다.
- `available_buildings[*].action_index`는 build 번역용 인덱스이며 범위는 `16-38`이다.
- `action_index`가 있다고 해서 현재 그 액션이 legal하다는 뜻은 아니다.
- 현재 legal 여부의 최종 판단은 `action_mask`와 backend 검증이 한다.

### 3.3 `common_board.available_buildings`

키 계약은 canonical snake_case다.

예:

- `small_indigo_plant`
- `small_sugar_mill`
- `guild_hall`
- `customs_house`
- `city_hall`

각 항목 필드:

- `cost`
- `max_colonists`
- `vp`
- `copies_remaining`
- `action_index`

계약:

- 출력 serializer에서는 `guildhall` 같은 구키를 노출하지 않는다.
- 입력 파서는 legacy alias를 normalize할 수 있지만, public output contract는 snake_case다.

### 3.4 `players`

각 player 객체는 다음 필드를 가진다.

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

- `display_number`는 governor-relative 순번이며, 같은 state 안에서 unique한 `1..n`이다.
- `is_governor`는 `meta.governor`와 일치해야 한다.

### 3.5 Slot Id

- `players[*].city.buildings[*].slot_id` 형식은 `city:<building_name>:<index>`다.
  - 예: `city:guild_hall:0`
- `players[*].island.plantations[*].slot_id` 형식은 `island:<tile_name>:<index>`다.
  - 예: `island:corn:0`

계약:

- slot id는 보드 상태 설명용 serializer 필드다.
- 현재 supported public action submission은 slot id가 아니라 `payload.action_index` 기반이다.

### 3.6 `result_summary`

terminal state에서 `result_summary`는 다음 구조를 따른다.

- `scores`
- `winner`
- `player_order`
- `display_names`

계약:

- `scores`와 `winner`는 stable player ref(`player_0`, `player_1`, ...) 기준이다.
- display name이 중복돼도 stable ref가 깨지지 않아야 한다.

### 3.7 `model_versions`

`model_versions`는 game start 시 room snapshot으로 생성되며 `player_<idx>` key를 쓴다.

주요 필드:

- `actor_type`
- `player_id` or `bot_type`
- `artifact_name`
- `metadata_source`
- `fingerprint`

계약:

- human actor도 `model_versions`에 별도 snapshot을 가진다.
- bot actor는 `bot_type`과 artifact fingerprint가 포함된다.

## 4. Action Contract

현재 supported action space:

- `0-7`: role selection
- `8-13`: face-up plantation pick
- `14`: quarry pick
- `15`: pass
- `16-38`: build
- `39-43`: trade house sell
- `44-58`: captain ship load
- `59-63`: captain wharf load
- `64-68`: captain windrose keep
- `69-71`: (reserved legacy — no longer Mayor public contract)
- `93-97`: craftsman privilege
- `105`: hacienda draw
- `106-110`: captain warehouse keep
- `120-131`: Mayor sequential island slot placement (slot 0-11)
- `140-151`: Mayor sequential city slot placement (slot 0-11)

### 4.1 Mayor

현재 supported Mayor contract:

- Human / Bot 공통 slot-direct sequential placement
- `120-131`: island slot 0-11에 colonist 1명 배치
- `140-151`: city slot 0-11에 colonist 1명 배치
- 각 배치는 `POST /api/puco/game/{game_id}/action`으로 1회 호출한다.
- 이미 점유된 slot이나 capacity가 찬 building에 대한 action은 400 에러다.
- unplaced colonists가 0이 되거나 legal slot이 없으면 자동으로 다음 player로 넘어간다.
- 한번 확정된 배치는 되돌릴 수 없다.

명시적 비지원:

- `69-71`: Mayor strategy band (legacy, 더 이상 Mayor public contract가 아님)
- `POST /api/puco/game/{game_id}/mayor-distribute` (410 Gone)
- cursor metadata (`mayor_slot_idx`, `mayor_can_skip`)

### 4.2 Settler Guard

계약:

- 일반 plantation pick이 가능한 Settler 상황에서는 backend guard가 `action_mask[15]`를 `0`으로 내려 pass를 막는다.
- 즉, Settler의 pass 가능 여부는 raw engine mask가 아니라 backend-guarded mask 기준으로 해석한다.

### 4.3 Builder

Builder phase 유효성 계약:

- 도시 빈칸이 0이면 모든 build action은 막혀야 한다.
- 대형 건물은 도시 2칸이 필요하다.
- 현재 대형 건물:
  - `guild_hall`
  - `residence`
  - `fortress`
  - `customs_house`
  - `city_hall`
- 동일 건물 중복 소유는 불가하다.
- 최종 build 가능 여부는 엔진 action mask가 결정한다.

주의:

- 게임 종료 트리거는 “도시가 찬 플레이어가 생김”이지만, 현재 구현의 종료 판정 타이밍은 라운드 종료 흐름을 유지한다.
- 즉, Builder phase에서 도시가 꽉 찼다고 즉시 게임을 끊는 계약은 아니다.

## 5. Naming And Identity Contract

- 건물 이름은 backend / frontend 전체에서 snake_case가 정식 계약이다.
- room 저장용 bot actor id는 `BOT_<bot_type>`다.
- stable player ref는 `player_<idx>`다.

호환성 규칙:

- 입력 파서는 `guildhall`을 `guild_hall`로 normalize할 수 있다.
- 출력 serializer와 문서 계약에서는 `guildhall`을 사용하지 않는다.

## 6. Persistence Contract

한 판의 상태는 여러 계층에 저장되지만 역할이 다르다.

- 실시간 정본 엔진
  - `GameService.active_engines[game_id]`
- Redis 상태 캐시
  - key: `game:<game_id>:state`
  - TTL: 진행 중 900초, 종료 후 300초
- Redis 브로드캐스트 채널
  - key: `game:<game_id>:events`
  - payload: `{ "type": "STATE_UPDATE", "data": <GameState> }`
- Redis 연결 메타
  - `game:<game_id>:meta`
  - fields: `status`, `human_count`, `num_players`
  - TTL: 900초
- Redis 플레이어 연결 상태
  - `game:<game_id>:players`
  - `<player_id> -> connected|disconnected`
  - TTL: 900초
- PostgreSQL 운영 메타
  - `games`, `game_logs`
- 파일 로그 / replay
  - `data/logs/games/<game_id>.jsonl`
  - `data/logs/replay/<game_id>.json`

계약:

- 프론트 렌더링 기준 상태는 serializer + game service가 만든 rich `GameState`다.
- Redis는 캐시 / 브로드캐스트 레이어이지 정본 저장소가 아니다.

## 7. Tests That Guard This Contract

현재 주요 회귀 테스트:

- `backend/tests/test_game_ws_auth_contract.py`
- `backend/tests/test_ws_disconnect.py`
- `backend/tests/test_lobby_ws.py`
- `backend/tests/test_room_title_uniqueness.py`
- `backend/tests/test_channel_bot_endpoint.py`
- `backend/tests/test_final_score_access.py`
- `backend/tests/test_mayor_slot_contract.py`
- `backend/tests/test_phase_action_edge_cases.py`
- `backend/tests/test_state_serializer_action_index.py`
- `backend/tests/test_model_version_snapshot.py`
- `backend/tests/test_priority2_bot_routing_contract.py`
- `backend/tests/test_priority2_bot_input_snapshot.py`
- `backend/tests/test_legacy_features.py`
- `backend/tests/test_redis_service.py`
- `PuCo_RL/tests/test_phase_edge_cases.py`
- `frontend/src/__tests__/App.auth-flow.test.tsx`
- `frontend/src/__tests__/App.mayor-flow.test.tsx`
- `frontend/src/components/__tests__/MayorSequentialPanel.test.tsx`
- `frontend/src/components/__tests__/RoomListScreen.test.tsx`
- `frontend/src/components/__tests__/SanJuan.test.tsx`
- `frontend/vite.config.test.ts`

이 문서를 바꾸는 변경은 최소한 위 계약 테스트와 Docker 빌드까지 같이 확인해야 한다.
