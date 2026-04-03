• 1. 로그 타임라인 요약

  error_logs.md 기준 흐름은 명확합니다.

  1. 게임 시작 직후

  - [BOT_TRACE] schedule_check ... next_idx=0
  - [BOT_TRACE] schedule_human ... idx=0
  - 즉 시작 직후는 human turn입니다.

  2. human action 1회 후

  - [STATE_TRACE] process_action_enter
  - [BOT_TRACE] process_action_turn_check
  - [BOT_TRACE] process_action_mask
  - [STATE_TRACE] sync_to_redis_start/end
  - [STATE_TRACE] process_action_exit
  - 즉 human action 적용과 state sync는 정상입니다.

  3. human action 2회 후 bot handoff

  - [BOT_TRACE] schedule_check ... next_idx=1
  - [BOT_TRACE] schedule_bot ... next_actor=BOT_ppo
  - [BOT_TRACE] task_created
  - 즉 bot task는 실제로 생성됩니다.

  4. bot task 실행

  - [BOT_TRACE] turn_start
  - [BOT_TRACE] turn_mask
  - [BOT_TRACE] phase_id
  - [BOT_TRACE] selected_action
  - [BOT_TRACE] turn_action_selected
  - 즉 bot은 observation/action mask를 읽고 액션도 고릅니다.

  5. bot action 적용

  - [BOT_TRACE] callback_enter
  - [STATE_TRACE] process_action_enter
  - [BOT_TRACE] process_action_turn_check
  - [BOT_TRACE] process_action_mask
  - [STATE_TRACE] sync_to_redis_start/end
  - [STATE_TRACE] process_action_exit
  - [BOT_TRACE] callback_exit
  - [BOT_TRACE] turn_action_applied
  - [BOT_TRACE] task_done cancelled=False exception=None
  - 즉 backend 기준 bot action pipeline은 정상 완료입니다.

  6. 반복

  - 위 흐름이 한 번이 아니라 여러 번 반복됩니다.
  - 즉 backend bot task가 전혀 안 도는 상황이 아닙니다.

  동시에 모든 상태 전파 구간에서 반복되는 로그:

  - [WS_TRACE] ws_broadcast_end ... connection_count=0

  이게 핵심 증거입니다.

  2. 마지막으로 확실히 정상인 단계

  가장 마지막으로 확실히 정상이라고 볼 수 있는 단계는:

  - [BOT_TRACE] turn_action_applied
  - 그리고 그 직전의
  - [STATE_TRACE] process_action_exit
  - [STATE_TRACE] sync_to_redis_end

  이 세 단계입니다.

  의미:

  - bot이 액션을 실제로 선택했고
  - process_action()이 성공했고
  - state 직렬화/Redis sync까지 끝났습니다.

  즉, backend game engine, bot inference, callback, action apply는 정상입니다.

  3. 처음으로 수상한 단계

  처음으로 수상한 단계는:

  - [WS_TRACE] ws_broadcast_end ... connection_count=0

  이 로그가 첫 state update부터, human action 뒤에도, bot action 뒤에도 계속 반복됩니다.

  이 의미는 코드 기준으로 명확합니다.

  관련 파일:

  - backend/app/services/ws_manager.py

  _broadcast()는 self.active_connections[game_id]에 들어 있는 WebSocket들에만 보냅니다.
  connection_count=0이면 해당 game_id로 등록된 활성 게임 WS 연결이 없다는 뜻입니다.

  즉, “메시지를 보냈는데 프론트가 반영을 못 했다”보다 한 단계 앞선 문제, 즉 애초에 게임 WS 연결이 backend에 살아 있지 않다가 더 직접적
  인 의심 지점입니다.

  4. 가장 유력한 원인 1순위~3순위
  5. websocket 연결 실패 또는 연결 직후 끊김

  - 가장 유력합니다.
  - 증거:
      - backend bot pipeline은 정상
      - connection_count=0 반복
  - 즉 backend는 보낼 준비가 되어 있는데 수신자가 없습니다.

  2. 프론트가 게임 WS에 아예 붙지 않음

  - frontend/src/hooks/useGameWebSocket.ts에서 game screen일 때만 연결합니다.
  - gameId 또는 token이 없으면 아예 연결 안 합니다.
  - screen === 'game' ? gameId : null 조건도 있기 때문에 화면 전환 타이밍/상태 값 누락 시 연결 자체가 생기지 않을 수 있습니다.

  3. 연결은 시도하지만 wrong URL / auth / reverse proxy path 문제

  - 프론트는 ws://${location.host}/api/puco/ws/${gameId}로 붙습니다.
  - backend endpoint는 backend/app/api/channel/ws.py의 @router.websocket("/{game_id}")이며 main.py에서 /api/puco/ws prefix로 등록되어
    있습니다.
  - URL 자체는 코드상 맞습니다.
  - 그래서 남는 후보는:
      - location.host가 backend가 아닌 frontend dev server를 가리키는 문제
      - proxy가 WS upgrade를 제대로 안 넘기는 문제
      - auth first message가 안 가거나 invalid token으로 닫히는 문제

  프론트가 메시지를 받아도 state 반영 실패는 현재 우선순위가 더 낮습니다.
  왜냐하면 그 경우 backend에는 최소한 active WS connection이 있어야 하는데, 지금 로그 증거는 connection_count=0입니다.

  5. 관련 파일/함수

  backend

  - backend/app/services/game_service.py
      - process_action()
      - _schedule_next_bot_turn_if_needed()
      - _sync_to_redis()
  - backend/app/services/bot_service.py
      - run_bot_turn()
      - get_action()
  - backend/app/services/ws_manager.py
      - connect()
      - _redis_listener()
      - broadcast_to_game()
      - _broadcast()
  - backend/app/api/channel/ws.py
      - websocket_endpoint()

  frontend

  - frontend/src/hooks/useGameWebSocket.ts
      - connect()
      - ws.onopen
      - ws.onmessage
      - ws.onclose
      - ws.onerror
  - frontend/src/App.tsx
      - useGameWebSocket({...})
      - onStateUpdate: (gs) => setState(...)
      - screen === 'game' ? gameId : null
      - frontend_set_state 경로
      - state.meta.active_player, state.meta.bot_thinking, isBlocked 사용 UI

  6. 최소 수정안

  큰 수정은 필요 없습니다. 지금은 WS 연결 여부를 확정하는 최소 수정만 맞습니다.

  1. 프론트 콘솔에서 실제 game WS 연결 lifecycle 확인

  - 이미 추가한 로그로 충분합니다.
  - 꼭 볼 로그:
      - frontend_ws_connect_attempt
      - frontend_ws_onopen
      - frontend_ws_auth_send
      - frontend_ws_onerror
      - frontend_ws_onclose
      - frontend_ws_message_type

  2. backend WS endpoint에서 실제 접속/인증 성공 여부 확인

  - 이미 추가한 로그로 충분합니다.
  - 꼭 볼 로그:
      - ws_connect
      - ws_receive ... message_type=auth
      - ws_auth_ok_sent
      - ws_subscribe
      - ws_disconnect

  3. frontend dev server/proxy 설정 점검

  - 현재 코드상 프론트 WS URL은 location.host 기반이라, frontend dev server가 backend로 WS proxy를 올바르게 넘겨야 합니다.
  - 이 부분이 실제 1순위 원인 후보입니다.

  즉 최소 수정안은 사실 추가 코드보다 재현 시 프론트 콘솔 + backend 로그를 동시에 보는 것입니다.

  7. 추가 로그가 꼭 필요하면 3개 이하만 제안

  현재는 거의 충분합니다. 그래도 3개만 더 꼽으면:

  1. frontend useGameWebSocket에서 wsUrl과 location.host를 더 명확히 한 줄 출력

  - 현재도 frontend_ws_connect_attempt에 이미 포함되어 있어 사실상 충분

  2. backend ws.py에서 auth 실패 사유별 로그

  - Token required
  - Auth timeout
  - Invalid auth message
  - Invalid token
  - 지금은 disconnect는 찍히지만 close reason은 안 보입니다.

  3. frontend onmessage에서 STATE_UPDATE 수신 후 active_player와 직전 active_player 비교 출력

  - state 반영 실패가 의심될 때만 추가 가치가 있습니다.
  - 지금 단계 우선순위는 낮습니다.

  최종 결론:

  - 첨부 로그만 보면 backend stall 가능성은 낮습니다.
  - backend bot action pipeline은 명백히 정상입니다.
  - 마지막 정상 단계는 turn_action_applied + process_action_exit + sync_to_redis_end입니다.
  - 첫 수상한 단계는 ws_broadcast_end ... connection_count=0입니다.
  - 따라서 이번 분석의 1순위는 프론트가 game websocket에 실제로 연결되지 않았거나, 연결 직후 끊기거나, wrong host/path/auth로 인해
    backend active_connections에 등록되지 않는 문제입니다.