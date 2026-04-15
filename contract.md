# Castone Contract Document

작성일: 2026-04-14  
범위: `frontend` / `backend` / `PuCo_RL` / Redis / PostgreSQL / replay/logging  
목적: 현재 코드와 테스트가 실제로 보장하는 supported contract만 정리한다. 이상적인 설계가 아니라, 지금 구현이 내보내는 계약을 기록한다.

보조 문서:

- `design/2026-04-08_engine_cutover_phase2_contract_followup.md`
- `design/2026-04-08_engine_cutover_batch_f_cleanup.md`
- `design/2026-04-14_mayor_large_building_masking_fix.md`

## 1. Source Of Truth

- 게임 규칙과 합법 액션의 최종 소스
  - `PuCo_RL/env/engine.py`
  - `PuCo_RL/env/pr_env.py`
- backend의 canonical engine 생성/실행 경계
  - `backend/app/services/engine_gateway/factory.py`
  - `backend/app/services/game_service.py`
- 프론트에 전달되는 channel `GameState`의 최종 소스
  - `backend/app/services/state_serializer.py`
  - `backend/app/services/state_serializer_support.py`
  - `backend/app/services/game_service_support.py`
- 액션 인덱스 번역의 최종 소스
  - `backend/app/services/action_translator.py`
- 프론트 타입 참고치
  - `frontend/src/types/gameState.ts`

계약이 충돌하면 엔진 규칙 > backend serializer / game service > 프론트 타입 순으로 맞춘다.

현재 코드베이스에서 명시적으로 drift가 있는 항목:

- 프론트 `PhaseType`의 `end_of_round`는 legacy union 잔재이며 현재 backend emit 값이 아니다.
- 프론트 일부 타입/컴포넌트는 첫 번째 Prospector를 `prospector`로 다루지만, backend serializer의 canonical role key는 `prospector_1`이다.
- channel `history` 키는 항상 존재하지만, 현재 channel state assembly 경로에서는 실제 내용이 `[]`로 내려간다.

## 2. Supported Public Interfaces

### 2.1 Operational

- `GET /`
- `GET /health`

계약:

- `/`는 단순 liveness 메시지를 반환한다.
- `/health`는 PostgreSQL/Redis 체크를 수행한다.
- `/health` 응답 shape는 `{ "status": "ok" | "degraded", "checks": { "postgresql": "...", "redis": "..." } }`다.
- 두 의존성이 모두 정상일 때 200, 하나라도 실패하면 503이다.

### 2.2 Auth

- `POST /api/puco/auth/google`
  - 요청: `{ "credential": "<google-id-token>" }`
  - 응답: `{ "access_token": "...", "token_type": "bearer", "user": { ... } }`
- `GET /api/puco/auth/me`
- `PATCH /api/puco/auth/me/nickname`

계약:

- `POST /google`만 비인증 엔드포인트고, `me`/`nickname`은 bearer 인증이 필요하다.
- JWT `sub`는 내부 `users.id`다.
- JWT 알고리즘은 HS256이고 기본 만료는 24시간이다.
- `google` 로그인 응답과 `me` 응답의 `user`에는 `needs_nickname`이 포함된다.
- `needs_nickname=true`면 프론트는 닉네임 설정 UI를 띄운다.
- 닉네임 검증 규칙은 현재 다음과 같다.
  - 길이 2-20
  - 허용 문자: 영문, 한글, 숫자, `_`, `-`
- 닉네임은 전역 unique이며, 같은 값으로 다시 설정하는 요청은 idempotent하게 성공한다.

### 2.3 Rooms

- `POST /api/puco/rooms/`
- `GET /api/puco/rooms/`
- `POST /api/puco/rooms/{room_id}/join`
- `POST /api/puco/rooms/{room_id}/leave`
- `POST /api/puco/rooms/bot-game`

계약:

- 모든 room REST는 bearer 인증이 필요하다.
- 최대 플레이어 수는 현재 3명이다.
- room status는 현재 `WAITING`, `PROGRESS`, `FINISHED`를 사용한다.
- `GET /rooms/`는 `WAITING` 방만 노출하며 최신 생성순(`created_at desc`)으로 정렬한다.
- room title uniqueness는 `WAITING` 방에 대해서만, 대소문자 무시 기준으로 적용된다.
- 한 사용자는 동시에 하나의 `WAITING` 방만 host할 수 있다.
- private room 비밀번호는 4자리 숫자 문자열이다.
- `GameRoomResponse.player_names[]`는 `{ display_name, is_bot }`만 가진다.
- room list/create/join 응답의 `player_names[]`와 lobby WS의 `players[]`는 shape가 다르다.
- `join`은 비공개 방일 때 비밀번호가 틀리거나 없으면 403이다.
- `join`은 이미 방에 있는 사용자를 일부 경우 idempotent하게 처리하지만, 현재 구현은 full-room 검사를 먼저 하기 때문에 이미 멤버여도 방이 꽉 차 있으면 409가 먼저 날 수 있다.
- `leave`는 현재 room에 없는 사용자가 호출해도 idempotent하게 `{ "status": "ok" }`를 반환한다.

`/bot-game` 계약:

- 요청 body의 `bot_types`는 최대 3개까지 받고, 부족하면 `random`으로 채운다.
- 현재 유효한 `bot_type`은 다음 registry key들이다.
  - `ppo`
  - `hppo`
  - `random`
  - `rule_based`
  - `advanced_rule`
  - `shipping_rush`
  - `factory_rule`
  - `action_value`
- unknown `bot_type`은 400이다.
- 기본 `bot_types`는 `["random", "random", "random"]`다.
- `/bot-game`은 즉시 시작되는 봇 전용 관전자형 게임 생성 경로다.
- `/bot-game`으로 만들어진 room은 `players`에 인간 대신 `BOT_<bot_type>` actor id만 저장하고, `host_id`는 관전자 human id로 유지한다.
- `/bot-game` 완료 후 room status는 `PROGRESS`다.
- `/bot-game` 응답 shape는 room summary가 아니라 `{ "game_id": "<uuid>", "state": <GameState> }`다.

### 2.4 Lobby WebSocket

- 엔드포인트: `GET ws /api/puco/ws/lobby/{room_id}`
- 연결 직후 5초 안에 첫 text message로 JWT JSON을 보내야 한다.
  - 지원 키: `token`, `accessToken`

주요 서버 발행 메시지:

- `LOBBY_STATE`
- `LOBBY_UPDATE`
- `GAME_STARTED`
- `ROOM_DELETED`
- `PING`

계약:

- 이 소켓은 `WAITING` room의 실제 member만 연결할 수 있다.
- bot-only spectator host는 `room.players`에 없으므로 lobby WS member가 아니다.
- `LOBBY_STATE` / `LOBBY_UPDATE` payload에는 `players[]`와 `host_id`가 포함된다.
- lobby payload의 각 player 항목은 현재 다음 필드를 쓴다.
  - `name`
  - `player_id`
  - `is_bot`
  - `is_host`
  - `connected`
- human lobby `player_id`는 실제 user UUID다.
- bot lobby `player_id`는 저장 actor id와 다른 synthetic key인 `BOT_<bot_type>_<slot_index>`다.
- `host_id`는 host human의 실제 UUID다.
- `GAME_STARTED`는 lobby WebSocket에서 발행되며 payload는 `{ "type": "GAME_STARTED", "state": <GameState> }`다.
- `PING`은 30초 동안 클라이언트 메시지가 없을 때 keep-alive로 전송된다.
- 게임 시작 후 lobby socket이 닫히는 것은 leave가 아니라 화면 전환으로 취급한다.
- `WAITING` 중 host가 떠나면 room은 삭제된다.

### 2.5 Game REST

- `POST /api/puco/game/{game_id}/start`
- `POST /api/puco/game/{game_id}/action`
- `POST /api/puco/game/{game_id}/mayor-distribute`
- `POST /api/puco/game/{game_id}/add-bot`
- `DELETE /api/puco/game/{game_id}/bots/{slot_index}`
- `GET /api/puco/game/{game_id}/final-score`

