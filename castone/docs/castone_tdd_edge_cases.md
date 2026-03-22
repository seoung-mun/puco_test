# TDD Edge Cases & Test Scenarios (Castone Backend)

본 문서는 TDD(Test-Driven Development) 프로세스를 위해, `castone` 백엔드 개발 과정에서 발생할 수 있는 주요 엣지 케이스들을 5가지 전문 분야(아키텍처, 보안, 로직, 검증, MLOps) 관점으로 정리한 테스트 명세서입니다.

---

## 1. 🏗️ 아키텍처 및 동시성 제어 (Architecture & Brainstorming)

**핵심 우려 사항**: 다중 접속, Redis Pub/Sub, 비동기 봇 로직 간의 충돌
- **[A-1] Race Condition (Simultaneous Actions)**: 두 유저가 거의 정확히 같은 밀리초(ms)에 액션을 전송했을 때, 상태가 꼬이는가?
    - **Test**: 동시에 10개의 유효한 액션을 HTTP/WS로 쏘아, 단 하나만 적용되고 나머지는 기각됨을 확인. Lock(Redis `SETNX` 혹은 메모리 Lock) 전략 검증.
- **[A-2] Reconnection State Loss**: 게임 도중 클라이언트 브라우저가 끊기고 5분 뒤 다시 재접속할 때.
    - **Test**: `ConnectionManager.disconnect` 직후, 새로운 JWT 송신 시 Redis에 저장된 최신 상태를 정확히 내려주는지, 이전 턴부터 밀렸던 메시지 누락이 없는지 확인.
- **[A-3] Bot Inference Blocking**: 봇이 2초 Delay 후 인퍼런스를 도는 동안, 서버의 메인 이벤트 루프(Event Loop)가 정지하는가?
    - **Test**: 한 방에서 봇이 턴을 진행하는 도중, 다른 방의 유저가 채팅이나 액션을 쐈을 때 지연 없이 처리되는가를 테스트 (즉, 봇 함수가 완전한 Non-blocking `async` 인지 검증).

---

## 2. 🛡️ 보안 방어 (Backend Security Coder)

**핵심 우려 사항**: 권한 우회, 상태 변조, 페이로드 해킹
- **[S-1] Turn Spoofing (턴 위조)**: 현재 자신의 턴이 아닌 유저 코인충(`player_idx=1`)이 몰래 강제 스킵(`action_id=15`) 메시지를 소켓으로 쏘는 경우.
    - **Test**: `JWT` 정보와 현재 엔진의 `current_player_idx`를 대조하여 즉시 `4002 (Not your turn)` 오류를 반환.
- **[S-2] Action Mask Evasion**: 클라이언트가 악용하여 UI에서 숨겨진 액션(예: 돈이 없는데 건물 구매, ID=17)을 강제로 전송하는 경우.
    - **Test**: 서버 측 백엔드가 `engine.valid_action_mask()`를 검증 없이 단순히 믿어버리는지 체크. 악성 액션 수신 시 상태 변경 없이 `4003` 반환.
- **[S-3] Invalid Room ID / Broken Token**: `ws://url/ws/INVALID-ROOM?token=EXPIRED` 로 접속 시도.
    - **Test**: 연결(Handshake) 단계에서 즉시 Connection이 `close(code=1008)` 되며 서버 에러(Traceback)가 터지지 말아야 함.

---

## 4. 📝 입력 검증 및 정적 테스트 (Lint & Validate)

**핵심 우려 사항**: 런타임 이전 런타임 타입 캐스팅 및 문법 결함
- **[V-1] Malformed JSON Payload**: WebSocket을 통해 `{"type": "action", "payload": "DROP TABLE users;"}` 혹은 타입이 잘못된 파라미터가 들어올 경우.
    - **Test**: Pydantic(FastAPI) Schema 검증 모델을 거치지 않고 터지는지(`500 에러`). 제대로 된 `422 Unprocessable Entity` 혹은 웹소켓 형식을 뱉는지 방어 테스트.
- **[V-2] NaN / Invalid Characters**: 채팅이나 방 이름에 이모지, XSS 템플릿 스트링(`<script>`) 삽입.
    - **Test**: 생성 API 단에서 Sanitization/Validation 린팅 에러가 정상적으로 잡아내는지.

---

## 3. 🐞 엔진 상태 불일치 및 디버깅 (Debugger & Logic)

**핵심 우려 사항**: 푸에르토리코 엔진 내부 로직과 래퍼(Wrapper)간의 위상 불일치
- **[D-1] Auto-Pass Loop Exception**: 시장(Mayor) 페이즈에서 놓을 이주민이 없거나 선장(Captain) 페이즈에서 실을 물건이 없어 서버가 자동 패스(Auto-pass) 시켰을 때, 무한 루프에 빠지는 이슈.
    - **Test**: `test_states/`의 엣지케이스(Full Trading House, 0 Colonists)를 불러와 서버 단에서 `game_context` 인젝션이 에러 없이 무한루프를 탈출하여 다음 턴으로 넘기는지 검증.
- **[D-2] Model Fallback**: MCTS 봇이 `Null`이나 마스크에 없는 유효하지 않은 액션을 리턴하는 치명적 런타임 오류 시나리오.
    - **Test**: 에이전트 인터페이스(`bot_service.py`)가 오류를 감지하면 예외를 터트리지 말고 `15번 (Pass)` 또는 랜덤 유효 풀백 액션을 던져, 방 전체 게임 보드가 프리징(Freezing)되는 사태를 막는지 검증.

---

## 5. 🤖 MLOps 데이터 품질 보증 (MLOps Engineer)

**핵심 우려 사항**: 훈련 데이터 손실 및 결측치, 인퍼런스 상태 관리
- **[M-1] Zombie Partial Logs**: 중간에 유저가 도망가거나 엔진 충돌로 게임이 터졌을 때 기록된 (State, Action) 로그들이 어떻게 남는가?
    - **Test**: 완성되지 않은 게임의 로그(Reward가 할당되지 않은 로그)는 명확히 `status: "aborted"`를 찍어 GPU 파이프라인(train)에 오염물로 빨려 들어가지 않음을 증명.
- **[M-2] OOM (Out of Memory) during Inference**: 동시에 너무 많은 방에서 PPO, ONNX 모델이 100회 동시 Inference를 호출당할 때 램 폭발 우려.
    - **Test**: `BotService`의 로컬 워커가 ThreadPool 또는 세마포어(Semaphore)로 동시 실행 개수 한도를 걸어둬 서버 스로틀링만 걸릴 뿐 프로세스가 죽지 않는지 체크.
- **[M-3] NaN in Shaping Rewards**: 엔진 `_compute_potential` 값이 `None` 이나 `NaN`을 뿜어 MLOps 로깅 파일이 망가지는 경우.
    - **Test**: 유저의 승점이 의도적으로 -50인 극단적인 상황에서도 로깅 모듈이 정상 포맷(Float32 보장 등)의 JSON을 내뱉도록 단언(Assert).
