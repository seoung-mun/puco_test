# Priority 2 TDD Execution Plan

작성일: 2026-04-05

기준 문서:
- `error_report/2026-04-04_priority2_design_report.md`

구현 순서:
1. `2-B. bot_type 라우팅 복구`
2. `2-A. 봇전 생성 구조와 봇 타입 고정값 제거`
3. `2-D. 봇 입력 데이터 검증 로직`
4. `2-C. Random 봇 deterministic 보장 + 분석용 trace`
5. `2-E. 봇전 WS 리스크 완화`

## 목표

이번 작업은 기능 추가보다 `계약 통합`을 우선한다.

- `channel`과 `legacy`가 같은 `bot_type + game_context` 계약을 사용해야 한다.
- `BOT_random`, `BOT_ppo` 같은 actor label이 실제 wrapper 선택으로 이어져야 한다.
- 봇이 보는 `obs / action_mask / phase / current_player / step_count`가 serializer와 같은 step를 가리켜야 한다.
- WebSocket 상태 전파는 가능한 한 단일 경로를 사용하고, 중복 수신을 프론트 dedupe에만 의존하지 않는다.
- MLOps 관점에서 모델 입력과 추론 결과 전달 경로를 로그/테스트로 설명 가능해야 한다.

## TDD 규칙

- 구현 전 red 테스트를 먼저 추가한다.
- 각 task는 `red -> green -> refactor` 순서로 진행한다.
- 새 기능을 넣기 전에 현재 계약 drift를 재현하는 테스트를 먼저 고정한다.
- 통계적 관찰과 deterministic correctness를 분리한다.

## Task 2-B

핵심 변경:
- `BotService`가 전역 singleton wrapper 대신 `AgentRegistry` 기반 per-bot wrapper resolver를 사용한다.
- `legacy`와 `channel` 모두 `BotService.get_action(bot_type, game_context)`를 사용한다.
- actor label 파싱 로직을 공용 helper로 정리한다.

red 테스트:
- `BOT_random`이 `RandomWrapper`로 연결되는지
- `BOT_ppo`가 `PPOWrapper`로 연결되는지
- `legacy` 계약인 `get_action(bot_type, game_context)`가 channel과 동일하게 동작하는지

acceptance:
- room/session에 저장된 bot_type과 실제 inference wrapper가 일치한다.

## Task 2-A

핵심 변경:
- `/api/puco/rooms/bot-game`가 `bot_types` 요청 body를 받는다.
- 기본값은 `["random", "random", "random"]`이다.
- `add-bot`와 `bot-game`이 같은 bot_type validator를 사용한다.

red 테스트:
- 명시한 `bot_types`로 봇전이 생성되는지
- 알 수 없는 `bot_type`이 400으로 거절되는지
- body가 없을 때 기본 3 random이 적용되는지

acceptance:
- mixed bot / all-ppo / all-random 생성이 같은 계약으로 설명 가능하다.

## Task 2-D

핵심 변경:
- `BotInputSnapshot`을 도입해 `obs`, `action_mask`, `phase_id`, `current_player_idx`, `step_count`, `bot_type`를 한 번에 만든다.
- serializer와 snapshot 사이의 contract를 검증하는 helper/test를 추가한다.

red 테스트:
- `engine.last_obs` phase와 serializer phase가 같은 step를 가리키는지
- snapshot action_mask와 serializer action_mask가 일치하는지
- snapshot current_player와 serializer active_player가 일치하는지

acceptance:
- UI와 모델이 서로 다른 step를 보고 있지 않다는 근거가 테스트로 남는다.

## Task 2-C

핵심 변경:
- Random bot이 유효 mask 안에서만 행동한다는 deterministic test를 강화한다.
- 분석용 trace에 `bot_type`, `phase_id`, `valid_actions`, `selected_action`, `step_count`를 남긴다.

red 테스트:
- random wrapper가 항상 valid action만 고르는지
- bot trace 입력 구조가 누락 없이 생성되는지

acceptance:
- "random인데 왜 이상하게 행동하지?"를 라우팅 문제와 분포 문제로 분리 진단할 수 있다.

## Task 2-E

핵심 변경:
- 상태 전파는 기본적으로 Redis publish 경로를 사용한다.
- direct broadcast는 Redis 실패 시 fallback으로만 사용한다.
- 중복 STATE_UPDATE를 backend에서 줄이고, frontend dedupe는 최후 방어선으로 남긴다.

red 테스트:
- Redis publish 성공 시 direct broadcast를 중복 호출하지 않는지
- Redis publish 실패 시 direct broadcast fallback이 동작하는지

acceptance:
- 동일 상태가 direct + redis 두 경로로 중복 전파되지 않는다.

## 데이터 흐름 검증 포인트

`UI -> backend`
- action_index가 현재 action_mask 안에 있는지 검증
- actor_id가 현재 active player와 일치하는지 검증

`backend -> engine`
- engine step 이전 mask와 actor를 로그/DB에 남김
- invalid action은 engine 진입 전에 차단

`engine -> model`
- bot snapshot에 obs/action_mask/phase/current_player/step_count를 고정
- bot_type이 wrapper 선택과 1:1로 대응

`model -> backend`
- selected_action이 해당 snapshot mask에서 valid인지 기록
- invalid output이면 fallback/retry와 함께 trace 남김

`backend -> UI`
- serializer state의 `meta.active_player`, `meta.phase`, `action_mask`가 snapshot/engine과 일치
- WS는 단일 전파 경로 우선

## Docker 검증 계획

- `backend` 테스트: Priority 2 관련 pytest subset 실행
- `frontend` 테스트: websocket hook 및 bot-game 관련 영향 범위 확인
- `docker compose up` 후 `/health` 확인
- bot-game 생성 및 action 흐름으로 `STATE_UPDATE`가 정상 전파되는지 확인
- game log / transition log로 actor, action_mask, phase, step 연속성 확인

## 완료 기준

- Priority 2 관련 핵심 경로가 테스트와 도커 검증에서 재현 가능하다.
- 게임 진행이 막히지 않고, 봇전 생성/시작/진행/종료 흐름이 유지된다.
- 모델 입력과 출력 전달 경로를 코드와 로그 기준으로 설명할 수 있다.
