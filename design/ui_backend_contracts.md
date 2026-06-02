# UI 리디자인용 백엔드 계약 정리

이 문서는 프론트엔드 UI 디자인만 바꿀 때 백엔드 연동과 충돌하기 쉬운 계약을 정리한 안전 가드다. 목표는 레이아웃, 색상, 컴포넌트 구조, 표시 방식은 자유롭게 바꾸되 API 경로, 요청/응답 스키마, 액션 의미, 상태 키는 유지하는 것이다.

## 한 줄 원칙

- 디자인 변경은 `frontend/src/components/*`, `frontend/src/App.css`, `frontend/src/index.css`, 번역 문구, 표시 컴포넌트 분리에 머무르는 것이 가장 안전하다.
- `frontend/src/App.tsx`의 API 호출, WebSocket 처리, `channelAction`, 턴 판정, 로컬 세션 저장 로직은 디자인 변경 범위 밖으로 본다.
- `frontend/src/types/gameState.ts`와 `frontend/src/types/replay.ts`는 백엔드 응답을 반영하는 계약 타입이다. 화면 편의를 위해 별도 view model을 만들 수는 있지만 원본 필드 의미는 바꾸지 않는다.
- `action_index`, `canonical_id`, `action_mask`, `expected_state_revision`, `player_*` 식별자는 UI 버튼과 백엔드 검증을 직접 잇는 핵심 계약이다.

## 계약 원천 파일

| 영역 | 프론트 원천 | 백엔드 원천 |
| --- | --- | --- |
| 게임 상태 타입 | `frontend/src/types/gameState.ts` | `backend/app/services/state_serializer.py`, `backend/app/services/state_serializer_support.py` |
| 액션 요청 | `frontend/src/App.tsx` `channelAction` | `backend/app/schemas/game.py`, `backend/app/api/channel/game.py`, `backend/app/services/contracts.py` |
| 액션 의미/인덱스 | `frontend/src/App.tsx` `channelActionIndex`, 상태 내 `action_index` | `backend/app/services/canonical_action.py`, `backend/app/services/action_translator.py` |
| 게임 WebSocket | `frontend/src/hooks/useGameWebSocket.ts` | `backend/app/api/channel/ws.py`, `backend/app/services/ws_manager.py` |
| 로비 WebSocket | `frontend/src/App.tsx` `connectLobbyWs` | `backend/app/api/channel/lobby_ws.py`, `backend/app/services/lobby_manager.py` |
| 방/봇/시작 API | `frontend/src/App.tsx`, `frontend/src/components/RoomListScreen.tsx` | `backend/app/api/channel/room.py`, `backend/app/api/channel/game.py` |
| 인증/닉네임 | `frontend/src/hooks/useAuthBootstrap.ts`, `frontend/src/App.tsx` | `backend/app/api/channel/auth.py`, `backend/app/schemas/auth.py` |
| 리플레이 | `frontend/src/hooks/useReplayList.ts`, `frontend/src/components/ReplayViewScreen.tsx`, `frontend/src/types/replay.ts` | `backend/app/api/channel/replay.py`, `backend/app/schemas/replay.py` |
| 봇전 재생 제어 | `frontend/src/App.tsx` | `backend/app/api/channel/playback.py`, `backend/app/schemas/playback.py` |

## API 엔드포인트 계약

### 인증

`POST /api/puco/auth/google`

- 요청: `{ "credential": string }`
- 응답: `{ "access_token": string, "token_type": "bearer", "user": UserResponse }`
- `UserResponse`: `id`, `nickname`, `email`, `total_games`, `win_rate`, `needs_nickname`
- UI 주의: 로그인 화면 디자인을 바꿔도 Google credential 전달 이름은 `credential`이어야 한다.

`GET /api/puco/auth/me`

- 헤더: `Authorization: Bearer <token>`
- 응답: `UserResponse`
- UI 주의: 앱 부트스트랩과 새로고침 복귀 흐름이 이 응답에 의존한다.

`PATCH /api/puco/auth/me/nickname`