계약:

- `start`는 host만 호출할 수 있다.
- `start`는 실제 `room.players` 길이가 3 이상일 때만 성공한다.
- `start` 응답 shape는 `{ "status": "started", "state": <GameState>, "action_mask": [...] }`다.
- bot-only spectator room에서는 host가 `players` 바깥에 있어도 `start`와 `final-score` 접근이 허용된다.

`action` 계약:

- `action` 호출자는 room의 실제 `players` 멤버여야 한다.
- `action` 호출자는 현재 턴 actor와 일치해야 한다.
- 현재 supported public 입력은 `payload.action_index` 정수 하나다.
- `payload.action_index`가 없으면 400, 정수로 변환 불가능해도 400이다.
- 현재 구현은 추가 payload 키를 읽지 않는다.
- 서버는 현재 engine `action_mask` 기준으로 action을 검증하고, invalid action이면 400을 반환한다.
- `action` 성공 응답 shape는 `{ "status": "success", "state": <GameState>, "action_mask": [...] }`다.
- REST 응답의 top-level `action_mask`는 convenience duplicate이고, canonical mask는 `state.action_mask`다.

Mayor 관련 계약:

- human public Mayor는 slot-direct sequential placement만 지원한다.
- island slot direct action index는 `120-131`, city slot direct action index는 `140-151`이다.
- 한 번의 REST 호출에 colonist 1명씩 순차 배치한다.
- 이미 점유된 slot이나 capacity가 찬 building에 대한 action은 400이다.
- `POST /api/puco/game/{game_id}/mayor-distribute`는 현재 410 Gone이다.

봇 관리 계약:

- `add-bot` / `remove-bot`은 host만 가능하다.
- 현재 구현은 host 여부 이전에 membership도 검사하므로, caller는 host이면서 room member여야 한다.
- `add-bot` / `remove-bot`은 `WAITING` room에서만 허용된다.
- `add-bot`은 room이 꽉 찼으면 409다.
- `add-bot`의 `bot_type` 기본값은 `random`이다.
- `add-bot` 응답 shape는 `{ "status": "ok", "slot_index": <int>, "bot_type": "<type>" }`다.
- `remove-bot`은 slot index가 없으면 404, human slot이면 400이다.
- `remove-bot` 응답 shape는 `{ "status": "ok", "slot_index": <int>, "bot_type": "<type>" }`다.
- `add-bot` / `remove-bot` 성공 시 lobby WS로 `LOBBY_UPDATE`가 브로드캐스트된다.

`final-score` 계약:

- player 또는 host만 조회 가능하다.
- active engine이 없으면 404가 날 수 있다.
- 응답 shape는 `{ "scores": ..., "winner": ..., "player_order": ..., "display_names": ... }`다.

### 2.6 Game WebSocket

- 엔드포인트: `GET ws /api/puco/ws/{game_id}`
- 연결 직후 5초 안에 첫 JSON 메시지로 JWT를 보내야 한다.
  - 지원 키: `token`, `accessToken`
- 인증 성공 시 서버는 `{ "type": "auth_ok", "player_id": "<user-uuid>" }`를 보낸다.

클라이언트 발행 메시지:

- `END_GAME_REQUEST`

주요 서버 발행 메시지:

- `STATE_UPDATE`
  - shape: `{ "type": "STATE_UPDATE", "data": <GameState> }`
- `PLAYER_DISCONNECTED`
- `GAME_ENDED`

계약:

- game WebSocket은 room player 또는 host spectator만 연결할 수 있다.
- `STATE_UPDATE`의 canonical action mask는 `data.action_mask`다.
- 현재 game WS 브로드캐스트 경로는 top-level `action_mask`를 붙이지 않는다.
- `PLAYER_DISCONNECTED.player_id`는 stable player ref가 아니라 끊긴 user의 실제 UUID다.
- `PLAYER_DISCONNECTED`에는 항상 `message`가 포함된다.
- multi-human 진행 게임(`human_count >= 2`)일 때만 `options`와 `timeout_seconds`가 추가된다.
- disconnect timeout은 현재 600초다.
- `GAME_ENDED.reason`은 현재 최소한 다음 값을 쓴다.
  - `player_request`
  - `player_disconnect_timeout`
