# TODO

이 문서는 우선순위, 파일 결합도, TDD 원칙을 기준으로 재정렬한 작업 목록이다.

정렬 원칙:
- 1순위: 게임 규칙 검토 및 규칙 강제 로직 감사
- 2순위: 봇전/봇 추론/WS/봇 타입 라우팅
- 3순위: 게임 로그 저장 구조
- 4순위: 게임 종료 UX 및 결과 화면
- 5순위: 나머지 구조 개선 및 장기 과제

작업 묶음 원칙:
- 같은 파일군을 주로 수정하게 되는 task는 최대한 한 섹션에 묶는다.
- 각 섹션은 설계 전에 테스트 기준부터 정한다.
- 구현 전 반드시 "현재 동작을 고정하는 테스트"와 "원하는 동작을 드러내는 테스트"를 분리한다.

---

## Priority 1. 규칙 검토 및 규칙 강제 로직 감사

### 1-A. Mayor 규칙 구조 및 슬롯 진행 순서 검증

관련 파일군:
- `PuCo_RL/env/engine.py`
- `PuCo_RL/env/pr_env.py`
- `PuCo_RL/env/player.py`
- `backend/app/services/state_serializer.py`
- `frontend/src/App.tsx`

핵심 질문:
- Mayor 배치가 실제로 `농지 -> 건물` 순서로만 강제되는가
- 이 순서가 구현 편의인지, 의도된 규칙인지, UI 타협인지 구분되는가
- 사람 UI와 봇 mask가 동일한 slot progression 모델을 공유하는가

세부 작업:
- Mayor 시작 시 `recall_all_colonists()` 호출 시점과 영향 범위를 추적
- Mayor 슬롯 인덱스가 `0-11 island`, `12-23 city`인 현재 모델의 근거를 정리
- 프론트의 `mayorPending` 전체 계획형 입력과 엔진의 순차 슬롯형 모델이 일치하는지 검증
- `mayor_slot_idx`, `mayor_can_skip`, `colonists_unplaced`의 의미가 phase 전반에 걸쳐 안정적인지 점검

TDD 원칙:
- 먼저 현재 Mayor 순서와 slot progression을 고정하는 characterization test를 만든다.
- 그 다음 원하는 규칙 변경이 있다면 failing test를 별도로 만든다.
- Mayor 관련 테스트는 engine 단위와 serializer/UI 계약 단위를 분리한다.

필수 테스트 초안:
- `test_mayor_slot_progression_is_island_then_city`
- `test_mayor_serializer_slot_idx_matches_engine_cursor`
- `test_mayor_frontend_assumption_matches_backend_contract`

완료 기준:
- Mayor의 현재 규칙을 엔진, 백엔드, 프론트 각각이 어떤 가정으로 해석하는지 문장으로 설명 가능
- 규칙 버그인지, 표현 계약 문제인지, 설계 변경 요구인지 분류 완료

### 1-B. Mayor 강제 배치/skip 판정 감사

관련 파일군:
- `PuCo_RL/env/engine.py`
- `PuCo_RL/env/pr_env.py`
- `backend/app/services/state_serializer.py`
- `frontend/src/App.tsx`

핵심 질문:
- "반드시 배치해야 하는 상황"과 "skip 가능한 상황"이 엔진과 프론트에서 동일하게 계산되는가
- Mayor에서 프론트가 사용자를 잘못 막거나, 반대로 잘못 허용하는 지점이 있는가

세부 작업:
- `valid_action_mask()`의 Mayor 분기를 분석해 `min_place`, `max_place`, `future_capacity` 계산 과정을 문서화
- 프론트의 `mayorCannotConfirm`, `mayorMustPlace`, `mayorFinishPlacement` 조건과 엔진 mask를 비교
- Mayor에서 `action 15`가 금지되어야 하는 상태와 UI가 pass/finish 버튼을 보여주는 상태가 어긋나는지 점검

TDD 원칙:
- 엔진 mask 기준 truth table을 먼저 만든다.
- 프론트는 그 truth table을 그대로 소비하는지만 검증한다.
- 프론트 로직을 엔진 규칙의 복제본처럼 따로 확장하지 않도록 테스트 이름도 "contract" 중심으로 쓴다.