- 헤더: `Authorization: Bearer <token>`
- 요청: `{ "nickname": string }`
- 제약: 2-20자, 영문/한글/숫자/`_`/`-`만 허용
- 응답: `UserResponse`

### 활성 게임 복귀

`GET /api/puco/session/active-game`

- 헤더: `Authorization: Bearer <token>`
- 응답 없음 상태: `{ "has_active_game": false }`
- 응답 있음 상태: `{ "has_active_game": true, "game_id": string, "status": "WAITING" | "PROGRESS" | "RECOVERY_BLOCKED", "is_host": boolean, "is_player": boolean }`
- UI 주의: 새로고침 후 lobby/game 화면 복귀 판단에 쓰인다.

### 방 목록/생성/참가

`GET /api/puco/rooms/`

- 헤더: `Authorization: Bearer <token>`
- 응답: `GameRoomResponse[]`
- `GameRoomResponse`: `id`, `title`, `status`, `is_private`, `current_players`, `max_players`, `player_names`
- `player_names[]`: `{ "display_name": string, "is_bot": boolean }`

`POST /api/puco/rooms/`

- 요청: `{ "title": string, "is_private": boolean, "password"?: string }`
- 제약: `title` 1-30자, 비밀방이면 `password` 필수, 비밀번호는 4자리 숫자
- 응답: `GameRoomResponse`
- UI 주의: 방 생성 모달/폼을 바꿔도 `is_private`, `password` 이름과 의미를 유지한다.

`POST /api/puco/rooms/{room_id}/join`

- 요청: `{ "password"?: string | null }`
- 응답: `GameRoomResponse`
- UI 주의: 비밀방 참가 UI에서 빈 문자열과 `null` 처리를 조심한다.

`POST /api/puco/rooms/{room_id}/leave`

- 응답: `{ "status": "ok" }`
- UI 주의: 뒤로가기, 로그아웃, 방 나가기 버튼의 흐름에서 호출된다.

### 봇전/봇 관리

`GET /api/bot-types`

- 응답: 봇 타입 목록/맵
- UI 주의: 방 목록 화면과 로비 화면에서 봇 선택지를 그릴 때 사용한다.

`POST /api/puco/rooms/bot-game`

- 요청: `{ "bot_types": string[] }`
- 응답: `{ "game_id": string, "state": GameState }`
- UI 주의: 사용자는 관전자로 들어가며 `state`를 즉시 게임 화면에 넣는다.

`POST /api/puco/game/{game_id}/add-bot`

- 요청: `{ "bot_type": string }`
- 응답: `{ "status": "ok", "slot_index": number, "bot_type": string }`
- UI 주의: 성공 후 로컬 목록을 직접 조작하지 말고 로비 WebSocket의 `LOBBY_UPDATE`를 신뢰한다.

`DELETE /api/puco/game/{game_id}/bots/{slot_index}`

- 응답: `{ "status": "ok", "slot_index": number, "bot_type": string }`
- UI 주의: `slot_index`는 현재 로비 플레이어 배열 기준이다. 화면 정렬을 바꾸면 삭제 대상 매핑이 틀어질 수 있다.

### 게임 시작/액션/점수

`POST /api/puco/game/{game_id}/start`

- 응답: `{ "status": "started", "state": GameState, "action_mask": number[] }`
- UI 주의: 게임 시작 직후 `GameState.players`의 표시 이름으로 `myPlayerId`를 재해석한다.

`POST /api/puco/game/{game_id}/action`

- 요청:

```json
{
  "payload": {
    "schema_version": "action-request.v1",
    "action_index": 10,
    "canonical_id": "settler:tile_type:corn",
    "action_intent_id": "uuid-like-client-id",
    "expected_state_revision": 12
  }
}
```

