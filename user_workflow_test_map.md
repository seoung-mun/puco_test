# 사용자 워크플로 기반 테스트 맵

이 문서는 현재 코드베이스의 테스트 파일을 디렉터리 기준이 아니라 실제 사용자 흐름 기준으로 다시 배열한 브레인스토밍 문서입니다.

- 범위: `frontend` 테스트 20개, `backend` 테스트 44개
- 배치 원칙: 한 테스트 파일은 가장 대표적인 사용자 순간에만 1회 배치
- 용도: "지금 로그인 흐름을 건드렸는데 어디까지 같이 봐야 하지?" 같은 질문에 빠르게 답하기

## 요약

| 단계 | 사용자 순간 | Frontend | Backend |
| --- | --- | ---: | ---: |
| 1 | 접속 준비, 로그인, 기본 진단 | 3 | 3 |
| 2 | 방 찾기, 방 만들기, 로비 정리 | 2 | 5 |
| 3 | 게임 시작 직전/직후 세션 부트스트랩 | 1 | 6 |
| 4 | 실시간 상태 전달과 차례 루프 | 3 | 8 |
| 5 | 역할별 액션과 보드 상호작용 | 4 | 5 |
| 6 | 봇 동반 플레이와 모델 안전성 | 0 | 6 |
| 7 | 게임 종료, 결과 확인, 리플레이 | 7 | 6 |
| 8 | 저장, 감사 로그, 인프라 회귀 | 0 | 5 |

## 1. 접속 준비, 로그인, 기본 진단

이 단계는 사용자가 앱을 열고 "들어갈 수 있는가"를 먼저 확인하는 구간입니다.

### Frontend

- `frontend/src/__tests__/googleOAuth.test.ts`: Google OAuth 설정 누락/존재 시 사용자에게 어떤 안내를 보여줘야 하는지 보호
- `frontend/src/components/__tests__/LoginScreen.test.tsx`: 로그인 화면에서 Google 위젯 렌더링과 오류 콜백 전달 계약 보호
- `frontend/src/__tests__/App.auth-flow.test.tsx`: 저장된 토큰이 유효하면 바로 방 목록으로, 무효하면 로그인으로 되돌리는 앱 부트스트랩 보호

### Backend

- `backend/tests/test_auth.py`: 토큰 생성, `/auth/me`, 인증 없는 액션/방 조회 차단 등 기본 인증 경계 보호
- `backend/tests/test_health_endpoint.py`: PostgreSQL/Redis 상태에 따라 `/health`가 `ok` 또는 `degraded`를 정확히 내놓는지 보호
- `backend/tests/test_env_secrets.py`: 런타임 비밀값 생성, placeholder 금지, 프론트/백엔드 키 동기화 보호

## 2. 방 찾기, 방 만들기, 로비 정리

이 단계는 사용자가 멀티플레이 또는 봇전으로 들어가기 전에 방을 찾고, 만들고, 정리하는 흐름입니다.

### Frontend

- `frontend/src/components/__tests__/RoomListScreen.test.tsx`: 봇전 생성 시 선택한 bot type 조합이 정확히 전송되는지 보호
- `frontend/src/components/__tests__/LobbyScreen.test.tsx`: 로비 헤더에서 로그아웃 같은 기본 탈출 경로가 유지되는지 보호

### Backend

- `backend/tests/test_room_title_uniqueness.py`: 대기방 제목 중복 금지와 대소문자 무시 규칙 보호
- `backend/tests/test_channel_bot_endpoint.py`: 대기방에서 bot 추가/삭제 권한, 슬롯, 수용 인원, bot type 검증 보호
- `backend/tests/test_lobby_ws.py`: 방 나가기, 방장 제한, bot-game 생성, 로비 WebSocket 인증/정리 흐름 보호
- `backend/tests/test_lobby_manager.py`: 로비 broadcast, 방 삭제, host 이전 같은 로비 연결 관리자 동작 보호
- `backend/tests/test_startup_cleanup.py`: 서버 기동 시 비정상적인 waiting room을 정리하거나 host를 넘기는 정리 루틴 보호

## 3. 게임 시작 직전/직후 세션 부트스트랩

이 단계는 로비에서 게임을 눌렀을 때 초기 상태가 어떻게 잡히고, 누가 연결 가능한지가 정해지는 구간입니다.

### Frontend

- `frontend/src/__tests__/App.mayor-flow.test.tsx`: 로비 시작 직후 Mayor 턴으로 진입하면 앱이 slot-direct panel을 노출하는 전환 보호

### Backend

- `backend/tests/test_multiplayer.py`: 로비 시작 응답 shape, bot type 보존, 초기 bot 실행 이후 상태 보호
- `backend/tests/test_governor_assignment.py`: governor 배정, 시드 기반 재현성, 초기 세팅 일관성 보호
- `backend/tests/test_game_service_control_modes.py`: 게임 시작 시 bot control mode가 서비스 계층으로 정확히 전달되는지 보호
- `backend/tests/test_model_version_snapshot.py`: room snapshot과 rich state에 bot model/version 메타데이터가 포함되는지 보호
- `backend/tests/test_game_ws_auth_contract.py`: 시작된 게임에서 참가자만 WebSocket 연결 가능하고, bot-only 게임은 host spectator가 허용되는지 보호
- `backend/tests/test_legacy_features.py`: legacy 경로의 display order, display number, `/bot-types`, `/bot/set` fallback 계약 보호

