
# API Specification: Puerto Rico AI Battle Platform

## 1. 개요 및 인증 (Overview & Auth)

- **Base URL:** `/api/v1`
    
- **인증 방식:** Bearer JWT (Google OAuth 기반)
    
- **에러 응답:** 모든 에러는 `{"error_code": string, "message": string}` 형식을 따른다.
    

### [POST] /auth/google

- **설명:** 프론트엔드(NextAuth)에서 받은 Google ID 토큰을 검증하고 서비스 전용 JWT를 발급한다.
    
- **Request:** `{ "id_token": "string" }`
    
- **Response:** ```json
    
    {
    
    "access_token": "jwt_string",
    
    "user": { "id": "uuid", "nickname": "string", "win_rate": 0.0, "total_games": 0 }
    
    }
    

---

## 2. 방 관리 API (Room Management)

사용자가 직접 방을 생성하고 에이전트 구성을 설정한다.

### [GET] /rooms

- **설명:** 현재 입장 가능한 방 목록을 조회한다.
    

### [POST] /rooms

- **설명:** 새로운 게임 방을 생성한다.
    
- **Request:**
    
    JSON
    
    ```
    {
      "title": "string",
      "config": {
        "agent_count": 1, // 0~2
        "agent_difficulty": "EASY | MEDIUM | HARD",
        "max_players": 2
      }
    }
    ```
    

### [POST] /rooms/{room_id}/join

- **설명:** 특정 방에 입장한다.
    

---

## 3. 게임 액션 API (Game Interaction)

모든 게임 로직은 서버에서 판정하며, 단일 엔드포인트를 통해 액션을 수집한다.

### [POST] /game/action

- **설명:** 현재 턴의 플레이어(또는 에이전트 요청)가 수행하는 모든 행동.
    
- **Request Body:**
    
    JSON
    
    ```
    {
      "game_id": "uuid",
      "action_type": "ROLE_SELECTION | BUILD | PLANT | MAYOR_DISTRIBUTE | TRADER_SELL | CAPTAIN_LOAD",
      "payload": {
        "role": "BUILDER",        // ROLE_SELECTION 인 경우
        "building_id": "factory", // BUILD 인 경우
        "tile_index": 1,          // PLANT 인 경우
        "distribution": { ... }   // MAYOR_DISTRIBUTE 인 경우
      }
    }
    ```
    
- **Validation:** 서버 엔진은 해당 액션의 유효성을 검증하고, 실패 시 `400 Bad Request`와 함께 이유를 반환한다.
    

---

## 4. 실시간 상태 동기화 (WebSocket)

- **Endpoint:** `ws://server/ws/game/{game_id}`
    
- **기능:** 게임 상태 변화 발생 시 모든 연결된 클라이언트에 브로드캐스트.
    
- **Message Type:**
    
    - `STATE_UPDATE`: 전체 보드 스냅샷 전송.
        
    - `PLAYER_EVENT`: 입장, 퇴장, 준비 완료 알림.
        

---

## 5. 데이터베이스 및 로그 설계 (Database & RL Logging)

### 5.1 데이터베이스 스키마

- **`users` 테이블:** 유저 고유 ID, 전적(승률), Google ID 저장.
    
- **`games` 테이블:** 게임 생성 정보, 참여 인원, 현재 상태(진행중/종료) 관리.
    
- **`game_logs` 테이블 (RL 전용):** PostgreSQL **JSONB** 타입을 사용하며, `round` 컬럼 기준 **Partitioning** 적용.
    

### 5.2 강화학습 로그 데이터 구조

모든 `/game/action` 성공 시 서버는 아래의 스냅샷을 자동으로 DB에 기록한다.

|**필드명**|**데이터 타입**|**설명**|
|---|---|---|
|`game_id`|UUID|게임 식별자|
|`round`|Integer|현재 라운드 (파티션 키)|
|`step`|Integer|게임 내 절대 액션 순서|
|`actor_id`|String|행동을 수행한 유저/에이전트 ID|
|`action_data`|JSONB|수행된 액션의 세부 파라미터|
|`available_options`|JSONB|**[필수]** 당시 선택 가능했던 모든 후보군 (Action Masking 데이터)|
|`state_before`|JSONB|액션 직전의 플레이어별 일꾼 배치, 자원, 농장 등 전체 스냅샷|
|`state_after`|JSONB|액션 적용 후의 전체 보드 스냅샷|

---

## 6. 특별 구현 지침 (Special Instructions)

1. **시장 페이즈(Mayor Phase) 기록:** 일꾼 재배치 시, 단순히 '누가 어디로 갔다'가 아니라 **'재배치 전 전체 배치'**와 **'재배치 후 최종 배치'**를 각각 `state_before`와 `state_after`에 담아야 한다.
    
2. **에이전트 요청 처리:** 에이전트의 차례인 경우 백엔드 스케줄러가 에이전트 라이브러리를 호출하고, 그 결과값을 `/action` 로직과 동일한 프로세스로 처리하여 로그를 남긴다.
    
3. **서버 사이드 검증:** 프론트엔드에서 보낸 모든 데이터는 불신하며, 서버 엔진의 현재 상태와 대조하여 유효한 액션인지를 최우선으로 검크한다.