- `schema_version`은 `action-request.v1`이어야 한다.
- `action_index`는 필수 정수다.
- `canonical_id`는 선택이지만, 상태가 제공하는 경우 반드시 같은 의미로 같이 보내야 한다.
- `action_intent_id`는 중복 요청 방지용이다.
- `expected_state_revision`은 stale action 방지용이다.
- 성공 응답: `{ "status": "success", "state": GameState, "action_mask": number[], "duplicate"?: true }`
- stale 응답: HTTP 409, `detail.error === "stale_state"`
- canonical mismatch 응답: HTTP 422, `detail.error === "canonical_id_mismatch"`
- UI 주의: 버튼 디자인을 바꾸더라도 클릭 핸들러가 보내는 `action_index`와 `canonical_id`는 바꾸면 안 된다.

`GET /api/puco/game/{game_id}/final-score`

- 응답: `FinalScoreSummary`
- `FinalScoreSummary`: `scores`, `winner`, `player_order`, `display_names?`
- UI 주의: 게임 종료 시 `state.result_summary`가 없으면 별도 fetch로 가져온다.

## GameState 스키마

`GameState`는 게임 화면 전체의 단일 원천이다.

```ts
interface GameState {
  meta: Meta;
  common_board: CommonBoard;
  players: Record<string, Player>;
  decision: Decision;
  history: HistoryEntry[];
  action_mask?: number[];
  bot_players?: Record<string, string>;
  model_versions?: Record<string, ModelVersionInfo>;
  result_summary?: FinalScoreSummary | null;
}
```

백엔드는 `schema_version: "rich-game-state.v1"`, `state_kind: "rich-game-state"`, `producer: "state-serializer"`도 붙인다. 현재 프론트 타입에는 이 세 필드가 명시되어 있지 않지만 응답에는 올 수 있으므로 제거/금지하는 런타임 검증을 추가하면 위험하다.

### Meta

필수/중요 필드:

- `game_id`: 게임 식별자
- `round`: 라운드 표시와 라운드 변경 효과에 사용
- `num_players`: 플레이어 수
- `player_order`: `player_0`, `player_1` 같은 내부 플레이어 키 배열
- `governor`: governor 플레이어 키
- `phase`: 현재 단계. 프론트 허용값은 `role_selection`, `settler_action`, `mayor_action`, `builder_action`, `craftsman_action`, `trader_action`, `captain_action`, `captain_discard`, `end_of_round`, `game_over`
- `active_role`: 현재 역할 또는 `null`
- `active_player`: 현재 활성 플레이어 키
- `state_revision`: 액션 stale 방지에 사용되는 선택 필드
- `end_game_triggered`, `end_game_reason`: 종료 UI와 최종 점수 fetch에 사용
- `vp_supply_remaining`, `captain_consecutive_passes`: 보드 표시/상태 표시
- `bot_thinking`: 상호작용 잠금과 오버레이 판단
- `pass_action_index`: 보통 15
- `hacienda_action_index`: 보통 105

Mayor 단계 편의 필드:

- `mayor_phase_mode`: 현재 `"slot-direct"`
- `mayor_remaining_colonists`
- `mayor_legal_island_slots`, `mayor_legal_city_slots`
- `mayor_island_actions[]`, `mayor_city_actions[]`
- 각 Mayor action entry는 `display_position`, `engine_action_index`, `canonical_id`, `tile_name?`, `building_name?`을 가진다.

UI 주의:

- `phase` 문자열은 화면 분기와 자동 스크롤에 쓰인다. 표시 라벨은 번역으로 바꾸고 원본 값은 바꾸지 않는다.
- `active_player`와 `decision.player`는 내 턴 판정에 쓰인다. 화면 표시 이름과 혼동하면 멀티플레이어에서 턴 잠금이 깨진다.
- Mayor UI를 새로 그려도 `engine_action_index`와 `canonical_id`를 그대로 `onPlaceMayorColonist`에 전달해야 한다.

### CommonBoard

핵심 필드:

- `roles: Record<RoleName, Role>`
- `colonists: { ship, supply }`
- `trading_house: { goods, d_spaces_used, d_spaces_remaining, d_is_full }`
- `cargo_ships[]: { capacity, good, d_filled, d_remaining_space, d_is_full, d_is_empty }`
- `available_plantations.face_up[]`
- `available_plantations.draw_pile`
- `available_buildings`
- `quarry_supply_remaining`
- `goods_supply`

