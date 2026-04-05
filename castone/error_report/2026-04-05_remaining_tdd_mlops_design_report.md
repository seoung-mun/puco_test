# 2026-04-05 Remaining TODO + Audit Codebase Re-Audit Report

작성일: 2026-04-05

기준:
- `audit.md`
- `TODO.md`
- 현재 워크트리의 실제 코드
- 현재 추가/수정된 테스트

이번 문서는 이전처럼 문서끼리만 비교하지 않고, 실제 코드베이스와 테스트를 다시 훑은 뒤 작성한 재감사 결과다.

확인한 범위:
- `backend/app/*`
- `frontend/src/*`
- `PuCo_RL/env/*`
- `backend/tests/*`
- 현재 변경된 git diff

## 0. 결론 요약

이전 판단보다 실제 구현은 더 많이 진행되어 있다.

특히 아래는 이미 "설계"가 아니라 "코드 + 테스트" 수준으로 들어와 있다.

1. 사람 Mayor 입력은 이미 `plan -> backend orchestrator -> sequential action` 구조로 구현되어 있다.
2. 봇전 생성 시 `bot_types`를 받는 mixed-bot contract가 frontend/backend 양쪽에 실제 반영되어 있다.
3. `BotService.get_action(bot_type, game_context)` 계약은 실제 복구되어 channel/legacy drift가 크게 줄었다.
4. governor 랜덤화와 `game_seed` 기반 재현 테스트가 실제로 추가되어 있다.
5. 모델 provenance는 `model_registry.py`, `room.model_versions`, `MLLogger.model_info`까지 실제 연결되었다.
6. DB `GameLog` + JSONL transition + `state_summary` 조합은 이미 존재하고, 일부 provenance 필드도 들어간다.

반대로 아래는 여전히 미완성 또는 부분 구현 상태다.

1. 종료 UX는 아직 완결되지 않았다.
2. `step_id`, `state_hash`, `state_revision` 같은 통합 lineage key가 없다.
3. runtime 로그에 `game_seed`가 남지 않아 audit의 재현성 항목은 아직 테스트 수준에 머문다.
4. 모델 확률 분포/logits가 없어서 행동 heatmap audit은 정확히 재현할 수 없다.
5. inference latency / terminal delivery latency 같은 online monitoring 지표는 아직 없다.

## 1. 실제로 구현된 것

## 1-1. Mayor 사람 입력 계약

이 부분은 이미 코드로 구현되어 있다.

확인한 증거:

- `frontend/src/App.tsx`
  - `buildMayorPlacements(...)`
  - `confirmMayorDistribution()`
  - `/api/puco/game/{gameId}/mayor-distribute` 호출
- `backend/app/api/channel/game.py`
  - `POST /{game_id}/mayor-distribute`
- `backend/app/services/mayor_orchestrator.py`
  - `build_slot_catalog()`
  - `validate_distribution_plan()`
  - `translate_plan_to_actions()`
  - `apply_distribution_plan()`
- `backend/app/services/state_serializer.py`
  - island / city `slot_id`
  - `capacity`
  - `mayor_slot_idx`
  - `mayor_can_skip`

테스트 증거:

- `backend/tests/test_mayor_orchestrator.py`
- `backend/tests/test_channel_mayor_distribute.py`
- `backend/tests/test_mayor_serializer_contract.py`
- `backend/tests/test_todo_priority1_task1_mayor_contract.py`

판정:

- TODO의 `1-A`는 일부가 이미 characterization test 단계까지 구현됨
- TODO의 `1-B`는 meta/mask 노출은 구현됐지만 "engine truth table을 완전히 먼저 고정했다"고 보기는 아직 어렵다

남은 리스크:

- `translate_plan_to_actions()`는 slot catalog를 순회하며 `69 + amount`를 만든다
- 하지만 현재는 사전 검증이 `capacity` / `total_assigned` 중심이라, engine mask의 "지금 이 slot에서 skip 가능 여부"까지 미리 판정하지 않는다
- 즉 backend orchestrator는 존재하지만, Mayor forced-placement truth source를 완전히 문서화/고정했다고 보기는 어렵다