## 4. 실시간 상태 전달과 차례 루프

이 단계는 게임이 이미 시작된 뒤 브라우저와 서버가 상태를 주고받고, 턴을 소유한 플레이어가 액션을 보내는 메인 루프입니다.

### Frontend

- `frontend/src/hooks/__tests__/useGameWebSocket.test.ts`: auth-first handshake, dedupe, reconnect, cleanup 등 게임 WebSocket 수명주기 보호
- `frontend/src/__tests__/turnFocus.test.ts`: 내 턴이 되었을 때 어떤 패널을 자동 포커싱해야 하는지 보호
- `frontend/src/components/__tests__/GameScreen.test.tsx`: active role 표기, pass 버튼 활성/비활성, replay mode 차이 보호

### Backend

- `backend/tests/test_ws_disconnect.py`: 연결/해제 시 player 상태, disconnect timeout, auto-end, 종료 broadcast 보호
- `backend/tests/test_priority2_ws_delivery_contract.py`: Redis publish 성공/실패에 따라 direct broadcast fallback 여부 보호
- `backend/tests/test_event_bus.py`: in-memory pub/sub 이벤트 전달 형상과 unsubscribe 정리 보호
- `backend/tests/test_sse_stream.py`: legacy SSE 경로가 lobby start/join 이벤트를 publish하는지 보호
- `backend/tests/test_game_action.py`: 액션 요청이 DB 로그를 남기고 정확한 `action_index`를 서비스로 전달하는지 보호
- `backend/tests/test_game_service_turn_validation.py`: bot 턴에 잘못된 actor가 액션하는 것을 막는 서버 검증 보호
- `backend/tests/test_state_serializer_action_index.py`: 프론트가 소비하는 role/plantation/building/action index 직렬화 계약 보호
- `backend/tests/test_phase_action_edge_cases.py`: phase별 허용 액션, 마스크 위반, wrong-turn, 재사용 액션 등 전체 턴 검증 보호

## 5. 역할별 액션과 보드 상호작용

이 단계는 사용자가 실제 보드와 역할 패널을 만지는 순간입니다. 특히 Settler, Builder, Mayor 같은 세부 상호작용이 여기에 모입니다.

### Frontend

- `frontend/src/components/__tests__/MayorSequentialPanel.test.tsx`: legal slot 렌더링, slot 클릭 시 action index 매핑, illegal slot disable 보호
- `frontend/src/components/__tests__/AvailablePlantations.test.tsx`: Hacienda 추가 드로우가 진행 중일 때 plantation 클릭이 중복되지 않도록 보호
- `frontend/src/components/__tests__/CommonBoardPanel.test.tsx`: Hacienda 후속 안내 문구 같은 공용 보드 패널 문맥 보호
- `frontend/src/components/__tests__/SanJuan.test.tsx`: Guild Hall 표기, 재고 남음/소진에 따른 시각 상태 보호

### Backend

- `backend/tests/test_mayor_slot_contract.py`: human/bot Mayor 모두 slot-direct 계약을 따르고, legacy distribute endpoint가 막혀 있는지 보호
- `backend/tests/test_mayor_serializer_contract.py`: Mayor serializer가 island/city slot id와 capacity 메타데이터를 내보내는지 보호
- `backend/tests/test_mayor_large_building_masking.py`: 대형 건물 포함 city slot 마스킹이 올바른 legal slot 집합으로 변환되는지 보호
- `backend/tests/test_hacienda_turn_flow.py`: Hacienda 추가 드로우 뒤에도 같은 플레이어가 Settler 결정을 이어가야 하는 턴 연속성 보호
- `backend/tests/test_scenario_regression_harness.py`: trader 과선택, bonus role 우선순위, Mayor strategy band 같은 알려진 회귀 시나리오 보호

## 6. 봇 동반 플레이와 모델 안전성

이 단계는 "사용자가 사람 상대만이 아니라 bot과도 플레이한다"는 제품 특성을 지키는 안전망입니다.

### Backend

- `backend/tests/test_priority2_bot_routing_contract.py`: 요청된 bot type에 따라 random/PPO 라우팅이 정확히 갈리는지 보호
- `backend/tests/test_priority2_bot_input_snapshot.py`: bot 입력 snapshot이 serializer/engine state와 맞물리고 최신 agent type이 등록되는지 보호
- `backend/tests/test_bot_service_safety.py`: bot turn 콜백 실패, mask 추출 실패, last obs 누락 같은 예외 상황 복구 보호
- `backend/tests/test_bot_task_reference.py`: 비동기 bot task reference가 누락되지 않고 수명주기에서 추적되는지 보호
- `backend/tests/test_model_registry_bootstrap.py`: allowlist checkpoint, sidecar metadata, obs 차원 추론 같은 model registry 부트스트랩 보호
- `backend/tests/test_serving_ppo_wrapper.py`: 2.10 체크포인트를 2.11 런타임 관측치로 맞춰주는 serving wrapper 호환성 보호

