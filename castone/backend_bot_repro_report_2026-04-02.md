 1. 원인 후보 우선순위 재정렬
  2. bot task는 생성되지만, process_action callback 전후에서 실패하거나 조용히 종료되는 경우

  - 새 관찰 기준에 가장 잘 맞습니다.
  - backend/app/services/bot_service.py에서 bot turn은 run_bot_turn() 하나에 걸려 있습니다.
  - 여기서 get_action_mask(), get_action(), process_action_callback() 중 하나가 실패하면 진행이 멈출 수 있습니다.
  - 특히 현재는 “task가 살아 있었는지”, “callback까지 갔는지”, “callback이 예외로 끝났는지”를 충분히 구분하는 로그가 부족했습니다.

  2. bot action은 백엔드에서 적용됐지만, 프론트가 상태 업데이트를 못 받는 경우

  - 이건 여전히 상위 후보입니다.
  - 이유는 제가 백엔드 단독 재현에서는 실제로 bot action이 DB에 쌓이는 케이스를 봤기 때문입니다.
  - 반면 사용자 체감은 “계속 Bot 대기중”입니다.
  - 즉 실제 문제는 “bot이 안 뒀다”가 아니라 “bot은 뒀는데 프론트가 못 본다”일 수도 있습니다.
  - 후보 위치는 backend/app/services/game_service.py의 _sync_to_redis()와 backend/app/services/ws_manager.py의 Redis listener/
    broadcast 경로입니다.

  3. 특정 phase에서 action_mask 또는 obs가 비정상이라 bot task가 매번 실패하는 경우

  - all-bot이나 단순 phase에서는 잘 되더라도, 특정 게임 상태에서만 stall이 날 수 있습니다.
  - 특히 backend/app/services/bot_service.py의 current_phase, action_mask, last_obs가 phase-dependent하게 깨지면, 선택 액션이 계속 거
    부되거나 task가 종료될 수 있습니다.
  - 이 경우 프론트는 계속 bot active turn만 보게 됩니다.

  4. room.players 기준 bot 판별과 엔진의 current_player_idx/agent_selection이 어긋나는 경우

  - backend/app/services/game_service.py의 _schedule_next_bot_turn_if_needed()는 DB의 room.players[next_idx]를 보고 bot 여부를 판단합
    니다.
  - 엔진 쪽 active turn은 engine.env.game.current_player_idx와 agent_selection입니다.
  - 이 셋이 특정 시점에 어긋나면 프론트는 bot turn처럼 보이는데 백엔드는 human으로 취급하거나, 반대로 잘못된 actor로 callback을 호출할
    수 있습니다.

  5. delay 가설

  - 이제 우선순위는 낮습니다.
  - delay는 stall 설명의 보조 요소일 뿐, 주원인 후보에서 내려야 합니다.

  2. delay 착시 가설을 왜 낮춰야 하는가

  - backend/app/services/bot_service.py의 delay는 현재 2.0s 또는 3.0s로 고정입니다.
  - 사용자가 관찰한 것은 2~3분 이상 무변화입니다.
  - 하드코드 상수만으로는 이 시간을 설명할 수 없습니다.
  - 제가 본 재현 로그에서도 bot task가 정상일 때는 turn_start -> turn_delay -> turn_action_selected -> turn_action_applied가 몇 초 안
    에 끝났습니다.
  - 따라서 지금부터는 “지연 때문에 멈춘 것처럼 보인다”가 아니라 “bot turn pipeline 어딘가에서 실제 정지 또는 상태 미반영이 난다”를 기
    준으로 봐야 합니다.

  3. 실제 stall을 만들 수 있는 지점 3~5개
  4. _schedule_next_bot_turn_if_needed()에서 task가 실제로 생성되지 않는 지점

  - 파일: backend/app/services/game_service.py
  - 조건:
      - next_idx가 잘못됨
      - room.players[next_idx]가 BOT_로 시작하지 않음
      - asyncio.create_task()가 실패
  - 증상:
      - 프론트는 bot active turn처럼 보일 수 있지만, 실제 bot task는 없음

  2. run_bot_turn() 진입 후 get_action_mask() 또는 last_obs 단계에서 죽는 지점

  - 파일: backend/app/services/bot_service.py
  - 조건:
      - engine.get_action_mask() 예외
      - engine.last_obs 비정상
      - phase_id 추출 실패
  - 증상:
      - task는 생성됐지만 action 선택까지 못 감

  3. get_action()은 끝났지만 process_action_callback()에서 막히거나 실패하는 지점

  - 파일: backend/app/services/bot_service.py
  - callback 구현 위치:
      - backend/app/services/game_service.py의 sync_callback
  - 조건:
      - GameService.process_action()에서 invalid action
      - DB/Redis/commit 문제
      - callback이 예외 후 fallback도 실패
  - 증상:
      - bot은 액션을 골랐지만 state는 안 움직임

  4. process_action()은 성공했지만 상태 전파가 프론트에 전달되지 않는 지점

  - 파일:
      - backend/app/services/game_service.py
      - backend/app/services/ws_manager.py
  - 조건:
      - _sync_to_redis()는 실패
      - Redis pub/sub listener가 안 돌음
      - direct broadcast 실패
  - 증상:
      - DB 로그는 증가하는데 프론트는 계속 “Bot 대기중”

  5. phase-specific invalid state

  - 파일:
      - backend/app/engine_wrapper/wrapper.py
      - backend/app/services/bot_service.py
  - 조건:
      - 특정 phase에서 action_mask는 존재하지만 실제 callback 적용 시 거부
      - agent_selection과 current_player_idx가 phase 전환 중 어긋남
  - 증상:
      - 특정 phase에서만 재현되고 일반 케이스는 정상

  4. 각 지점마다 반드시 확인해야 할 로그 포인트
  5. 스케줄링 단계

  - 위치: backend/app/services/game_service.py
  - 로그:
      - game_id
      - next_idx
      - current_player_idx
      - governor_idx
      - agent_selection
      - room.players
      - next_actor
      - is_bot
      - task_id
  - 목적:
      - “봇이 스케줄링되지 않는지” 즉시 구분

  2. task lifecycle

  - 위치: backend/app/services/game_service.py
  - 로그:
      - task 생성 직후
      - task done callback에서 cancelled, exception, result
  - 목적:
      - “스케줄링되지만 task가 즉시 죽는지” 구분

  3. bot turn 내부

  - 위치: backend/app/services/bot_service.py
  - 로그:
      - turn_start
      - turn_mask
      - phase_id
      - valid_action_count
      - selected_action
      - callback_start
      - callback_success
      - callback_exception
      - fallback_retry_start
      - fallback_retry_success/failure
  - 목적:
      - “액션을 못 고르는지 / 골랐는데 적용이 실패하는지” 구분

  4. process_action 내부

  - 위치: backend/app/services/game_service.py
  - 로그:
      - actor_id
      - expected_actor
      - current_player_idx
      - action
      - mask[action]
      - terminated
      - _sync_to_redis start/end
      - _schedule_next_bot_turn_if_needed start/end
  - 목적:
      - callback이 실제로 들어왔는지와, 적용 후 전파까지 갔는지 확인

  5. 상태 전파

  - 위치:
      - backend/app/services/game_service.py
      - backend/app/services/ws_manager.py
  - 로그:
      - redis set/publish 성공 여부
      - direct broadcast 호출 여부
      - WS listener가 message를 받았는지
      - active connection 수
  - 목적:
      - “백엔드는 진행됐는데 프론트가 못 본 것인지” 구분

  5. 최소 수정안 제안

  수정 전에 로그를 우선 깔아야 합니다. 그 전제에서 최소 수정안은 이 정도가 적절합니다.

  1. bot task done callback에 예외 로깅 추가

  - 현재는 _bot_tasks.discard만 합니다.
  - 여기에 task.exception()을 읽어 [BOT_TRACE] task_done 로그를 남기면 task 소멸 원인을 바로 알 수 있습니다.

  2. process_action_callback 전후 로그 추가

  - callback_enter
  - callback_exit
  - callback_error
  - 지금은 action 선택 로그는 있어도 callback lifecycle은 충분히 안 보입니다.

  3. _sync_to_redis() 성공/실패를 warning 레벨로 짧게 기록

  - DB는 진행되는데 프론트가 stale인 경우를 빨리 가를 수 있습니다.

  4. bot stall watchdog 추가

  - bot task 시작 시 timestamp 저장
  - 5초 안에 turn_action_applied가 없으면 [BOT_STALL] game=... actor=... phase=... 로그
  - 동작 변경 없이 관찰성만 높이는 최소 수정입니다.

  6. 검증 기준 제안

  성공 기준:

  - bot turn 진입 후 5초 이내에
      - turn_action_applied 로그가 찍히거나
      - game_logs row가 1개 이상 증가하거나
      - 프론트로 STATE_UPDATE가 전파된 로그가 찍혀야 합니다.

  실패 기준:

  - bot turn 진입 로그는 찍혔는데 5초 내
      - turn_action_selected 없음
      - 또는 callback_enter 없음
      - 또는 callback_exit 없음
      - 또는 _sync_to_redis end 없음
  - 2~3분 동안 active_player가 bot인 채로 아무 lifecycle 로그 변화가 없으면 명백한 stall입니다.

  추가로, 지금 기준에서 가장 먼저 해야 할 건 “delay 축소”가 아니라 아래 3개입니다.

  1. schedule -> task_done 전체 lifecycle 로그
  2. callback_enter/exit/error 로그
  3. _sync_to_redis와 WS broadcast 로그

  이 세 개만 있으면 다음 재현 때

  - 스케줄 안 됨
  - task 즉사
  - action 선택 실패
  - callback 실패
  - 상태 전파 실패
    중 어디서 멈췄는지 바로 분리할 수 있습니다.