필수 테스트 초안:
- `test_mayor_skip_allowed_only_when_mask_69_open`
- `test_mayor_finish_button_disabled_when_engine_requires_more_placement`
- `test_mayor_meta_contract_matches_mask`

완료 기준:
- Mayor 강제 배치 관련 bug 가능 지점을 코드 레벨로 식별하고, 엔진/프론트 어느 쪽이 진실 소스인지 정리

### 1-C. Captain 강제 적재 규칙 검증

관련 파일군:
- `PuCo_RL/env/engine.py`
- `PuCo_RL/env/pr_env.py`
- `backend/app/services/game_service.py`
- `backend/app/services/bot_service.py`

핵심 질문:
- 선장 페이즈에서 적재 가능하면 반드시 적재해야 한다는 규칙이 실제로 강제되는가
- `action_captain_pass()`와 `valid_action_mask()`가 완전히 같은 조건을 사용하는가
- 실서비스 경로에서 봇이 action `15`를 받는 경우가 진짜 정상인가

세부 작업:
- `action_captain_pass()`의 can_load_anything 계산과 `valid_action_mask()`의 Captain 분기를 나란히 비교
- 다수 적재 가능한 액션 중 자유 선택은 허용하되 pass는 닫히는 상황을 표로 정리
- backend 로그에서 `phase_id`, `selected_action`, `valid=True`, `action=15`가 Captain에서 나온 적이 있는지 확인

TDD 원칙:
- 엔진 레벨에서 "can load이면 pass forbidden"을 고정하는 테스트를 먼저 확장한다.
- 서비스 레벨에서는 mask가 닫힌 pass가 bot 경로에서 절대 적용되지 않는지 테스트한다.

필수 테스트 초안:
- `test_captain_pass_forbidden_when_any_ship_load_exists`
- `test_captain_service_rejects_pass_when_engine_mask_closes_it`
- `test_bot_captain_never_applies_pass_when_load_exists`

완료 기준:
- Captain 규칙 강제가 엔진, 서비스, 봇 경로에서 일관되는지 결론 도출

### 1-D. Trader 규칙 및 pass 정책 검증

관련 파일군:
- `PuCo_RL/env/engine.py`
- `PuCo_RL/env/pr_env.py`
- `backend/app/services/bot_service.py`

핵심 질문:
- Trader에서 pass가 항상 허용되는 현재 정책은 의도된 설계인가
- 판매 가능한 상태에서 pass를 자주 선택하는 것이 "정상 random"인지 "라우팅/정책 버그"인지 분리할 수 있는가

세부 작업:
- Trader mask가 현재 어떤 조건에서 `39~43`과 `15`를 동시에 여는지 문서화
- Corn 판매처럼 가격이 낮아도 sell action이 열리는지 재확인
- 판매 가능 상태 대비 pass 빈도를 측정할 지표 설계

TDD 원칙:
- Trader는 binary bug가 아니라 distribution 문제일 수 있으므로 deterministic test와 statistical check를 구분한다.
- mask 존재 여부는 unit test로, 선택 편향은 replay/log 기반 분석 테스트로 본다.

필수 테스트 초안:
- `test_trader_pass_and_sell_can_coexist_by_design`
- `test_trader_sell_actions_open_for_owned_goods_only`
- `test_random_bot_trader_pass_rate_report`

완료 기준:
- Trader 무행동 현상을 규칙 문제, 랜덤 특성, wrapper 문제 중 무엇으로 봐야 하는지 분류 완료

### 1-E. 규칙 강제 로직 전수 감사

관련 파일군:
- `PuCo_RL/env/engine.py`
- `PuCo_RL/env/pr_env.py`
- `backend/app/services/game_service.py`
- `frontend/src/App.tsx`

핵심 질문:
- "할 수 있으면 반드시 해야 하는 액션"이 phase별로 어디에서 보장되는가
- 엔진, mask, backend validation, frontend disable 중 어느 층이 최종 책임을 가져야 하는가

세부 작업:
- Settler, Mayor, Builder, Trader, Captain, Captain Store의 강제 규칙 목록 작성
- 각 규칙을 `engine action`, `valid_action_mask`, `process_action`, `frontend` 중 어디가 담당하는지 매핑
- 중복 검증과 누락 검증을 분리 기록