## 7. 게임 종료, 결과 확인, 리플레이

이 단계는 사용자가 끝난 게임을 이해하고 다시 보는 흐름입니다.

### Frontend

- `frontend/src/components/__tests__/EndGamePanel.test.tsx`: terminal result summary, 로딩 fallback, 중복 display name 렌더링 보호
- `frontend/src/components/__tests__/ReplayConfirmModal.test.tsx`: 리플레이 진입 확인 모달 open/confirm/cancel/ESC/backdrop 동작 보호
- `frontend/src/components/__tests__/ReplayListScreen.test.tsx`: 리플레이 목록 조회, 검색, watch 진입, empty state 보호
- `frontend/src/components/__tests__/ReplayViewScreen.test.tsx`: 리플레이 상세 fetch, frame 이동, 404/에러 처리 보호
- `frontend/src/components/__tests__/Pagination.test.tsx`: 페이지 계산, ellipsis, 현재 페이지 강조, page change 동작 보호
- `frontend/src/hooks/__tests__/useReplayList.test.ts`: replay list fetch, 검색 시 page reset, error state 보호
- `frontend/src/hooks/__tests__/useReplayPlayer.test.ts`: frame seek/playback/speed/toggle 같은 리플레이 플레이어 상태머신 보호

### Backend

- `backend/tests/test_final_score_access.py`: bot-game host spectator만 최종 점수에 접근 가능한지 보호
- `backend/tests/test_replay_api.py`: finished game만 목록에 나오고, 검색/정렬/페이지네이션/상세 리플레이 필터가 맞는지 보호
- `backend/tests/test_replay_logging_integration.py`: 실제 액션 요청 뒤 replay JSON 파일이 쓰이는 통합 흐름 보호
- `backend/tests/test_replay_logger.py`: 사람이 읽는 replay 문자열, final score payload, 중복 bot 이름 처리 보호
- `backend/tests/test_replay_logger_rich_state.py`: rich state 포함/억제 혼합 케이스가 replay entry에 올바르게 저장되는지 보호
- `backend/tests/test_terminal_result_summary.py`: terminal state에만 result summary가 들어가고 중복 이름도 stable ref로 구분되는지 보호

## 8. 저장, 감사 로그, 인프라 회귀

이 단계는 사용자가 직접 보지 않아도 제품 신뢰도를 좌우하는 운영/데이터 계약입니다.

### Backend

- `backend/tests/test_redis_service.py`: Redis TTL, publish 채널명, meta 저장, finished 상태 갱신 보호
- `backend/tests/test_db_schema.py`: SQLAlchemy 모델, JSONB 저장, 관계, 인덱스, 기본값 보호
- `backend/tests/test_ml_logger.py`: transition JSONL 동시성, action mask/model info 기록, 파일 경로 규칙 보호
- `backend/tests/test_gamelog_vp_doubloon.py`: state_summary, VP/doubloon 추적, before/after 체인, JSON 직렬화 가능성 보호
- `backend/tests/test_engine_gateway_import_guard.py`: backend가 `PuCo_RL` 모듈을 gateway/legacy 경계 밖에서 직접 import하지 않는 규칙 보호

## 지원 파일과 테스트 보조 자산

아래 파일들은 "테스트 파일"이라기보다 실행 설정이나 fixture 자산이므로 위 워크플로 표에서는 따로 뺐습니다.

- `frontend/vite.config.test.ts`: 프론트 테스트 전용 Vite/Vitest 설정
- `frontend/src/test/setup.ts`: jsdom 공용 setup과 전역 mock
- `backend/tests/conftest.py`: pytest fixture, DB/session/client 공용 bootstrap
- `backend/test_action_index.db`: serializer/action index 계열 테스트에서 쓰는 보조 DB 자산

## 추천 활용 방식

### 변경 영향도를 빠르게 좁히고 싶을 때

1. 내가 건드린 기능이 어느 사용자 순간에 속하는지 먼저 찾습니다.
2. 그 섹션의 Frontend와 Backend 테스트 파일을 함께 봅니다.
3. 경계가 애매하면 바로 다음 섹션까지 한 단계 더 포함합니다.

### 실행 템플릿

Frontend 섹션 실행 템플릿:

```bash
cd frontend
npm test -- <이 섹션의 frontend 테스트 파일들>
```

Backend 섹션 실행 템플릿:

```bash
cd backend
pytest <이 섹션의 backend 테스트 파일들>
```

전체를 한 번에 훑고 싶다면, 위 1번부터 8번 순서로 내려오면서 "사용자 진입점에서 운영 로그까지" 순차적으로 확인하는 편이 가장 이해가 빠릅니다.
