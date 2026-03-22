# Implementation Guide: Castone Backend (AI Handoff)

본 문서는 AI 코딩 어시스턴트가 `castone` 멀티플레이어 백엔드를 즉시 구현할 수 있도록 핵심 로직과 구조를 정리한 가이드라인입니다.

## 1. 프로젝트 구조 (Target Structure)

- `castone/backend/app/`
    - `main.py`: FastAPI 앱 초기화 및 미들웨어 설정.
    - `api/v1/endpoints/`: REST API 엔드포인트 (Auth, Room).
    - `services/`
        - `ws_manager.py`: WebSocket 연결 및 Redis Pub/Sub 핸들러.
        - `room_manager.py`: 개별 방의 게임 엔진 상태 및 수명이 주기 관리.
        - `bot_service.py`: 봇 추론 로직 (Universal Agent Interface 적용).
    - `schemas/`: Pydantic 모델 정의.
    - `models/`: SQLAlchemy (Postgres) DB 모델.

## 2. 핵심 구현 로직 (Core Implementation Logic)

### 2.1. `RoomManager` (핵심)
- 모든 게임 인스턴스를 메모리(`Dict[game_id, PuertoRicoGame]`)에 관리합니다.
- `action_mayor_pass`, `action_captain_pass` 등 수동 조작이 필요한 엔진 함수를 래핑하여 `game_context`와 연동합니다.
- 특정 액션 후 게임이 종료되었는지(`check_game_end`) 여부를 판단하여 DB에 기록합니다.

### 2.2. `ws_manager.py` (실시간성)
- `ConnectionManager` 클래스를 사용하여 각 `room_id`별로 사용자 소켓 그룹을 관리합니다.
- 한 세션에서 액션이 발생하면 Redis Pub/Sub을 이용해 동일한 `room_id` 전용 채널에 메시지를 발행(Publish)합니다.
- 각 서버 인스턴스는 해당 채널을 구독(Subscribe)하여 자기에게 연결된 소켓들에 `game_update`를 전파합니다.

### 2.3. `bot_service.py` (AI 연동)
- `get_action(game_context)` 표준 인터페이스를 구현합니다.
- 입력값: `vector_obs`, `engine_instance`, `action_mask`, `phase_id`.
- 봇의 턴이 돌아오면 `asyncio.sleep(2.0)` 후 추론 결과를 `RoomManager`에 전달합니다.

## 3. MLOps 데이터 로깅 규칙

- `ml_logger.py` 모듈을 생성하여 모든 턴의 데이터를 `/data/logs/{game_id}.jsonl`에 저장합니다.
- 저장 포맷: `{"timestamp": ..., "state": [...], "action": ..., "reward": ...}`.

## 4. 즉시 실행 가능한 다음 단계 (Next Steps)

1. **DB 통합**: `models.py`에 유저 및 방 정보를 위한 Postgres 스키마를 정의합니다.
2. **WebSocket 기반 마련**: `castone/backend/app/services/ws_manager.py`를 작성하고 Redis 연동을 확인합니다.
3. **엔진 마운트**: `Dockerfile`에서 `PuCo_RL` 폴더를 `/PuCo_RL` 경로로 마운트하고 `PYTHONPATH`를 설정합니다.
4. **봇 추론 엔진 수립**: `bot_runner.py`의 로직을 `bot_service.py`로 이식하고 ONNX 모델 로딩 부분을 구현합니다.