TDD 원칙:
- 단일 진실 소스를 엔진으로 두고, 나머지는 contract test만 가져간다.
- 프론트/백엔드 테스트는 "엔진 truth를 어기지 않는다" 수준으로 제한한다.

완료 기준:
- 규칙 강제 로직의 단일 책임 위치와 누락/중복 지점 문서화

---

## Priority 2. 봇전 / 봇 추론 / WS / 봇 타입 라우팅

### 2-A. 봇전 생성 구조와 봇 타입 고정값 제거 설계

관련 파일군:
- `frontend/src/App.tsx`
- `frontend/src/components/LobbyScreen.tsx`
- `backend/app/api/channel/room.py`
- `backend/app/api/channel/game.py`
- `backend/app/services/game_service.py`

핵심 질문:
- 현재 봇전 생성 흐름에서 왜 `random` 3개가 고정되는가
- 동일 봇 3개 self-play를 허용하려면 어떤 입력 계약이 필요한가

세부 작업:
- `/api/puco/rooms/bot-game` 생성 경로와 payload 부재 구조 정리
- 대기실 `add-bot` 경로와 즉시 시작 봇전 경로를 비교
- 동일 타입 중복이 프론트/백엔드에서 막히는지 확인

TDD 원칙:
- 현재 고정 동작을 먼저 snapshot 테스트로 고정
- 이후 `bot_types: ["random","random","random"]` 같은 원하는 요청이 통과하는 failing test를 설계

완료 기준:
- 봇전 생성, 대기실 봇 추가, 게임 시작 간 bot_type 계약을 하나로 설명 가능

### 2-B. bot_type 라우팅 복구

관련 파일군:
- `backend/app/services/bot_service.py`
- `backend/app/services/agent_registry.py`
- `backend/app/services/game_service.py`
- `backend/app/api/legacy/deps.py`

핵심 질문:
- `BOT_random`이 실제로 Random wrapper를 쓰는가
- 채널 경로와 레거시 경로가 같은 bot_type 계약을 공유하는가

세부 작업:
- `BotService.get_action()`이 현재 bot_type 없이 동작하는 구조를 정리
- 레거시가 기대하는 `get_action(bot_type, game_context)` 계약과 채널 계약의 드리프트를 문서화
- actor label과 실제 wrapper 선택이 일치하도록 설계 초안 작성

TDD 원칙:
- wrapper 선택은 deterministic unit test로 고정한다.
- `BOT_random -> RandomWrapper`, `BOT_ppo -> PPOWrapper`를 먼저 failing test로 만든다.

필수 테스트 초안:
- `test_channel_bot_random_uses_random_wrapper`
- `test_channel_bot_ppo_uses_ppo_wrapper`
- `test_legacy_and_channel_share_same_bot_type_contract`

완료 기준:
- bot_type 라우팅 누락 여부를 확정하고, 단일 계약으로 통합하는 설계안 작성

### 2-C. Random 봇 역할 선택/상인/선장 편향 분석

관련 파일군:
- `backend/app/services/bot_service.py`
- `backend/app/services/game_service.py`
- `PuCo_RL/logs/replay/*`
- `PuCo_RL/agents/wrappers.py`

핵심 질문:
- Random 봇이 정말 uniform random에 가깝게 행동하는가
- Trader/Captain 이상 행동이 mask 문제인지, wrapper 문제인지, replay/WS 문제인지 구분 가능한가

세부 작업:
- Random 봇전에서 역할 선택 빈도, Trader pass 비율, Captain pass 발생 여부를 지표화
- `BOT_random`이 실제 RandomWrapper인지 먼저 검증
- 필요하면 `true_random`과 `active_random`을 분리해야 하는지 제품 관점에서 검토

TDD 원칙:
- deterministic test는 wrapper 선택과 mask validity에만 둔다.
- 행동 분포는 replay 분석 스크립트나 report test로 분리한다.

완료 기준:
- "랜덤인데 시장을 너무 많이 고른다"는 관찰을 재현 가능한 수치로 정리

### 2-D. 봇 입력 데이터 검증 로직 및 테스트 계획

관련 파일군:
- `backend/app/services/bot_service.py`
- `backend/app/engine_wrapper/wrapper.py`
- `backend/app/services/state_serializer.py`
- `backend/app/services/game_service.py`

