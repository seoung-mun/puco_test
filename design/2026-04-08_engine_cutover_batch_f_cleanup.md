# Engine Cutover Batch F Cleanup

작성일: 2026-04-08  
연결 backlog: `design/2026-04-08_engine_cutover_task_breakdown.md`  
대상 task: `P6-T1`, `P6-T2`, `P6-T3`, `P6-T4`, `P6-T5`, `P7-T4`, `P7-T5`

## 1. 구조 분리 결과

### Frontend

- `frontend/src/hooks/useAuthBootstrap.ts`
  - auth bootstrap / local token restore / nickname gating 분리
- `frontend/src/components/AppScreenGate.tsx`
  - login / rooms / join / lobby gate 분리
- `frontend/src/components/GameScreen.tsx`
  - game 화면 렌더링, Mayor strategy panel, trader/captain/discard action card 렌더링 분리
- `frontend/src/App.tsx`
  - screen orchestration, websocket state wiring, action dispatch orchestration 중심으로 축소

### Backend

- `backend/app/services/game_service_support.py`
  - room player/bot name 해석
  - model_versions snapshot 생성
  - replay player snapshot 생성
  - rich state builder 분리
- `backend/app/services/state_serializer_support.py`
  - phase/role/good/tile mapping
  - mask guard
  - common board / player serializer
  - score breakdown 계산
- `backend/app/services/state_serializer.py`
  - public serializer entrypoint만 유지

## 2. Dead File 정리

삭제된 legacy 파일:

- `backend/app/services/mayor_orchestrator.py`
- `backend/app/services/mayor_strategy_adapter.py`
- `backend/app/services/agents/__init__.py`
- `backend/app/services/agents/factory.py`
- `backend/app/services/agents/legacy_models.py`
- `backend/app/services/agents/wrappers.py`

삭제된 legacy 테스트:

- `backend/tests/test_bot_mayor_adapter_integration.py`
- `backend/tests/test_mayor_strategy_adapter.py`
- `backend/tests/test_mayor_orchestrator.py`
- `backend/tests/test_todo_priority1_task1_mayor_contract.py`
- `backend/tests/test_channel_mayor_distribute.py`
- `backend/tests/test_agent_compatibility.py`
- `backend/tests/test_legacy_ppo_wrapper.py`

## 3. Import Path 정책

`PuCo_RL` import path bootstrap은 아래 위치만 허용한다.

- canonical bootstrap: `backend/app/services/engine_gateway/bootstrap.py`
- wrapper entrypoint: `backend/app/engine_wrapper/wrapper.py`
  - 자체 경로 조작 대신 `ensure_puco_rl_path()`를 호출
- legacy compatibility only: `backend/app/api/legacy/*`

추가 제약:

- active backend app code는 `engine_gateway` / `engine_wrapper` / `api/legacy` 바깥에서 `from env.*`, `from configs.*`, `from agents.*`를 직접 import하지 않는다.
- 이 규칙은 `backend/tests/test_engine_gateway_import_guard.py`가 보장한다.

## 4. Bot / Mayor 정리 기준

- `BotService.run_bot_turn()`은 Mayor를 위한 별도 adapter 흐름을 두지 않는다.
- Mayor phase에서는 선택된 action을 `69-71` strategy band로 normalize해서 canonical engine action으로 바로 전달한다.
- invalid Mayor action이 나와도 fallback은 strategy band 내부에서만 일어난다.

## 5. 문서 정리 기준

현재 팀이 참조해야 하는 문서는 아래다.

- `contract.md`
- `design/2026-04-08_engine_cutover_task_breakdown.md`
- `design/2026-04-08_engine_cutover_phase0_map.md`
- `design/2026-04-08_engine_cutover_phase1_lock.md`
- `design/2026-04-08_engine_cutover_phase2_contract_followup.md`

아래 문서는 historical reference only로 deprecate 표식을 붙였다.

- `design/task_status_detailed.md`
- `design/dual_mayor_engine_design.md`
- `design/puco_solid_refactoring_scope_plan.md`