- `END_GAME_REQUEST`는 즉시 DB status를 `FINISHED`로 바꾸고 `GAME_ENDED`를 브로드캐스트한다.

### 2.7 Legacy Compatibility

- `GET /api/bot-types`

계약:

- room/lobby 화면은 아직 이 경로를 사용한다.
- 응답 shape는 `[{ "type": "...", "name": "..." }]`다.
- 응답 원천은 `app.services.agent_registry.AGENT_REGISTRY`다.
- 이 문서의 주 계약은 channel API이지만, `bot-types`는 현재 지원 중인 호환 경로로 유지한다.
- 그 외 `/api/...` legacy single-player/SSE 경로는 코드에는 남아 있지만, 현재 SPA의 주 계약 소스는 아니다.

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

- serializer core가 대부분을 만들고,
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
- 엔진의 `END_ROUND`와 `PROSPECTOR` phase는 serializer에서 `role_selection`으로 평탄화된다.
- 프론트 타입의 `end_of_round`는 legacy union 잔재이며 현재 backend emit 값이 아니다.
- `active_role`의 canonical role name은 현재 다음 집합을 쓴다.
  - `settler`
  - `mayor`
  - `builder`
  - `craftsman`
  - `trader`
  - `captain`
  - `prospector_1`
  - `prospector_2`
- `active_player`, `governor`, `player_order[]`는 모두 `player_<idx>` naming scheme을 따른다.
- `phase_id`는 엔진 `Phase` enum 정수다.
- `pass_action_index`는 항상 `15`다.
- `hacienda_action_index`는 항상 `105`다.

Mayor phase 추가 convenience fields:

- `mayor_phase_mode`: `"slot-direct"`
- `mayor_remaining_colonists`
- `mayor_legal_island_slots`
- `mayor_legal_city_slots`

Mayor 메타 계약:

- `mayor_legal_island_slots`는 island 배열 index 기준이다.
- `mayor_legal_city_slots`는 raw engine city index가 아니라 serializer가 `OCCUPIED_SPACE`를 제거한 뒤의 filtered city array index다.
- 과거 cursor용 `mayor_slot_idx`, `mayor_can_skip`는 포함되지 않는다.

### 3.2 `decision`, `history`, `bot_players`

계약:

- `decision`은 `{ "type": <phase>, "player": <active_player>, "note": "" }` shape를 쓴다.
- `history` 키는 항상 존재한다.
- 현재 channel path의 `history`는 실제로는 `[]`가 내려간다.
- `bot_players`는 stable player ref 기준 `{ "player_<idx>": "<bot_type>" }`를 쓴다.

### 3.3 `common_board`

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

- `roles[*]`에는 `doubloons_on_role`, `taken_by`가 있다.
- 사용 가능한 role(`taken_by == null`)에는 `action_index`가 포함되며 범위는 `0-7`이다.
- canonical role key는 serializer 기준으로 `prospector_1`, `prospector_2`를 쓴다.
- `available_plantations.face_up[*]`는 문자열이 아니라 `{ type, action_index }` 객체다.
- 일반 plantation slot의 `action_index`는 `8-13`, quarry는 `14`다.
- `available_buildings[*].action_index`는 build 번역용 인덱스이며 범위는 `16-38`이다.
- `action_index`가 있다고 해서 현재 그 액션이 legal하다는 뜻은 아니다.
- 최종 legality는 `action_mask`와 backend 검증이 결정한다.

### 3.4 `common_board.available_buildings`

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

- public output contract는 snake_case다.
- 입력 파서는 legacy alias를 normalize할 수 있지만, serializer 출력은 `guildhall` 같은 구키를 노출하지 않는다.

### 3.5 `players`

각 player 객체 top-level 필드:

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