핵심 질문:
- 봇에게 들어가는 관측과 UI에서 보이는 상태가 같은 게임 상태를 기준으로 하는가
- schema drift, phase drift, stale last_obs 문제가 있는가

세부 작업:
- `engine.last_obs`, `engine.get_action_mask()`, serializer 출력이 같은 step 기준인지 확인
- phase_id 추출과 bot trace 로그가 실제 엔진 phase와 일치하는지 비교
- 검증 로직이 있으면 테스트로 정리하고, 없으면 설계 문서 목차 작성

TDD 원칙:
- 현재 obs/mask/serializer 동기화를 characterization test로 먼저 고정
- phase drift가 재현되면 regression test로 남긴다

완료 기준:
- 봇 입력 데이터 검증 로직의 존재 유무를 명확히 결론내고 테스트 계획 수립

### 2-E. 봇전 WS 리스크 및 통신 오류 대응 분석

관련 파일군:
- `backend/app/services/game_service.py`
- `backend/app/services/ws_manager.py`
- `backend/app/api/channel/ws.py`
- `frontend/src/hooks/useGameWebSocket.ts`

핵심 질문:
- 봇전 시작, 턴 진행, 종료 시 WS 이벤트 흐름이 안정적인가
- backend에서 상태가 바뀌었는데 프론트가 못 보는 경로가 있는가

세부 작업:
- `STATE_UPDATE`, redis publish, direct broadcast, listener dispatch 순서를 문서화
- 봇 턴 lifecycle 로그와 WS 브로드캐스트 로그를 같은 타임라인으로 재구성
- reconnect, duplicate broadcast, stale state 가능성 점검

TDD 원칙:
- WS는 unit test보다 sequence test가 중요하므로 "이벤트 순서" 중심의 integration test를 설계한다.
- 상태 적용과 브로드캐스트를 같은 assertion 묶음으로 검증한다.

완료 기준:
- WS 회귀 위험 목록과 우선 검증 시나리오 작성

---

## Priority 3. 게임 로그 저장 구조

### 3-A. 현재 로그 저장 구조 조사

관련 파일군:
- `backend/app/services/game_service.py`
- `backend/app/services/ml_logger.py`
- `backend/app/db/models.py`
- `PuCo_RL/logs/replay/*`

핵심 질문:
- 현재 로그가 DB, JSONL, replay 파일 중 어디에 어떤 형태로 저장되는가
- `replay_seed42_1775006136.json`과 현 서비스 저장 포맷의 차이는 무엇인가

세부 작업:
- `GameLog` 저장 시점과 payload 구조 파악
- transition logging과 human-readable summary 저장 구조 비교
- replay 스타일 로그를 만들려면 어떤 데이터가 추가로 필요한지 정리

TDD 원칙:
- 먼저 "지금 실제로 저장되는 필드"를 fixture 기반으로 고정
- 그 다음 원하는 replay schema를 contract test로 정의

완료 기준:
- 로컬 저장 지점과 DB 저장 지점을 분리 설명 가능

### 3-B. 로그 저장 대상 설계

관련 파일군:
- `backend/app/services/game_service.py`
- `backend/app/db/models.py`
- `backend/alembic/*`

핵심 질문:
- 로컬 파일 저장과 PostgreSQL 저장 중 어느 계층이 원본이어야 하는가
- 운영 확인성과 replay 재생성을 동시에 만족하는 구조는 무엇인가

세부 작업:
- 저장 단위 결정: step log, round snapshot, final summary
- DB schema 초안 작성
- replay export와 직접 저장 중 어느 방식을 택할지 비교

TDD 원칙:
- schema migration 이전에 example payload와 expected query shape를 먼저 정의
- 저장 테스트는 "한 액션 후 한 row"와 "한 판 후 summary"를 분리해서 설계

완료 기준:
- 저장 위치, 스키마, 조회 방식, 보존 정책 초안 작성

### 3-C. PostgreSQL 확인 절차 문서화

관련 파일군:
- `backend/app/db/models.py`
- `backend/app/api/*`
- 운영 문서

세부 작업:
- DB 확인 쿼리 정리
- Adminer/psql/API에서 확인하는 절차 문서화
- 개발자/운영자 기준 검증 흐름 분리

완료 기준:
- 저장 여부를 사람이 직접 검증할 수 있는 체크리스트 완성

### 3-D. Redis 역할 정의