UI 주의:

- `roles[role].action_index`가 역할 선택 버튼의 실제 액션이다.
- `available_plantations.face_up[]`의 `display_position`은 보이는 위치, `engine_action_index`/`action_index`는 서버 액션 의미다. 정렬하거나 필터링해도 클릭 시 원래 entry의 인덱스를 보내야 한다.
- `available_buildings[buildingName].action_index`가 건설 액션이다. 건물 이름 키를 화면용 라벨로 변환해서 원본 키를 잃으면 건설이 깨진다.

### Player

`players`는 `player_0` 같은 내부 키를 사용한다. 각 `Player`는 다음 구조를 가진다.

- `display_name`, `display_number`, `is_governor`
- `doubloons`, `vp_chips`
- `goods`: `corn`, `indigo`, `sugar`, `tobacco`, `coffee`, `d_total`
- `island`: `total_spaces`, `d_used_spaces`, `d_empty_spaces`, `d_active_quarries`, `plantations[]`
- `city`: `total_spaces`, `d_used_spaces`, `d_empty_spaces`, `colonists_unplaced`, `d_quarry_discount`, `d_total_empty_colonist_slots`, `buildings[]`
- `production`
- `warehouse`
- `captain_first_load_done`, `wharf_used_this_phase`, `hacienda_used_this_phase`

UI 주의:

- 화면 정렬 기준은 바꿀 수 있지만 `players` record의 key는 내부 식별자다. display name으로 key를 대체하지 않는다.
- `slot_id`, `engine_slot_idx`, `capacity`, `current_colonists`, `empty_slots`, `is_active`는 섬/도시 배치 UI와 Mayor 배치 가능 여부 표시에서 의미가 있다.

### History와 팝업

`history[]`는 `{ ts, action, params }`다.

- `action`은 번역 키 `history.actions.${action}`로 쓰인다.
- `params.role`, `params.player`, `params.good`, `params.plantation`, `params.building`은 표시용 번역/강조에 쓰인다.

UI 주의:

- 팝업 모양은 바꿔도 `history.length` 증가 감지는 유지해야 한다.
- `params`를 문자열이 아닌 다른 구조로 가정하는 UI를 만들면 기존 번역 흐름이 깨질 수 있다.

## 액션 인덱스 계약

다음 숫자 범위는 백엔드 `canonical_action.py`와 엔진 액션 공간에 묶여 있다.

| 범위 | 의미 | canonical 예 |
| --- | --- | --- |
| `0-7` | 역할 선택 | `role:settler`, `role:mayor` |
| `8-12` | Settler 농장 타입 선택 | `settler:tile_type:corn` |
| `13`, `14` | Quarry 선택 | `settler:quarry` |
| `15` | Pass | `pass` |
| `16-38` | Builder 건물 건설 | `builder:building:{building_type}` |
| `39-43` | Trader 판매 | `trader:sell:{good}` |
| `44-58` | Captain 선적 | `captain:load:{good}:ship:{ship_idx}` |
| `59-63` | Wharf 선적 | `captain:wharf:{good}` |
| `64-68` | Windrose 저장 | `store:windrose:{good}` |
| `93-97` | Craftsman 특권 | `craftsman:privilege:{good}` |
| `105` | Hacienda | `settler:hacienda` |
| `106-110` | Warehouse 저장 | `store:warehouse:{good}` |
| `120-125` | Mayor island slot-direct | `mayor:island:tile_type:{tile_name}` |
| `140-162` | Mayor city slot-direct | `mayor:city:building_type:{building_type}` |

Good enum 순서는 중요하다.

```ts
coffee = 0
tobacco = 1
corn = 2
sugar = 3
indigo = 4
```

UI 주의:

- 굿 표시 순서를 바꾸는 것은 가능하지만 액션 계산의 enum 순서를 바꾸면 안 된다.
- 버튼 disable 판단은 `action_mask[action_index]`를 기준으로 한다.
- `maskAllowed === 0`이면 프론트가 요청을 막는다. `undefined`는 과거/부분 상태 호환 때문에 즉시 차단하지 않는다.
- 디자인용 컴포넌트에서 `onClick={() => onAction(displayIndex)}`처럼 화면 순서를 액션 인덱스로 보내면 안 된다.