## 1-2. 봇전 생성과 mixed bot 선택

이 부분도 실제 구현이 들어가 있다.

확인한 증거:

- `backend/app/schemas/game.py`
  - `BotGameCreateRequest.bot_types`
- `backend/app/api/channel/room.py`
  - `POST /api/puco/rooms/bot-game`
  - `normalize_bot_types(...)`
  - `players=[make_bot_player_id(bot_type) ...]`
- `frontend/src/App.tsx`
  - `handleCreateBotGame(botTypes: string[])`
- `frontend/src/components/RoomListScreen.tsx`
  - bot-game modal
  - `/api/bot-types` fetch
  - 슬롯별 bot type select

테스트 증거:

- `backend/tests/test_lobby_ws.py`
  - explicit `bot_types`
  - unknown type reject
  - empty body default
- `frontend/src/components/__tests__/RoomListScreen.test.tsx`

판정:

- TODO의 `2-A`는 실제 구현 완료에 가깝다
- 더 이상 "random x 3 고정" 상태만은 아니다

## 1-3. bot_type 라우팅과 wrapper 선택

이 부분도 문서만이 아니라 실제 코드가 바뀌어 있다.

확인한 증거:

- `backend/app/services/bot_service.py`
  - `get_action(bot_type, game_context)`
  - `build_input_snapshot(...)`
  - `get_agent_wrapper(...)`
- `backend/app/services/agent_registry.py`
  - `get_wrapper(bot_type, obs_dim)`
  - `resolve_model_artifact(bot_type)`
  - `clear_wrapper_cache()`

핵심 변화:

- 이전처럼 singleton 하나를 전역 `MODEL_TYPE`로만 쓰는 구조가 아니라
- `bot_type -> artifact -> wrapper` 흐름으로 해석된다

테스트 증거:

- `backend/tests/test_priority2_bot_routing_contract.py`
- `backend/tests/test_priority2_bot_input_snapshot.py`

판정:

- TODO의 `2-B`와 `2-D`는 상당 부분 실제 구현으로 들어왔다
- legacy/channel drift는 적어도 `BotService.get_action(bot_type, game_context)` 시그니처 수준에서는 복구되었다

남은 리스크:

- `build_input_snapshot()`와 serializer 간 step alignment는 일부 테스트가 있지만, DB/JSONL까지 묶는 전 계층 reconciliation test는 아직 없다

## 1-4. governor 랜덤화와 seed 재현성

이 부분도 실제로 바뀌었다.

확인한 증거:

- `backend/app/engine_wrapper/wrapper.py`
  - `game_seed`
  - `governor_idx`
  - `_reset_environment(...)`
- 기존의 "무조건 governor_idx == 0" 루프 제거

테스트 증거:

- `backend/tests/test_governor_assignment.py`
  - same seed -> same governor/setup
  - random governor varies across seeds
  - explicit governor override

판정:

- TODO의 재현성 축 일부는 구현됐다
- 다만 이건 runtime observability가 아니라 engine initialization contract 수준이다

## 1-5. 모델 레지스트리 / provenance snapshot

이 부분은 설계 수준을 넘어 실제 코드와 테스트가 있다.

확인한 증거:

- `backend/app/services/model_registry.py`
  - `ModelArtifact`
  - `resolve_model_artifact_from_path(...)`
  - bootstrap metadata derivation
- `backend/app/services/agent_registry.py`
  - `resolve_model_artifact(...)`
- `backend/app/services/agents/factory.py`
  - `ppo_residual`
  - `num_res_blocks`
- `backend/app/services/game_service.py`
  - `_build_model_versions_snapshot(...)`
  - `_resolve_actor_model_info(...)`
  - `state["model_versions"]`
- `backend/app/services/ml_logger.py`
  - `model_info`

테스트 증거:

- `backend/tests/test_model_registry_bootstrap.py`
- `backend/tests/test_model_version_snapshot.py`
- `backend/tests/test_ml_logger.py`

