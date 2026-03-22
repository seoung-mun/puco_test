# API Specification: Castone WebSocket & REST

## 1. REST API (Lobby & User)

보드게임 세션 전 단계(Lobby)와 유저 관리를 위한 표준 REST API입니다.

### 1.1. 유저 인증 (Auth)
- **POST `/api/v1/auth/login`**: 유저 정보(ID, PW 등)를 받아 JWT 토큰 발급.

### 1.2. 방 관리 (Room)
- **GET `/api/v1/rooms`**: 현재 활성화된 방 목록 조회.
- **POST `/api/v1/rooms`**: 새로운 방 생성 (방 제목, 최대 인원, 비밀번호 등).
- **GET `/api/v1/rooms/{room_id}`**: 특정 방의 상세 정보(참여자 리스트 등) 조회.

---

## 2. WebSocket API (Game Session)

실시간 게임 플레이를 위한 양방향 메시지 규격입니다.
Endpoint: `ws://{host}/api/v1/ws/{room_id}?token={jwt}`

### 2.1. Client -> Server (Action)
클라이언트가 서버로 보내는 액션 메시지 형식입니다.

```json
{
  "type": "game_action",
  "payload": {
    "action_id": 16, 
    "action_name": "BUILDER_BUILD",
    "param": "SMALL_MARKET"
  }
}
```

- **type**: `game_action`, `chat_message`, `ping`
- **payload**: 액션에 필요한 구체적인 파라미터.

### 2.2. Server -> Client (Update)
서버가 클라이언트들에게 브로드캐스팅하는 메시지 형식입니다.

```json
{
  "type": "game_update",
  "payload": {
    "current_player": 2,
    "current_phase": "BUILDER",
    "game_state": { ... },
    "action_mask": [0, 1, 0, ...], 
    "last_action": { "player": 1, "action": "SETTLER_TAKE_QUARRY" }
  }
}
```

- **type**: `game_update` (상태 갱신), `game_error` (잘못된 요청), `player_join/leave` (참여자 변경)
- **payload**: 클라이언트가 렌더링에 필요한 전체 게임 데이터.

---

## 3. 유니버설 에이전트 인터페이스 (AI API)

AI 에이전트가 내부적으로 호출받거나(로컬), API로 동작할 때의 입출력 규격입니다.

### 3.1. get_action(game_context) 입출력
```json
// Input (game_context)
{
  "vector_obs": [0.1, 0.5, ...], // 210-dim
  "engine_instance": <PuertoRicoGame Object>,
  "action_mask": [1, 0, 1, ...], // 200-dim
  "phase_id": 2
}

// Output (Recommended Action)
{
  "action_id": 16,
  "confidence": 0.98,
  "agent_type": "PPO_MODEL_V2"
}
```

---

## 4. 에러 코드 및 응답 정책
- **4001**: 인증 실패 (Invalid Token).
- **4002**: 권한 없음 (Not your turn).
- **4003**: 유효하지 않은 액션 (Action masked out).
- **5001**: 엔진 오류 (Internal Engine Crash).
