# Engine Cutover Final Verification

작성일: 2026-04-08  
연결 backlog: `design/2026-04-08_engine_cutover_task_breakdown.md`  
대상 task: `P7-T1`, `P7-T2`, `P7-T3`

## 1. 목적

engine-first, strategy-first Mayor cutover가 실제 현재 코드 기준으로 green인지 확인한다.

이 문서는 다음 세 가지를 닫는다.

- backend 전체 테스트
- frontend 전체 테스트 및 build
- 실제 service path 기반 human/bot Mayor smoke + replay parity 확인

관련 승격 기준은 `design/2026-04-08_engine_cutover_promotion_gate.md`를 따른다.

## 2. Backend Full Test

실행 명령:

```bash
docker compose exec backend pytest -q
```

결과:

- `327 passed, 2 skipped, 9 warnings in 12.44s`

관찰:

- red는 없고 전체 suite green이다.
- warning은 기존 FastAPI `on_event` deprecation과 websocket disconnect test의 async mock warning이다.
- Mayor strategy contract, replay parity, scenario regression, import guard가 모두 full suite 안에서 함께 통과한다.

## 3. Frontend Full Test / Build

실행 명령:

```bash
docker compose exec frontend npm test
docker compose exec frontend npm run build
```

결과:

- vitest: `11 passed`, `28 passed`
- production build: Vite build 성공

build 산출 요약:

- `dist/assets/index-C-4YnQnI.css` `18.33 kB`
- `dist/assets/index-C-1OZj_3.js` `380.52 kB`

관찰:

- `App.auth-flow`, `App.mayor-flow`, `MayorStrategyPanel`을 포함한 핵심 strategy-first UI 흐름이 green이다.
- frontend는 더 이상 sequential Mayor UI를 요구하지 않는다.

## 4. Replay / Manual Smoke

실행 방식:

- 실제 backend service path에서 room/user/session을 만들고 `GameService.start_game`, `GameService.process_action`, `BotService.run_bot_turn`을 사용해 smoke를 수행했다.
- Mayor phase를 canonical engine state로 세팅한 뒤 human 1회, bot 1회를 각각 실행했다.

### Human Mayor Smoke

replay:

- `data/logs/replay/0af7acfe-1e61-4eaf-a568-265766f5a79b.json`

확인 결과:

- `parity.mismatched_players == []`
- 마지막 Mayor action: `Mayor: Strategy Captain Focus`
- `state_summary_after.current_player == 1`

해석:

- human Mayor가 strategy band action으로 정상 처리되었고, replay parity mismatch가 없다.

### Bot Mayor Smoke

replay:

- `data/logs/replay/3680e916-7c29-4ed3-becc-c61203e03136.json`

확인 결과:

- `parity.mismatched_players == []`
- 마지막 Mayor action: `Mayor: Strategy Building Focus`
- `state_summary_after.current_player == 1`

해석:

- bot Mayor도 strategy-first contract로 정상 처리되었고, replay parity mismatch가 없다.

## 5. 판정

다음 backlog task를 완료로 닫는다.

- `P7-T1`
- `P7-T2`
- `P7-T3`

현재 컷오버 기준에서 확인된 결론:

- backend canonical engine 경로는 green이다.
- frontend strategy-first Mayor UI는 green이다.
- human/bot 실제 flow replay가 strategy-first action 설명과 parity를 함께 남긴다.
- `design/2026-04-08_engine_cutover_promotion_gate.md`의 compatibility/scenario/replay gate를 적용할 수 있는 상태다.

## 6. 잔여 메모

- full suite에는 기존 warning 9건이 남아 있다.
- 이번 검증은 sqlite 신규 생성 목적이 아니라, 이미 구성된 docker 서비스 경로 기준 검증이다.
- task breakdown 기준 남은 `TODO`는 없다.