판정:

- TODO의 `5-A`, `5-B`와 Priority 3 일부는 실제 구현이 이미 들어와 있다
- 특히 "어떤 봇이 어떤 checkpoint로 서빙되었는가"를 runtime state/JSONL에 찍기 시작한 것이 중요하다

남은 리스크:

- `frontend/src/types/gameState.ts`에는 아직 `model_versions` 타입이 없다
- 즉 backend state에는 들어가지만 frontend contract에는 아직 반영/활용되지 않는다

## 1-6. DB + JSONL 저장 구조

이 부분도 이미 많이 구현되어 있다.

확인한 증거:

- `backend/app/db/models.py`
  - `GameSession.model_versions`
  - `GameLog.action_data`
  - `GameLog.state_before`
  - `GameLog.state_after`
  - `GameLog.state_summary`
- `backend/app/services/game_service.py`
  - `GameLog(...)` 저장
  - `serialize_compact_summary(engine)`
  - `MLLogger.log_transition(...)`
- `backend/app/services/state_serializer.py`
  - `serialize_compact_summary(...)`
- `backend/app/services/ml_logger.py`
  - `action_mask_before`
  - `phase_id_before`
  - `current_player_idx_before`
  - `model_info`

테스트 증거:

- `backend/tests/test_game_action.py`
- `backend/tests/test_gamelog_vp_doubloon.py`
- `backend/tests/test_ml_logger.py`

판정:

- TODO의 `3-A`는 "조사" 단계가 아니라 이미 구현/검증 단계다
- TODO의 `3-B`는 부분 완료다
  - DB 원본
  - JSONL raw transition
  - compact summary
  구조는 실제 존재한다

남은 리스크:

- DB와 JSONL을 묶는 canonical key가 없다
- 현재는 `round`, `step`, `actor_id`, `action` 조합으로만 best-effort 대조 가능
- `step_id`, `state_hash`, `schema_version`은 아직 없다

## 1-7. WS 전달 경로와 fallback

이 부분도 일부 실제 수습이 들어가 있다.

확인한 증거:

- `backend/app/services/game_service.py`
  - `_sync_to_redis()`
  - Redis publish 성공 시 direct fallback 생략
  - Redis 실패 시 `manager.broadcast_to_game(...)`
- `backend/app/services/ws_manager.py`
  - `PLAYER_DISCONNECTED`
  - `GAME_ENDED`
  - Redis listener -> broadcast
- `frontend/src/hooks/useGameWebSocket.ts`
  - `STATE_UPDATE`
  - `GAME_ENDED`
  - `PLAYER_DISCONNECTED`
  - JSON stringify dedupe

테스트 증거:

- `backend/tests/test_priority2_ws_delivery_contract.py`
- `backend/tests/test_ws_disconnect.py`
- `frontend/src/hooks/__tests__/useGameWebSocket.test.ts`

판정:

- TODO의 `2-E`는 일부 구현이 들어와 있다
- direct + redis 중복 전파를 줄이려는 backend 수정도 존재한다

남은 리스크:

- `state_revision`이 없어서 consumer가 stale/out-of-order를 robust하게 막을 수 없다
- frontend dedupe가 아직 JSON stringify 기반이다

## 2. 아직 미완성인 것

## 2-1. 종료 UX / final-score / spectator contract

이 영역은 아직 핵심 문제가 남아 있다.

코드 증거:

- `frontend/src/App.tsx`
  - `state.meta.end_game_triggered`가 되면 `final-score` API를 fetch
  - `onGameEnded: () => {}` 로 사실상 no-op
  - 결과 화면은 `finalScores`가 있어야 의미 있게 렌더
- `backend/app/api/channel/game.py`
  - `GET /{game_id}/final-score`
  - 현재 `current_user.id in room.players` 조건을 요구

해석:

- bot-game host spectator는 `room.players`에 없으므로 403 가능성이 그대로 남아 있다
- frontend는 종료 화면을 terminal `STATE_UPDATE` payload만으로 완결하지 못하고, 별도 fetch에 의존한다
- `GAME_ENDED` 이벤트는 존재하지만 frontend game-end flow를 주도하지 않는다