## WebSocket 계약

### 게임 WebSocket

경로: `WS /api/puco/ws/{game_id}`

연결 직후 첫 메시지:

```json
{ "token": "<jwt>" }
```

서버 메시지:

- `{ "type": "auth_ok", "player_id": string }`
- `{ "type": "STATE_UPDATE", "data": GameState, "action_mask"?: number[] }`
- `{ "type": "GAME_ENDED", "reason"?: string }`
- `{ "type": "PLAYER_DISCONNECTED", "player_id": string }`
- `{ "type": "RECOVERY_STARTED" }`
- `{ "type": "RECOVERY_BLOCKED", "reason": string }`

클라이언트 메시지:

- `{ "type": "END_GAME_REQUEST" }`는 복구 불가 모달의 종료 버튼에서 사용된다.

UI 주의:

- `STATE_UPDATE.data`의 `GameState`와 top-level `action_mask`를 합쳐 state에 저장한다.
- 같은 상태 중복 수신은 JSON key 비교로 dedupe한다.
- WebSocket 인증 토큰을 URL query로 옮기지 않는다. 첫 메시지 body 계약을 유지한다.

### 로비 WebSocket

경로: `WS /api/puco/ws/lobby/{room_id}`

연결 직후 첫 메시지:

```json
{ "token": "<jwt>" }
```

서버 메시지:

- `{ "type": "LOBBY_STATE", "players": LobbyPlayer[], "host_id": string | null }`
- `{ "type": "LOBBY_UPDATE", "players": LobbyPlayer[], "host_id": string | null }`
- `{ "type": "ROOM_DELETED" }`
- `{ "type": "GAME_STARTED", "state": GameState }`
- `{ "type": "PING" }`

`LobbyPlayer`:

- `name`
- `player_id`
- `is_bot`
- `is_host`
- `connected`
- 프론트 타입에는 `is_spectator?`도 있으나 현재 채널 로비 payload에서는 핵심 필드가 아니다.

UI 주의:

- `is_host`로 방장 권한 UI를 결정한다.
- `player_id`는 내부 식별자다. 표시 이름 변경과 섞지 않는다.
- `GAME_STARTED.state`를 받으면 로비 소켓을 닫고 게임 화면으로 전환한다.

## 리플레이 계약

`GET /api/puco/replays/?page=1&size=10&player=<optional>`

- 응답: `ReplayListResponse`
- `ReplayListResponse`: `replays`, `page`, `size`, `total_items`, `total_pages`
- `ReplayListItem`: `index`, `game_id`, `display_label`, `human_player_names`, `played_date`, `created_at`, `num_players`, `winner`, `players`

`GET /api/puco/replays/{game_id}`

- 응답: `ReplayDetailResponse`
- `ReplayFrame.rich_state`는 `GameState`다.
- UI 주의: 리플레이 화면 리디자인도 일반 게임 화면과 같은 `GameState` 표시 계약을 공유한다.

## 봇전 재생 제어 계약

`GET /api/puco/games/{game_id}/playback`

- 응답: `{ "speed": 1 | 2 | 4, "paused": boolean }`

`POST /api/puco/games/{game_id}/speed`

- 요청: `{ "speed": 1 | 2 | 4 }`
- 응답: `{ "speed": number }`

`POST /api/puco/games/{game_id}/pause`

- 요청: `{ "paused": boolean }`
- 응답: `{ "paused": boolean }`

UI 주의:

- 속도 UI를 슬라이더로 바꿔도 실제 전송값은 `1`, `2`, `4` 중 하나여야 한다.
- 이 API는 모든 플레이어가 봇인 진행 중 게임에서만 허용된다.

## 디자인 변경 시 안전한 영역