- `display_number`는 governor-relative 순번이며 같은 state 안에서 unique한 `1..n`이다.
- `is_governor`는 `meta.governor`와 일치해야 한다.
- `players[*].city.buildings[*]`는 현재 다음 필드를 가진다.
  - `name`
  - `engine_slot_idx`
  - `max_colonists`
  - `current_colonists`
  - `empty_slots`
  - `is_active`
  - `vp`
  - `slot_id`
  - `capacity`
- `players[*].island.plantations[*]`는 현재 다음 필드를 가진다.
  - `type`
  - `colonized`
  - `slot_id`
  - `capacity`

Slot id 계약:

- `players[*].city.buildings[*].slot_id` 형식은 `city:<building_name>:<index>`다.
  - 예: `city:guild_hall:0`
- `players[*].island.plantations[*].slot_id` 형식은 `island:<tile_name>:<index>`다.
  - 예: `island:corn:0`
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

human snapshot 주요 필드:

- `actor_type: "human"`
- `player_id`
- `fingerprint`

bot snapshot 주요 필드:

- `actor_type: "bot"`
- `bot_type`
- `family`
- `policy_tag`
- `artifact_name`
- `checkpoint_filename`
- `architecture`
- `metadata_source`
- `fingerprint`

`fingerprint` nested 주요 필드:

- `schema_version`
- `action_space`
- `mayor_semantics`
- `env`

계약:

- human actor도 `model_versions`에 별도 snapshot을 가진다.
- bot actor는 artifact/family 메타를 포함한다.
- `result_summary`와 달리 `model_versions`는 room start 시점 snapshot이며, 진행 중 실시간 재해석하지 않는다.

## 4. Action Contract

현재 codebase가 노출하는 action space 요약:

- `0-7`: role selection
- `8-13`: face-up plantation pick
- `14`: quarry pick
- `15`: pass
- `16-38`: build
- `39-43`: trade house sell
- `44-58`: captain ship load
- `59-63`: captain wharf load
- `64-68`: captain windrose keep
- `69-71`: reserved legacy Mayor band
- `93-97`: craftsman privilege
- `105`: hacienda draw
- `106-110`: captain warehouse keep
- `120-131`: Mayor sequential island slot placement
- `140-151`: Mayor sequential city slot placement

### 4.1 Mayor

현재 supported Mayor contract:

- public human contract는 slot-direct sequential placement다.
- `120-131`: island slot `0-11`에 colonist 1명 배치
- `140-151`: city slot `0-11`에 colonist 1명 배치
- 각 배치는 `POST /api/puco/game/{game_id}/action`으로 1회 호출한다.
- 이미 확정된 배치는 되돌릴 수 없다.
- 남은 colonist가 0이 되거나 legal slot이 없으면 자동으로 다음 player로 넘어간다.

현재 명시적 비지원:

- `69-71`: Mayor strategy band는 public contract가 아니다.
- `POST /api/puco/game/{game_id}/mayor-distribute`
- cursor metadata (`mayor_slot_idx`, `mayor_can_skip`)

내부 구현 참고:

- bot turn도 같은 slot-direct action range를 사용한다.
- bot Mayor는 내부적으로 여러 placement를 연속 처리하고 intermediate broadcast를 suppress할 수 있다.

### 4.2 Legality / Mask

계약:

- 서버가 최종적으로 거부/수락하는 기준은 현재 engine `action_mask`다.
- channel `GameState.action_mask`는 현재 serializer가 받은 engine-derived mask를 그대로 노출하는 경로다.
- websocket canonical state도 top-level이 아니라 `data.action_mask`를 사용한다.
- legality 판단은 파생 UI 필드가 아니라 `action_mask`와 서버 검증을 기준으로 해야 한다.

정정:

- 과거 문서에 있던 “Settler에서는 backend guard가 항상 `action_mask[15]`를 0으로 내린다”는 현재 channel path 기준 사실이 아니다.
- helper 함수는 존재하지만, 현재 serializer 경로의 supported contract는 “emit된 `action_mask` 자체를 신뢰한다” 쪽이다.

### 4.3 Builder

Builder phase 유효성 계약:

- 도시 빈칸이 0이면 build action은 legal하지 않아야 한다.
- 대형 건물은 도시 2칸을 차지한다.
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
- 즉, Builder phase에서 도시가 꽉 찼다고 즉시 게임을 끊는 public contract는 아니다.

## 5. Naming And Identity Contract

- 건물 이름은 backend / frontend 전체에서 snake_case가 canonical 계약이다.
- room 저장용 bot actor id는 `BOT_<bot_type>`다.
- lobby WS bot `player_id`는 synthetic key `BOT_<bot_type>_<slot_index>`다.
- stable player ref는 `player_<idx>`다.
- `result_summary`, `bot_players`, `model_versions`는 stable player ref를 키로 쓴다.
- canonical role naming은 현재 `prospector_1`, `prospector_2`를 포함한다.

호환성 규칙:

- 입력 파서는 `guildhall`을 `guild_hall`로 normalize할 수 있다.
- 출력 serializer와 문서 계약에서는 `guildhall`을 사용하지 않는다.

## 6. Persistence Contract

한 판의 상태는 여러 계층에 저장되지만 역할이 다르다.

- 실시간 정본 엔진
  - `GameService.active_engines[game_id]`
- Redis 상태 캐시
  - key: `game:{game_id}:state`
  - TTL: 진행 중 900초, 종료 후 300초
- Redis 브로드캐스트 채널
  - key: `game:{game_id}:events`
  - payload: `{ "type": "STATE_UPDATE", "data": <GameState> }`
- Redis 연결 메타
  - key: `game:{game_id}:meta`
  - fields: `status`, `human_count`, `num_players`
  - TTL: 진행 중 900초, 종료 마킹 후 300초
- Redis 플레이어 연결 상태
  - key: `game:{game_id}:players`
  - `<player_id> -> connected|disconnected`
  - TTL: connect 시 900초로 refresh
- PostgreSQL 운영 메타
  - table: `games`
  - table: `game_logs`
- 파일 로그 / replay
  - `data/logs/games/{game_id}.jsonl`
  - `data/logs/replay/{game_id}.json`

계약:

- 프론트 렌더링 기준 상태는 serializer + game service가 만든 rich `GameState`다.
- Redis는 캐시 / 브로드캐스트 레이어이지 정본 저장소가 아니다.
- room 메타의 운영 정본은 PostgreSQL `games`다.
- 실시간 진행 정본 엔진은 메모리 `active_engines`다.

## 7. Tests That Guard This Contract

현재 이 문서와 직접 맞물린 주요 회귀 테스트:

- `backend/tests/test_auth.py`
- `backend/tests/test_health_endpoint.py`
- `backend/tests/test_room_title_uniqueness.py`
- `backend/tests/test_lobby_ws.py`
- `backend/tests/test_channel_bot_endpoint.py`
- `backend/tests/test_game_ws_auth_contract.py`
- `backend/tests/test_ws_disconnect.py`
- `backend/tests/test_final_score_access.py`
- `backend/tests/test_state_serializer_action_index.py`
- `backend/tests/test_mayor_slot_contract.py`
- `backend/tests/test_mayor_serializer_contract.py`
- `backend/tests/test_mayor_large_building_masking.py`
- `backend/tests/test_model_version_snapshot.py`
- `backend/tests/test_redis_service.py`
- `frontend/src/__tests__/App.auth-flow.test.tsx`
- `frontend/src/__tests__/App.mayor-flow.test.tsx`
- `frontend/src/hooks/__tests__/useGameWebSocket.test.ts`
- `frontend/src/components/__tests__/MayorSequentialPanel.test.tsx`
- `frontend/src/components/__tests__/RoomListScreen.test.tsx`
- `frontend/src/components/__tests__/LobbyScreen.test.tsx`
- `frontend/src/components/__tests__/GameScreen.test.tsx`
- `frontend/src/components/__tests__/SanJuan.test.tsx`

이 문서를 다시 바꾸는 변경은 최소한 위 계약 테스트와, 변경이 런타임 경로에 닿는 경우 Docker/통합 실행까지 같이 확인하는 쪽을 권장한다.