즉 TODO의 `4-A ~ 4-E`는 아직 핵심 미완성이다.

## 2-2. 통합 lineage key 부재

현재 남는 값:

- DB: `round`, `step`
- JSONL: `info.step`, `phase_id_before`, `action_mask_before`
- state: `meta.step_count`

하지만 아직 없는 값:

- `step_id`
- `state_hash`
- `state_revision`

영향:

- `audit.md`의 Step-Lock Sankey를 정확히 그리기 어렵다
- DB / JSONL / WS / frontend render를 하나의 id로 연결할 수 없다

## 2-3. runtime 재현성 메타데이터 부족

테스트에는 seed 재현이 있지만 runtime 로그에는 아래가 없다.

- `game_seed`
- `governor_idx` snapshot per step
- build/app version
- replay reconstruction key

즉 audit의 "동일 시드에서 동일 결과"는 현재 runtime observability가 아니라 test evidence에 더 가깝다.

## 2-4. 행동 해석용 확률 분포 부재

현재 로그에는 아래가 있다.

- `action`
- `action_mask_before`
- `phase_id_before`
- `model_info`

하지만 아래는 없다.

- action probabilities
- logits
- top-k candidate actions

즉 `audit.md`의 probability heatmap은 현재 구조만으로는 정확 재현 불가다.

## 2-5. online monitoring 미계측

현재 코드에는 WS 이벤트와 timestamp는 있지만, 아래는 아직 없다.

- inference latency
- end-to-screen latency
- terminal delivery success rate
- stale revision drop count

즉 audit의 Online Monitoring은 아직 "지표 설계 필요" 상태다.

## 3. vis/ 추가 사항

이번 작업에서 아래 파일을 새로 추가했다.

- `vis/README.md`
- `vis/db/README.md`
- `vis/audit_requirements.md`
- `vis/common.py`
- `vis/render_lineage_report.py`
- `vis/render_storage_report.py`
- `vis/render_behavior_report.py`
- `vis/render_audit_requirements.py`

역할:

- 실제 DB/JSONL을 읽어 Markdown + Mermaid 리포트 생성
- 사람이 DB/로컬 로그를 수동으로 확인하는 절차 문서화
- `audit.md` 요구사항별로 현재 어떤 증거가 있고 무엇이 비었는지 시각화

## 4. 지금 시점의 우선순위 재정렬

실제 코드 상태를 기준으로 다시 보면 우선순위는 이렇게 잡는 것이 맞다.

1. `Priority 4 종료 UX`
   - final-score spectator 정책
   - terminal result payload
   - frontend game-end flow 정리
2. `lineage key 추가`
   - `step_id`
   - `state_hash`
   - `state_revision`
3. `runtime reproducibility stamping`
   - seed / governor / build / artifact
4. `behavior trace 확장`
   - probabilities/logits or top-k
5. `monitoring metric 추가`
   - latency / delivery success / stale drop

## 5. 최종 판단

이전 문서의 문제는 "남은 일"을 설계 관점에서만 본 것이고, 이번 재감사 결과 실제로는 아래가 맞다.

- Mayor 사람 입력 contract: 이미 구현됨
- mixed bot game 생성: 이미 구현됨
- bot_type routing: 이미 크게 복구됨
- seed/governor reproducibility: engine/test 수준으로 구현됨
- model registry / provenance snapshot: 이미 구현됨
- DB + JSONL + summary logging: 이미 구현됨
- WS fallback 일부: 구현됨

그리고 진짜 남은 핵심은 아래다.

- 종료 UX / final-score spectator contract
- canonical lineage id
- runtime reproducibility stamping
- probability-level behavior trace
- online monitoring metrics

즉 TODO 전체가 다 "설계만 남은 상태"는 아니고, 이미 구현된 축과 아직 비어 있는 축을 명확히 분리해서 다음 작업을 이어가는 것이 맞다.