관련 파일군:
- `backend/app/core/redis.py`
- `backend/app/services/game_service.py`
- `backend/app/services/ws_manager.py`

세부 작업:
- 현재 Redis 사용처를 state cache, pub/sub, meta 저장으로 분류
- 향후 로그 저장과의 역할 충돌 여부 점검
- "현재 역할 / 가능한 역할 / 권장 역할" 정리

완료 기준:
- Redis의 책임 경계를 문서화

---

## Priority 4. 게임 종료 UX 및 결과 화면

### 4-A. 종료 후 파란 화면 현상 분석

관련 파일군:
- `frontend/src/App.tsx`
- `frontend/src/hooks/useGameWebSocket.ts`
- `backend/app/services/game_service.py`
- `backend/app/api/channel/game.py`

핵심 질문:
- 종료 직후 프론트가 상태를 못 받는가, 받아도 렌더를 못 하는가
- 종료 후 화면이 비는 직접 원인이 `final-score 403`, `state shape`, `screen transition` 중 무엇인가

세부 작업:
- `finished=True` 이후 `STATE_UPDATE` 전파 흐름 추적
- 종료 직후 프론트의 screen/state 변화 추적
- 봇전 관전자 모드에서 종료 후 API 호출 흐름 확인

TDD 원칙:
- 종료 상태 수신, 결과 화면 렌더, 네비게이션 노출을 하나의 integration scenario로 묶어 테스트한다.

완료 기준:
- 파란 화면 현상의 직접 원인과 재현 조건 설명 가능

### 4-B. 종료 후 final-score 403 원인 분석

관련 파일군:
- `backend/app/api/channel/game.py`
- `backend/app/services/game_service.py`
- 프론트 종료 화면 호출부

핵심 질문:
- 관전자/host spectator가 final-score를 볼 수 없는 현재 정책이 의도인가 버그인가
- 결과 화면을 만들려면 별도 권한 정책이 필요한가

세부 작업:
- `final-score` 권한 검사를 봇전 host와 비교
- 결과 조회를 spectator 허용으로 바꿀지, 종료 payload에 score를 싣는지 비교

TDD 원칙:
- 권한 정책은 role별 access test로 먼저 고정
- host spectator, room player, spectator를 분리해서 테스트

완료 기준:
- final-score 403의 정책적 의미와 수정 방향 정리

### 4-C. 종료 결과 요약 화면 설계

관련 파일군:
- `frontend/src/App.tsx`
- `frontend/src/types/gameState.ts`
- `backend/app/services/state_serializer.py`
- `backend/app/api/channel/game.py`

세부 작업:
- 각 플레이어 총점, 순위, tie-break, bot_type 표시 방식 정의
- 결과 데이터 소스를 `final-score API` 또는 종료 state payload 중 하나로 통일
- all-bot 관전 / 멀티플레이 / 싱글플레이 UX 차이 설계

TDD 원칙:
- 결과 payload contract를 먼저 스냅샷으로 고정
- UI는 "랭킹/총점/복귀 버튼 렌더" acceptance test로 검증

완료 기준:
- 결과 화면의 데이터 소스, 필수 필드, 상태 전이 설계 완료

### 4-D. 종료 후 네비게이션 복구 설계

관련 파일군:
- `frontend/src/App.tsx`
- `backend/app/api/channel/room.py`

세부 작업:
- 종료 후 "로비로 돌아가기" 버튼 이동 경로를 모드별로 정의
- 즉시 시작 봇전은 기존 로비가 없으므로 어디로 복귀시킬지 정책화
- 새로고침 후 초기 화면 복귀만 되는 현재 구조를 persistence 관점에서 검토

완료 기준:
- 종료 후 이동 경로와 화면 복원 정책 정리

### 4-E. 종료 이벤트/WS 계약 점검

관련 파일군:
- `backend/app/services/ws_manager.py`
- `backend/app/services/game_service.py`
- `frontend/src/hooks/useGameWebSocket.ts`

세부 작업:
- 종료 시 `STATE_UPDATE`만으로 충분한지, `GAME_ENDED` 별도 이벤트가 필요한지 결정
- 종료 직후 websocket disconnect가 UX에 미치는 영향 분석

완료 기준:
- 종료 이벤트 계약을 명확히 정리

---

## Priority 5. 나머지 구조 개선 및 장기 과제

