첨부한 개발자도구 로그(error.md)를 근거로, 현재 문제를 "backend bot stall"로 보지 말고 프론트 UI/상태관리 버그로 분리해서 분석하고 최소 수정안을 제안해라.

[확인된 사실]
1. 봇 추가 UI 이상
- 사용자는 PPO bot을 1개만 추가했는데 화면상 2개가 추가된 것처럼 보인다.
- 하나를 지우고 다시 추가하면 화면상 봇이 3개처럼 보인다.
- 하지만 실제 데이터 기준으로는 1개씩만 늘어난다.
- 로그에는 "Encountered two children with the same key, `Bot (ppo)`" 경고가 있다.
- add-bot 요청은 409 Conflict가 2번 보인다.

2. 봇 액션 없음처럼 보이는 문제
- 사용자는 "시작해도 봇의 액션이 없다"고 체감한다.
- 하지만 로그에는 frontend_ws_onopen, frontend_ws_auth_send, frontend_ws_onmessage_raw, frontend_state_update_received, frontend_set_state_applied 가 반복된다.
- active_player도 player_1, player_2, player_0 등으로 계속 바뀐다.
- 즉 프론트는 websocket 상태 업데이트를 실제로 받고 있고, 게임은 진행 중일 가능성이 높다.
- 그런데 frontend_ui_block_state 에서는 isBotTurn=true, isBlocked=true 가 계속 보인다.
- bot_thinking 은 false 인데도 사용자는 "멈췄다"고 느낀다.

3. 방 삭제 후 재접속 문제
- 사용자가 방을 삭제한 뒤 다시 접속하면 "삭제된 게임"이라고 뜬다.
- 이 이슈는 이번 로그엔 직접 증거가 부족하므로, 프론트 state/localStorage/router/gameId 초기화 경로를 코드 기준으로 확인해야 한다.

[반드시 확인할 파일]
- frontend/src/components/LobbyScreen.tsx
- frontend/src/App.tsx
- frontend/src/hooks/useGameWebSocket.ts
- add-bot / remove-bot / start / delete-room 관련 프론트 API 호출부
- localStorage, sessionStorage, router navigation, selected gameId/state 관리 코드

[내가 원하는 분석 목표]
1. 왜 bot이 실제보다 2배/3배로 보이는지 원인을 좁혀라
   - React key 중복 문제
   - 동일 항목을 이름 기반 key로 렌더링하는 문제
   - optimistic UI 갱신 + 서버 응답 재반영 중복 문제
   - 409 Conflict 이후 UI rollback 누락 가능성
2. 왜 사용자는 "봇 액션이 없다"고 느끼는지 설명해라
   - 실제로는 WS state update가 오고 active_player가 바뀌는데
   - 어떤 UI 조건 때문에 계속 멈춘 것처럼 보이는지
   - isBlocked / isBotTurn / bot_thinking / dedupe / skipped update 경로를 중심으로 분석
3. 삭제된 게임 재접속 문제의 유력 원인을 코드 기준으로 찾아라
   - stale gameId
   - localStorage/sessionStorage 잔존
   - delete 후 state reset 미흡
   - route 전환 미흡
4. 각 문제별 최소 수정안만 제안해라

[출력 형식]
1. 문제 1: bot 중복 표시 원인 / 관련 파일 / 최소 수정안
2. 문제 2: bot 무반응처럼 보이는 UI 원인 / 관련 파일 / 최소 수정안
3. 문제 3: 삭제 후 재접속 문제 원인 후보 / 관련 파일 / 최소 수정안
4. 수정 diff
5. 수정 후 내가 확인할 체크리스트

[중요]
- 이번 로그 기준으로 websocket 연결은 실제로 열리고, STATE_UPDATE도 수신되고 있으므로 backend stall을 주원인으로 보지 마라.
- "봇이 안 움직인다"는 사용자 체감과 "프론트 state는 실제로 계속 변한다"는 로그를 함께 설명해야 한다.
- 특히 LobbyScreen.tsx의 duplicate key 경고와 App.tsx의 blocked UI 상태를 핵심 단서로 사용해라.