- CSS 변수, 색상, spacing, typography, responsive layout
- 컴포넌트 내부 마크업 구조 변경
- 게임 보드/플레이어 패널/공용 보드의 시각적 배치 변경
- 모달, 토스트, 팝업의 표현 방식 변경
- 번역 파일의 표시 문구 변경
- 표시 전용 helper 추가
- `GameState` 원본을 받아 derived view model을 만드는 순수 함수 추가

## 디자인 변경 시 위험한 영역

- `channelAction` payload 구조 변경
- `action_index`를 화면 index로 재계산
- `canonical_id` 누락 또는 임의 생성
- `action_mask` 기반 disabled/locked 처리 제거
- `isMyTurn`, `isBotTurn`, `interactionLocked`, `notMyTurn` 판정 변경
- `player_0` 같은 내부 key를 display name으로 대체
- 방/로비 WebSocket 메시지 타입 이름 변경
- `Authorization: Bearer` 헤더 제거
- `buildApiUrl`, `buildWebSocketUrl`, `VITE_BACKEND_ORIGIN` 흐름 변경
- `localStorage`의 `access_token` 및 active game session 저장/복구 흐름 변경
- 응답 필드명을 camelCase로 바꾸는 런타임 변환. 백엔드는 snake_case를 보낸다.

## 리디자인 작업 체크리스트

1. 화면 컴포넌트는 가능한 한 props 이름과 의미를 유지한다.
2. 클릭 가능한 게임 액션은 원본 상태 entry의 `action_index`/`engine_action_index`/`canonical_id`를 그대로 전달한다.
3. 표시 순서를 바꾼 경우에도 서버로 보내는 값이 화면 index가 아닌 엔진 action index인지 확인한다.
4. 모든 버튼의 disabled/locked 상태가 `action_mask`, `isMyTurn`, `isBotTurn`, `saving`, `bot_thinking`, recovery 상태를 반영하는지 확인한다.
5. 로비에서는 서버 WebSocket payload를 source of truth로 두고 로컬 목록을 낙관적으로 재구성하지 않는다.
6. 리플레이 화면은 `ReplayFrame.rich_state`를 일반 `GameState`처럼 취급한다.
7. 봇전 속도 컨트롤은 `1`, `2`, `4`만 전송한다.
8. 새 UI 테스트를 추가할 때 최소한 기존 계약 테스트를 같이 유지한다.

## 리디자인 후 권장 검증

프론트만 바꿨더라도 다음 테스트는 계약 회귀를 잡는 데 유용하다.

```bash
cd frontend
npm test -- --run src/__tests__/App.action-index-contract.test.tsx src/__tests__/App.idempotency.test.tsx src/hooks/__tests__/useGameWebSocket.test.ts src/components/__tests__/GameScreen.test.tsx
```

방/로비 UI를 바꿨다면 추가로:

```bash
cd frontend
npm test -- --run src/components/__tests__/RoomListScreen.test.tsx src/components/__tests__/LobbyScreen.test.tsx src/__tests__/App.refresh-rejoin.test.tsx
```

리플레이 UI를 바꿨다면 추가로:

```bash
cd frontend
npm test -- --run src/hooks/__tests__/useReplayList.test.ts src/components/__tests__/ReplayListScreen.test.tsx src/components/__tests__/ReplayViewScreen.test.tsx
```

백엔드 계약까지 확인해야 하는 큰 변경이면:

```bash
docker compose exec -T backend pytest tests/test_action_index_contract.py tests/test_game_ws_auth_contract.py tests/test_lobby_ws.py tests/test_replay_api.py tests/test_playback_api.py -q
```

## 절대 유지해야 할 최소 계약

- `GameState`의 `meta`, `common_board`, `players`, `decision`, `history` 구조
- `action-request.v1` payload 구조
- `action_index` 숫자 공간과 Good enum 순서
- 상태에서 제공된 `canonical_id` 전달
- `action_mask` 기반 액션 가능 여부
- `player_*` 내부 플레이어 키
- JWT는 `Authorization: Bearer`와 WebSocket 첫 메시지 `{ token }`로 전달
- WebSocket 메시지 타입 문자열
- snake_case API 필드명
