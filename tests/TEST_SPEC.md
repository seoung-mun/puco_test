# Castone TDD/테스트 명세서 (Test Specification)

이 문서는 `castone/backend/app` 등 신규 아키텍처의 각 컴포넌트 단위 동작을 증명하는 TDD 시나리오를 정의합니다.
테스트는 `pytest` 및 `pytest-asyncio` 를 활용하여 루트 디렉터리(`castest/tests/`)에서 독립적으로 실행 가능하게 작성되어야 합니다.

## 1. 테스트 목적
- 과거 단방향(Polling) 방식에서 양방향 WebSocket 기반 멀티플레이어 통신으로 이관된 백엔드 구조가 안정적인지 검증.
- 봇 서비스(PyTorch 추론 모듈 등)가 정상적으로 비동기 이벤트 루프를 방해하지 않고 게임 컨텍스트를 반환하는지 증명.
- 잘못된 접근(Turn Spoofing, 빈 입력, 포맷 오류) 시 예외가 발생하는지 확인.

## 2. 테스트 대상 기능 및 모듈 지정

### 2.1 GameService (`app/services/game_service.py`)
- **[테스트 1] 방 생성 및 초기 상태**: `create_room` 시 방 정보(`GameSession`)가 데이터베이스에 잘 생성되는가?
- **[테스트 2] 액션 검증 (TDD Defense)**: 현재 `engine.action_mask`에 위배되는 잘못된 `action`을 `process_action`에 넣었을 때 `ValueError`를 발생시키고 차단하는지 관찰 (Red -> Green 단계로 증명).
- **[테스트 3] 승패 결정 로직**: 게임 종료(done=True) 시 `room.status = "FINISHED"`로 전환되며 승자가 정상적으로 등록되는가?

### 2.2 WebSocket Manger (`app/services/ws_manager.py` & `ws.py`)
- **[테스트 4] 인증 실패 거부 (Turn Spoofing)**: 잘못된 JWT Token 또는 쿼리 파라미터가 누락된 채로 WebSocket 연결 시도 시, `code=1008` 로 Connection이 즉각 종료되는가?
- **[테스트 5] 방별 동기화 캡슐화**: A 게임방에서 발생한 브로드캐스팅 메시지가 B 게임방 클라이언트들의 소켓으로 흘러가지 않고 완벽히 격리되는가?

### 2.3 BotService (`app/services/bot_service.py`)
- **[테스트 6] PPO 에이전트 인터페이스**: PyTorch 모델(`HierarchicalAgent`)이 정상적으로 인스턴스화되고, 더미 상태 변수(Raw Dict)를 넣었을 때 `get_action(game_context)`가 `int`를 던져주는가?
- **[테스트 7] MLOps JSONL 로깅 비동기 기록 (`ml_logger.py`)**: `process_action` 호출 시, `log_transition`이 실행되어 실제로 지정된 `/logs/` 디렉터리에 `.jsonl` 줄이 기록되는가? (Temp Directory를 활용해 File I/O 확인)

## 3. 실행 방법
```bash
cd /Users/seoungmun/Documents/agent_dev/castest
pytest tests/ -v --asyncio-mode=auto
```