### 5-A. 학습된 모델 추가 방식 분석

관련 파일군:
- `backend/app/services/agents/factory.py`
- `backend/app/services/agent_registry.py`
- `PuCo_RL/models/*`

세부 작업:
- `.pth` 모델 로드 절차 조사
- 정적 등록 vs 동적 스캔 방식 비교
- 운영자가 새 모델을 추가할 때 필요한 메타데이터 정의

TDD 원칙:
- 모델 등록 테스트와 로딩 실패 폴백 테스트를 분리

완료 기준:
- 새 모델 추가 절차를 운영 관점에서 설명 가능

### 5-B. 모델 레지스트리/호환성 점검

관련 파일군:
- `backend/app/services/agents/*`
- `backend/app/services/bot_service.py`
- `PuCo_RL/models/*`

세부 작업:
- 모델 식별자, 경로, 메타데이터 관리 방식 정의
- 입력은 유지되더라도 잠재함수 변경 시 호환성 리스크 정리

완료 기준:
- 모델 추가 시 필요한 체크리스트 작성

### 5-C. 일반 통신 오류/엣지케이스 대응 방식 분석

관련 파일군:
- `backend/app/services/game_service.py`
- `backend/app/services/ws_manager.py`
- `frontend/src/hooks/useGameWebSocket.ts`

세부 작업:
- WS 끊김, 지연, 중복 이벤트, 상태 불일치 대응 방식 정리
- 재시도, fallback, timeout 정책 문서화

완료 기준:
- 현재 대응 방식과 미비점 보고 가능

### 5-D. 재현 로그 기반 체크리스트 작성

관련 파일군:
- 운영 로그
- `backend/app/services/game_service.py`
- `backend/app/services/bot_service.py`
- `backend/app/services/ws_manager.py`

세부 작업:
- 현재 기록된 로그에서 확정 사실과 추정 사실 분리
- 이후 동일 이슈 재현 시 반드시 수집할 로그 포인트 목록 작성

완료 기준:
- 규칙, 봇, 종료 UX 관련 이슈를 다시 볼 때 해석 혼선이 없도록 체크리스트 완성

---

## 메모

### 추가

mayor 페이즈에서 일꾼 배치를 현재는 순차 구조로 배치 시기에는 모든 배치된 일꾼을 빼서 다시 배치하는 방향으로 가고 있는데  
건설막/소형상가/채석장 이런 건물들은 한번 배치되면 앤간해서는 안빼는 식으로 로직을 수정할까라고 얘기가 나오고 있어  
engine.py 파일 자체를  
이거에 관련되서 만약 수정된다면 backend/ 부분은 어떤식으로 교체되야하는지 설계보고서 작성

현재 Random 봇전을 돌리는데 상인/선장 페이즈에서 물건을 팦거나/ 선적을 하지 않고 있어 랜덤인데 행동을 아예 하지 않는건 이상하므로, 액션 마스킹이 되어있는지 의심스러워 이거 체크

### 일단 기록 - 이건 명시적으로 말하기 전까지는 언급 금지

- mayor 페이즈에서 일꾼 배치할 때 농지 -> 건물 구조로 되고 있음
- 선장 페이즈에서 실을 수 있는 물건이 다수라면 어떤 걸 선택할지는 자유지만, 실을 수 있다면 무조건 실어야하는데 그 로직이 강제가 아닌거 같음
- 세부적인 로직을 점검 필요 - 게임 규칙 관련되서 강제하는 로직 부분이 제대로 들어가지 않는 부분들이 있는거 같음
- 아무리 랜덤이라지만, 시장 페이즈가 너무 많이 선택되는데 이거 확률부분 좀 살펴봐야할듯

