# Backend 구조 및 디버깅 가이드

작성 목적:

- 이 프로젝트의 `backend/`가 어떤 구조로 돌아가는지 이해한다.
- 특히 현재처럼 "봇 턴에서 멈춘다", "프론트가 상태를 못 받는다", "WS가 안 붙는 것 같다" 같은 문제를 추적할 때 어떤 부분을 알아야 하는지 정리한다.
- 단순 디렉터리 설명이 아니라, 실제 런타임 데이터 흐름과 디버깅 포인트 중심으로 설명한다.

---

## 1. 백엔드를 한 문장으로 요약하면

이 백엔드는 **FastAPI 기반의 게임 서버**이고, 내부적으로는:

1. PostgreSQL에 방/유저/게임 로그를 저장하고
2. Redis를 상태 브로드캐스트와 연결 상태 관리에 쓰고
3. `PuCo_RL` 엔진을 `EngineWrapper`로 감싼 뒤
4. `GameService`가 게임 진행을 관리하고
5. `BotService`가 봇 액션을 고르고
6. WebSocket과 Redis publish를 통해 프론트에 상태를 전달한다.

즉, 핵심은 다음 4개 계층이다.

- API 계층: FastAPI 라우터
- 서비스 계층: 게임 진행, 봇, 상태 직렬화, WS 관리
- 엔진 어댑터 계층: `PuCo_RL`를 감싸는 wrapper
- 인프라 계층: PostgreSQL, Redis, WebSocket

---

## 2. 디렉터리 구조를 실전 기준으로 읽는 법

### 2.1 진입점

관련 파일:

- [backend/app/main.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/main.py)

역할:

- FastAPI 앱 생성
- CORS 설정
- startup 시 DB/Redis health check
- 라우터 등록

이 파일은 "서버가 켜지는가"를 보는 곳이다. 게임 로직은 거의 없고, 어떤 API와 WS 엔드포인트가 열리는지 확인하는 용도다.

### 2.2 API 계층

관련 디렉터리:

- [backend/app/api/channel](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel)
- [backend/app/api/legacy](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/legacy)

의미:

- `channel`은 현재 프론트가 사용하는 최신 API/WS 계층이다.
- `legacy`는 이전 세대 호환 계층이다.

현재 디버깅에서 우선적으로 봐야 할 파일:

- [backend/app/api/channel/room.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/room.py)
- [backend/app/api/channel/game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/game.py)
- [backend/app/api/channel/ws.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/ws.py)
- [backend/app/api/channel/lobby_ws.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/lobby_ws.py)
- [backend/app/api/channel/auth.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/auth.py)

### 2.3 서비스 계층

관련 디렉터리:

- [backend/app/services](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services)

이곳이 실제 핵심이다.

문제 유형별 중심 파일:

- 게임 진행: [game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
- 봇 추론 및 턴 실행: [bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)
- 엔진 상태 -> 프론트 상태 변환: [state_serializer.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/state_serializer.py)
- WS 연결 및 브로드캐스트: [ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py)
- 로비 실시간 갱신: [lobby_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/lobby_manager.py)
- 모델 선택/로딩: [agents/factory.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/agents/factory.py), [agents/wrappers.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/agents/wrappers.py)

### 2.4 엔진 어댑터 계층

관련 파일:

- [backend/app/engine_wrapper/wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py)

이 파일은 매우 중요하다.

이유:

- 실제 게임 규칙은 `PuCo_RL` 안에 있다.
- 그러나 백엔드는 `PuCo_RL`를 직접 여기저기 만지지 않고 `EngineWrapper`를 통해 접근한다.
- 그래서 엔진 drift, 상태 구조 차이, observation/action mask 추출 문제는 이 wrapper에서 흡수하는 게 기본 전략이다.

### 2.5 DB/인프라 계층

관련 파일:

- [backend/app/db/models.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/db/models.py)
- [backend/app/dependencies.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/dependencies.py)
- [backend/app/core/redis.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/core/redis.py)
- [backend/alembic](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/alembic)

역할:

- `dependencies.py`: SQLAlchemy engine/session 생성
- `models.py`: `User`, `GameSession`, `GameLog`
- `redis.py`: sync/async Redis client

---

## 3. 런타임에서 실제로 무슨 일이 일어나는가

이 섹션이 가장 중요하다.

현재 구조를 이해하려면 "HTTP 요청이 들어와서 게임 상태가 바뀌고, 봇이 이어서 두고, 프론트가 그 상태를 받는 과정"을 머릿속에서 그릴 수 있어야 한다.

### 3.1 방 생성

관련 파일:

- [room.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/room.py)
- [models.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/db/models.py)

흐름:

1. 프론트가 `POST /api/puco/rooms/`
2. 백엔드가 `GameSession` row 생성
3. `players` 컬럼에 현재 유저 id를 넣음
4. `status="WAITING"`

핵심 필드:

- `games.id`
- `games.players`
- `games.host_id`
- `games.status`

중요 포인트:

- `players`는 JSON 배열이다.
- 사람은 UUID 문자열
- 봇은 `"BOT_ppo"`, `"BOT_random"` 같은 문자열

즉, 사람과 봇이 같은 `players` 배열 안에 공존한다.

### 3.2 방에 봇 추가

관련 파일:

- [game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/game.py)

흐름:

1. `POST /api/puco/game/{game_id}/add-bot`
2. `room.players.append(f"BOT_{bot_type}")`
3. DB commit

중요:

- 봇은 별도 테이블이 없다.
- 그냥 `players` 배열의 한 슬롯으로 존재한다.

즉, turn 판별도 결국 `room.players[current_idx]`가 사람인지 `BOT_`인지 보는 방식이다.

### 3.3 게임 시작

관련 파일:

- [game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/game.py)
- [game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
- [wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py)

흐름:

1. `POST /api/puco/game/{game_id}/start`
2. `GameService.start_game(game_id)`
3. DB에서 room을 읽는다.
4. `create_game_engine(num_players=actual_players)`로 `EngineWrapper` 생성
5. `GameService.active_engines[game_id] = engine`에 저장
6. `serialize_game_state_from_engine(...)`로 프론트용 rich state 생성
7. `_sync_to_redis()`로 Redis와 WS에 상태 전달
8. `_schedule_next_bot_turn_if_needed()` 호출

중요:

- 실제 게임 엔진 인스턴스는 DB에 저장되지 않는다.
- 메모리의 `GameService.active_engines` 딕셔너리에만 있다.
- 따라서 서버 프로세스가 죽거나 재시작되면 active engine은 날아간다.

이건 매우 중요하다.

왜냐하면:

- "DB에 방은 있는데 엔진이 없다"는 상태가 가능하다.
- 이런 경우 `process_action`에서 `Active game engine not found`가 날 수 있다.

### 3.4 인간 액션 처리

관련 파일:

- [game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/game.py)
- [game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)

흐름:

1. 프론트가 `POST /api/puco/game/{game_id}/action`
2. payload에 `action_index`를 넣어 보냄
3. `GameService.process_action(...)`
4. 현재 turn player와 `actor_id` 일치 여부 검사
5. `action_mask[action]`가 유효한지 검사
6. `engine.step(action)` 호출
7. 로그 저장 (`GameLog`)
8. 새 rich state 직렬화
9. `_sync_to_redis()`
10. 다음 플레이어가 bot이면 `_schedule_next_bot_turn_if_needed()`

### 3.5 봇 턴 처리

관련 파일:

- [game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
- [bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)

흐름:

1. `GameService._schedule_next_bot_turn_if_needed()`
2. `next_idx = engine.env.game.current_player_idx`
3. `next_actor = room.players[next_idx]`
4. `next_actor.startswith("BOT_")`면 bot turn으로 판단
5. `asyncio.create_task(BotService.run_bot_turn(...))`
6. `run_bot_turn()` 내부에서 delay 후 action 선택
7. `process_action_callback()`으로 다시 `GameService.process_action()` 호출

즉, 봇도 최종적으로는 사람과 같은 `process_action()` 경로를 탄다.

중요한 의미:

- bot 전용 별도 step 로직이 있는 게 아니다.
- bot은 단지 "누가 action_index를 고르느냐"만 다르다.
- 선택 후 적용은 동일 경로다.

그래서 디버깅할 때는:

- bot이 액션을 못 고르는지
- 골랐는데 `process_action()`에서 막히는지
- 적용됐는데 프론트가 못 받는지

를 분리해야 한다.

---

## 4. 엔진 wrapper를 꼭 이해해야 하는 이유

관련 파일:

- [wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py)

이 프로젝트에서 `PuCo_RL`는 사실상 black box이다.

백엔드는 엔진을 이렇게 본다.

- `engine.env` 안에 실제 PettingZoo/AEC 엔진이 있다.
- `engine.env.game` 안에 내부 게임 객체가 있다.
- `EngineWrapper`는 `last_obs`, `last_action_mask`, `last_info`를 캐시한다.

백엔드가 실제로 자주 보는 값:

- `engine.env.game.current_player_idx`
- `engine.env.game.governor_idx`
- `engine.env.agent_selection`
- `engine.last_obs`
- `engine.get_action_mask()`

### 4.1 왜 `current_player_idx`, `agent_selection`, `room.players`를 같이 봐야 하나

이 세 개는 각기 의미가 다르다.

- `room.players[i]`
  - DB에 저장된 "i번째 플레이어 슬롯"
- `current_player_idx`
  - 엔진이 지금 누구 차례라고 보는지
- `agent_selection`
  - PettingZoo AEC 관점에서 현재 active agent 이름

정상이라면 이 셋이 논리적으로 맞아야 한다.

예:

- `current_player_idx = 1`
- `room.players[1] = "BOT_ppo"`
- `agent_selection = "player_1"`

이게 어긋나면 이상 증상이 난다.

예:

- 프론트는 bot turn처럼 보이는데 backend는 human turn으로 판단
- bot callback은 들어왔는데 `expected_actor`가 사람으로 계산
- action mask는 다른 agent 기준으로 읽힘

그래서 현재 디버깅에서 이 세 값을 항상 같이 로그로 찍는 것이 중요하다.

### 4.2 governor가 왜 민감한가

이 프로젝트에서는 wrapper가 시작 시 governor를 `player_0` 쪽으로 맞추는 정책이 있다.

의미:

- UI/room owner 기준으로 일관성을 맞추려는 목적

부작용 가능성:

- 엔진 내부 초기 분배 규칙과 충돌하면 turn/initial state 착시 가능

다만, 현재 stall 문제를 볼 때는 governor 문제와 bot task lifecycle 문제를 분리해서 보는 게 맞다.

---

## 5. 상태 직렬화는 어디서 일어나는가

관련 파일:

- [state_serializer.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/state_serializer.py)

역할:

- `engine.env.game`의 내부 구조를 프론트가 쓰는 JSON으로 변환

중요:

- 프론트는 엔진 객체를 직접 모른다.
- 프론트가 보는 것은 serializer가 만든 `GameState`뿐이다.

즉, 프론트 화면이 이상하면 원인은 크게 둘 중 하나다.

1. 엔진 상태가 잘못됨
2. serializer가 잘못 번역함

예:

- 엔진은 진행됐는데 프론트 active player가 안 바뀜
- `action_mask`가 빠지거나 stale
- building/colonist/goods 정보가 누락

현재 serializer는 drift 대응을 위해 `_safe_get`, `_safe_int` 같은 보강이 일부 들어가 있다.

---

## 6. 프론트와의 통신 방식

이 프로젝트는 현재 게임 상태를 주로 **WebSocket**으로 전달한다.

### 6.1 게임 상태 WS

프론트 파일:

- [frontend/src/hooks/useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)
- [frontend/src/App.tsx](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/App.tsx)

백엔드 파일:

- [backend/app/api/channel/ws.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/ws.py)
- [backend/app/services/ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py)

흐름:

1. 프론트가 `ws://host/api/puco/ws/{gameId}` 연결
2. 연결 직후 `{ token }` 첫 메시지 전송
3. 백엔드가 JWT 검증
4. `manager.connect(game_id, websocket, player_id)`
5. 이후 서버는 `STATE_UPDATE` 메시지를 push

프론트는 `STATE_UPDATE` 외에는 거의 게임 상태로 사용하지 않는다.

즉, 프론트가 game screen에서 stale하면 먼저 WS를 의심해야 한다.

### 6.2 Redis + WS manager

관련 파일:

- [game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
- [ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py)
- [redis.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/core/redis.py)

흐름:

1. `GameService._sync_to_redis()`가 상태를 Redis key에 저장
2. 같은 상태를 Redis pub/sub channel에 publish
3. `ConnectionManager._redis_listener(game_id)`가 이를 수신
4. 활성 WS 연결들에 `_broadcast()`
5. fallback으로 `broadcast_to_game()` direct path도 사용

즉, 상태 전달 경로는 사실 두 개다.

- Redis pub/sub 경로
- direct in-memory broadcast 경로

디버깅할 때는 둘 다 봐야 한다.

### 6.3 로비 WS

관련 파일:

- [backend/app/api/channel/lobby_ws.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/lobby_ws.py)
- [backend/app/services/lobby_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/lobby_manager.py)

이건 게임 상태 WS와 별개다.

주의:

- 로비 WS는 room/lobby 상태용
- 게임 WS는 actual game state용

즉, 로비가 잘 보여도 게임 WS가 문제면 실제 대국 화면은 stale할 수 있다.

---

## 7. DB는 무엇을 저장하고 무엇을 저장하지 않는가

관련 파일:

- [models.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/db/models.py)

### 저장하는 것

- 유저 계정
- 방 메타데이터
- 플레이어 배열
- 게임 로그 (`GameLog`)
- 상태 전/후 snapshot

### 저장하지 않는 것

- live engine instance
- live asyncio task
- live websocket connection

이 차이를 이해해야 한다.

예:

- DB상으로는 `games.status = PROGRESS`
- 하지만 메모리 engine 없음
- 프론트는 게임 진행 중이라 생각
- 백엔드는 action 처리 불가

즉, DB만 보고는 live runtime을 다 알 수 없다.

---

## 8. 현재 문제를 해결하려면 반드시 알아야 하는 디버깅 축

현재와 같은 "봇 턴 stall" 또는 "프론트 Bot 대기중 고정" 문제를 풀려면 아래 순서로 봐야 한다.

### 축 1. bot lifecycle

관련 파일:

- [game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
- [bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)

질문:

- bot이 스케줄됐는가
- task가 생성됐는가
- task가 예외 없이 끝났는가
- callback이 들어갔는가
- `process_action()`이 실제로 실행됐는가

현재 추가된 trace:

- `[BOT_TRACE] schedule_check`
- `[BOT_TRACE] schedule_bot`
- `[BOT_TRACE] task_created`
- `[BOT_TRACE] task_done`
- `[BOT_TRACE] callback_enter`
- `[BOT_TRACE] callback_exit`
- `[BOT_TRACE] process_action_enter`
- `[BOT_TRACE] process_action_exit`

### 축 2. state propagation

관련 파일:

- [game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
- [ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py)

질문:

- 상태가 Redis에 저장됐는가
- publish됐는가
- listener가 수신했는가
- broadcast 대상 connection이 있었는가

현재 추가된 trace:

- `[STATE_TRACE] sync_to_redis_start/end/error`
- `[WS_TRACE] redis_listener_subscribed`
- `[WS_TRACE] redis_listener_message_received`
- `[WS_TRACE] redis_listener_broadcast_dispatch`
- `[STATE_TRACE] ws_broadcast_start/end/error`

### 축 3. front connection lifecycle

관련 파일:

- [frontend/src/hooks/useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)
- [backend/app/api/channel/ws.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/ws.py)
- [backend/app/services/ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py)

질문:

- 프론트가 `/api/puco/ws/{gameId}`에 실제 연결하는가
- 인증 첫 메시지를 보내는가
- 백엔드가 user_id를 식별했는가
- 연결이 유지되는가

현재 추가된 trace:

- `[WS_TRACE] ws_connect`
- `[WS_TRACE] ws_receive`
- `[WS_TRACE] ws_disconnect`

---

## 9. 실제 오류를 잡을 때 추천하는 읽기 순서

### 9.1 게임이 안 시작된다면

1. [main.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/main.py)
2. [dependencies.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/dependencies.py)
3. [core/redis.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/core/redis.py)
4. docker compose / env

확인할 것:

- `DATABASE_URL`
- `REDIS_URL`
- `SECRET_KEY`
- Postgres/Redis health

### 9.2 봇이 안 두는 것 같다면

1. [game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
2. [bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)
3. [wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py)

확인할 것:

- `current_player_idx`
- `room.players`
- `next_actor`
- `agent_selection`
- `action_mask`
- `phase_id`

### 9.3 봇은 두는 것 같은데 화면이 안 바뀐다면

1. [game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
2. [ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py)
3. [ws.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/ws.py)
4. [useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)

확인할 것:

- `sync_to_redis_end`
- `redis_listener_message_received`
- `ws_connect`
- `ws_broadcast_end connection_count`
- 프론트 `onmessage`

---

## 10. 지금 상태에서 특히 주의해서 봐야 할 구조적 포인트

### 10.1 `GameService.active_engines`는 메모리 저장소다

이건 프로덕션 수준의 durable storage가 아니다.

뜻:

- 리로더 재시작
- 프로세스 크래시
- multi-worker

같은 조건에서 상태가 꼬일 수 있다.

현재 디버깅 중에는 항상 "DB 상태"와 "메모리 engine 상태"를 구분해서 봐야 한다.

### 10.2 `players` 배열은 turn semantics의 기준이다

봇 판별도 여기서 한다.

즉, `room.players` 순서가 어긋나면:

- wrong actor
- bot/human 오판별
- callback mismatch

같은 문제가 난다.

### 10.3 game WS와 lobby WS는 별개다

이걸 헷갈리면 문제를 잘못 본다.

예:

- 로비는 실시간으로 잘 움직임
- 하지만 게임 WS가 안 붙음

이 경우 사용자는 "봇이 멈췄다"고 느끼지만 실은 game WS 문제일 수 있다.

### 10.4 프론트는 WS 실패를 크게 드러내지 않는다

`useGameWebSocket`에는:

- `onopen`
- `onmessage`
- `onclose`

는 있지만,

- 눈에 띄는 `onerror`
- UI error 승격
- 연결 상태 표시

가 부족하다.

즉, 실제 연결 실패가 "Bot 대기중 화면 유지"로 보일 수 있다.

---

## 11. 현재 문제 해결을 위해 최소한 이해해야 하는 파일 우선순위

### 반드시 읽어야 하는 1순위

- [backend/app/services/game_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/game_service.py)
- [backend/app/services/bot_service.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/bot_service.py)
- [backend/app/engine_wrapper/wrapper.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/engine_wrapper/wrapper.py)
- [backend/app/services/ws_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/ws_manager.py)
- [backend/app/api/channel/ws.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/ws.py)
- [frontend/src/hooks/useGameWebSocket.ts](/Users/seoungmun/Documents/agent_dev/castest/castone/frontend/src/hooks/useGameWebSocket.ts)

### 2순위

- [backend/app/services/state_serializer.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/state_serializer.py)
- [backend/app/api/channel/game.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/game.py)
- [backend/app/api/channel/room.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/channel/room.py)
- [backend/app/db/models.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/db/models.py)

### 참고용

- [backend/app/services/session_manager.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/services/session_manager.py)
- [backend/app/api/legacy/deps.py](/Users/seoungmun/Documents/agent_dev/castest/castone/backend/app/api/legacy/deps.py)

주의:

- `session_manager.py`와 `legacy/*`는 예전 흐름도 담고 있어서 참고는 되지만, 현재 channel API 디버깅에서는 1순위가 아니다.

---

## 12. 마지막 요약

이 백엔드를 이해할 때 가장 중요한 포인트는 다음 다섯 가지다.

1. **게임 엔진은 메모리에만 살아 있고, DB는 메타데이터와 로그만 저장한다.**
2. **봇도 결국 사람과 같은 `process_action()` 경로로 액션을 적용한다.**
3. **bot/human 판별은 `room.players[current_player_idx]`에 크게 의존한다.**
4. **프론트 게임 상태는 현재 SSE가 아니라 game WebSocket으로 받는다.**
5. **문제는 엔진/봇/상태전파/프론트반영 중 어디서 끊기는지 분리해야 풀린다.**

지금 같은 stall/대기 문제를 디버깅할 때는 항상 이 순서로 보면 된다.

1. bot task가 생성됐는가
2. action selection이 끝났는가
3. `process_action()`이 실행됐는가
4. state sync가 됐는가
5. WS connection이 존재하는가
6. 프론트가 `STATE_UPDATE`를 처리하는가

이 흐름을 기준으로 보면, 단순히 "봇이 안 움직인다"는 현상을 더 작고 명확한 단계 문제로 쪼갤 수 있다.