- 게임이 종료된 후, 그냥 파란 화면 뜨고 아무것도 없음 
- 새로 고침을 하면 다시 온라인 멀티플레이어 버튼이 있는 곳으로 이동
- 로그 
puco_backend   | [WS_TRACE] ws_broadcast_end game_id=1feb88b1-070f-4bf1-a8e6-69ed6581beee source=manager message_type=STATE_UPDATE connection_count=1
puco_backend   | [BOT_TRACE] phase_id game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random phase_id=6
puco_backend   | [BOT_TRACE] selected_action phase_id=6 action=15 valid=True
puco_backend   | [BOT_TRACE] turn_action_selected game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random action=15 phase=6
puco_backend   | [BOT_TRACE] callback_enter game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random action=15
puco_backend   | [STATE_TRACE] process_action_enter game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random action=15
puco_backend   | [BOT_TRACE] process_action_enter game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random action=15
puco_backend   | [BOT_TRACE] process_action_turn_check game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random expected_actor=BOT_random current_idx=2 governor_idx=1 agent_selection=player_2
puco_backend   | [BOT_TRACE] process_action_mask game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random action=15 valid=True mask_len=200
puco_backend   | [STATE_TRACE] sync_to_redis_start game=1feb88b1-070f-4bf1-a8e6-69ed6581beee finished=True ttl=300
puco_backend   | [STATE_TRACE] sync_to_redis_end game=1feb88b1-070f-4bf1-a8e6-69ed6581beee
puco_backend   | [STATE_TRACE] ws_broadcast_start game=1feb88b1-070f-4bf1-a8e6-69ed6581beee
puco_backend   | [STATE_TRACE] ws_broadcast_end game=1feb88b1-070f-4bf1-a8e6-69ed6581beee
puco_backend   | [STATE_TRACE] process_action_exit game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random action=15 terminated=True next_player_idx=2
puco_backend   | [BOT_TRACE] process_action_exit game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random action=15 terminated=True next_player_idx=2 governor_idx=2 agent_selection=player_2
puco_backend   | [BOT_TRACE] callback_exit game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random action=15
puco_backend   | [BOT_TRACE] turn_action_applied game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random action=15
puco_backend   | [WS_TRACE] ws_broadcast_start game_id=1feb88b1-070f-4bf1-a8e6-69ed6581beee source=direct message_type=STATE_UPDATE
puco_backend   | [WS_TRACE] ws_broadcast_start game_id=1feb88b1-070f-4bf1-a8e6-69ed6581beee source=manager message_type=STATE_UPDATE connection_count=1
puco_backend   | [WS_TRACE] ws_broadcast_end game_id=1feb88b1-070f-4bf1-a8e6-69ed6581beee source=manager message_type=STATE_UPDATE connection_count=1
puco_backend   | [WS_TRACE] ws_broadcast_end game_id=1feb88b1-070f-4bf1-a8e6-69ed6581beee source=direct message_type=STATE_UPDATE connection_count=1
puco_backend   | [BOT_TRACE] task_done game=1feb88b1-070f-4bf1-a8e6-69ed6581beee actor=BOT_random task_id=281472755988992 cancelled=False exception=None active_bot_tasks=0
puco_backend   | [WS_TRACE] redis_listener_message_received game_id=1feb88b1-070f-4bf1-a8e6-69ed6581beee
puco_backend   | [WS_TRACE] redis_listener_broadcast_dispatch game_id=1feb88b1-070f-4bf1-a8e6-69ed6581beee
puco_backend   | [WS_TRACE] ws_broadcast_start game_id=1feb88b1-070f-4bf1-a8e6-69ed6581beee source=manager message_type=STATE_UPDATE connection_count=1
puco_backend   | [WS_TRACE] ws_broadcast_end game_id=1feb88b1-070f-4bf1-a8e6-69ed6581beee source=manager message_type=STATE_UPDATE connection_count=1
puco_backend   | INFO:     172.18.0.6:43764 - "GET /api/puco/game/1feb88b1-070f-4bf1-a8e6-69ed6581beee/final-score HTTP/1.1" 403 Forbidden
puco_backend   | [WS_TRACE] ws_disconnect game=1feb88b1-070f-4bf1-a8e6-69ed6581beee connection_id=preauth-281472754720816 user_id=94881c94-e014-45bc-b0a3-132e8be2cf79
puco_backend   | [WS_TRACE] ws_disconnect game=1feb88b1-070f-4bf1-a8e6-69ed6581beee connection_id=ws-1 user_id=94881c94-e014-45bc-b0a3-132e8be2cf79
puco_backend   | INFO:     connection closed

- 원하는 점
  - 게임이 끝난후, 전판 게임의 결과를 요약(각 플레이어의 총점, 1,2,3등 등)
  - 로비로 돌아갈 수 있게 버튼 생성 및 실제로 연결하여 로비로 돌아갈 수 있게
