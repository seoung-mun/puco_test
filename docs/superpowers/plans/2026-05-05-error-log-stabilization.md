# 에러 로그 안정화 구현 계획

> **에이전트 작업자에게:** 필수 서브 스킬: `superpowers:subagent-driven-development`(권장) 또는 `superpowers:executing-plans`을 사용해 이 계획을 태스크 단위로 구현하세요. 단계는 체크박스(`- [ ]`) 문법으로 추적합니다.

**목표:** `error_logs.md`에 나열된 활성 장애를 모델 부트스트랩 강화, 봇→프론트엔드 상태 전달, 새로고침/복구 연속성, Render 런타임 관측성 개선을 통해 해결한다.

**아키텍처:** PostgreSQL 액션 로그를 영구 게임 저널로 유지하고, Redis는 팬아웃/캐시 계층으로 두며, 인메모리 엔진은 단일 진실원이 아닌 복구 가능한 캐시로 취급한다. PPO 번들 시작 시점에 명시적 서빙 검증을 추가하고, 모든 봇 턴이 가시적인 `STATE_UPDATE`로 종료됨을 보장하며, 새로고침/재시작 시 사용자를 방 목록으로 떨어뜨리지 않고 활성 게임 컨텍스트를 복원한다.

**기술 스택:** FastAPI, SQLAlchemy, Redis, WebSocket, React/Vite, Render Docker 배포

---

## 1. 근본 원인 요약

### 1.1 PPO 메타데이터 / 번들 시작 검증이 부족함

**근거**

- `backend/app/services/agent_registry.py`는 번들 우선 로직으로 PPO를 해석한다.
- `backend/app/services/model_registry.py`는 유효한 번들 manifest + 체크포인트, 또는 체크포인트 + 사이드카 메타데이터 중 하나를 요구한다.
- `PuCo_RL/models/ppo-pr-server-semantic293-20260419/manifest.json`은 존재하지만, 런타임 검증은 실제 봇 턴이 모델을 필요로 할 때만 수행된다.
- `.env.example`과 `docs/2026-04-27_render_vercel_deployment_guide.md`는 표준 배포 계약 없이 여러 서빙 조합(`PPO_BUNDLE_DIR`, `PPO_MODEL_FILENAME`)을 허용한다.

**실제 문제**

- 시작 시점에 선택된 PPO 아티팩트가 첫 봇 턴 이전에 로드 가능한지 증명되지 않는다.
- Render가 잘못된 환경 오버라이드, 누락된 체크포인트, 오래된 비-번들 파일명을 가지면 시스템은 늦고 불투명하게 실패한다.

### 1.2 "봇이 액션을 골랐는데 프론트엔드가 움직이지 않음"은 추론 문제만이 아니라 전달 계약 문제임

**근거**

- `backend/app/services/bot_service.py`는 Mayor 배치를 묶어 처리하며 `remaining > 1`인 동안 `suppress_broadcast=True`를 사용한다.
- `backend/app/services/game_service.py`는 `suppress_broadcast`가 false일 때만 `_sync_to_redis()`를 호출한다.
- Mayor 배치가 억제된 액션 후 조기 종료되면, 보상하는 마지막 `STATE_UPDATE`가 없다.
- `backend/app/services/ws_manager.py`는 순차적으로 브로드캐스트하며 `_broadcast()` 동안 죽은 소켓을 정리하지 않는다.

**실제 문제**

- 엔진은 진행될 수 있고, 로그에는 선택된 액션이 보일 수 있지만, 모든 봇 경로에서 마지막 가시 상태 푸시가 보장되지 않기 때문에 UI는 여전히 멈출 수 있다.
- 봇 전용 게임 및 모든 다단계 Mayor/Builder 시퀀스에서 특히 위험하다.

### 1.2.1 봇 전용 게임이 첫 액션 직후 즉시 멈추는 진짜 원인: 스케줄러가 자기 자신의 인플라이트 태스크 때문에 다음 턴 등록을 사일런트로 스킵함

**관측된 라이브 시퀀스 (3-PPO 봇 게임, 시장 선택 직후 정지, 2026-05-05 트레이스)**

```text
schedule_bot                ... next_actor=BOT_ppo idx=2
task_created                ... task_id=281471894521792 active_bot_tasks=1
turn_start / turn_mask / turn_delay (3.0s, role_selection=True)
adapter_inference           ... bundle=ppo-pr-server-semantic293-20260419 action=1 fallback=False
turn_action_selected        ... action=1 (Mayor)
callback_enter
process_action_enter
engine_step_exit            ... current_player_idx_after=0   ← 다음 액터는 player_0
sync_to_redis_end
schedule_check              ... next_idx=0 next_actor=BOT_ppo
schedule_skip_existing_task ... task_id=281471894521792       ← 사일런트 스킵 (BUG)
process_action_exit
callback_exit
turn_action_applied
task_done                   ... task_id=281471894521792 active_bot_tasks=0   ← 슬롯만 비움, 재스케줄 호출 없음
(이후 영구 정지)
```

**근거**

- `backend/app/services/game_service.py:519-555` — `_schedule_next_bot_turn_if_needed`는 `GameService._bot_tasks`를 `game_id` 단일 키로 조회하며, `existing is not None and not existing.done()`이면 즉시 반환한다.
- `backend/app/services/game_service.py:467-472` — `process_action`은 자신의 콜 스택 안에서 직접 `_schedule_next_bot_turn_if_needed`를 호출한다.
- `backend/app/services/game_service.py:637-663` — `_make_bot_task_done_callback`은 `_bot_tasks` 슬롯을 비우고 워치독을 취소할 뿐, 다음 봇 턴 재시도를 트리거하지 않는다.
- `backend/app/services/bot_service.py:541-616` — `run_bot_turn`은 `process_action_callback`이 동기적으로 끝난 다음에야 코루틴 자체가 종료된다. 즉 콜백 실행 시점엔 자기 자신 태스크가 항상 `_bot_tasks`에 살아있다.

**근본 원인 (단일 이벤트 루프, 결정론적 데드락)**

1. 봇 태스크 T1이 `run_bot_turn` → `_apply_action_with_retry` → `_dispatch_action` → `process_action_callback(=sync_callback)` → `bg_service.process_action(...)`을 호출한다.
2. `process_action`이 엔진을 진행시키고, 같은 콜 스택 안에서 `_schedule_next_bot_turn_if_needed`를 호출한다.
3. 이 시점 `_bot_tasks[game_id]`는 여전히 T1 자신을 가리키며 `not done()`이다 (T1이 끝나려면 `process_action`이 먼저 리턴해야 함).
4. 스케줄러는 `schedule_skip_existing_task`로 사일런트 종료한다.
5. T1이 정상 종료되며 `_make_bot_task_done_callback`이 슬롯을 비운다 — 그러나 *다음 봇 턴을 재시도하는 경로가 없다.*
6. 결과: 엔진은 player_0으로 진행했지만 어떤 코루틴도 `BotService.run_bot_turn(player_0)`을 트리거하지 않아 게임이 영구 정지된다.

**왜 사람-봇 혼합 게임에서는 잘 안 보이는가**

- 사람 액션이 들어오면 외부에서 `process_action`이 다시 호출되고, 그 호출은 인플라이트 봇 태스크가 없으므로 스케줄러를 정상 통과한다.
- 봇 전용 게임에는 외부 트리거가 없어 첫 봇 액션 직후 정확히 한 번 막힌다.
- 1-사람 + 2-봇 구성에서도, 사람 턴이 끝난 직후 *연속으로* 두 봇이 와야 하는 케이스에서 동일한 정지가 발생한다(첫 봇 액션 후 두 번째 봇 트리거 누락).

**왜 §1.2와 별개인가**

- §1.2: `STATE_UPDATE`가 *발행되지 않음* (UI는 멈춤, 엔진은 계속 진행). 수정 위치는 `bot_service._run_mayor_batch_turn` / 발행 경로.
- §1.2.1: `STATE_UPDATE`는 정상 발행됨, 그러나 *엔진이 더 이상 진행하지 않음*. 수정 위치는 `game_service._schedule_next_bot_turn_if_needed` / `_make_bot_task_done_callback`.
- 두 버그가 동시에 존재하면 사용자에게는 같은 "멈춤"으로 보이지만, 수정 지점이 다르고, 둘 다 고쳐야 봇 전용 게임이 끝까지 진행된다.

**MLOps 관점**

- 모델 추론 자체는 정확히 동작했다(`adapter_inference ... action=1 fallback=False`, 어댑터 `puco.semantic293.type_mayor.v1`, 번들 정상 로드). 깨진 것은 ML 모델이 아니라 *서빙 워크플로 오케스트레이터*의 liveness 경로다.
- 현재 워치독(§1.5)은 *N초 무동작*만 본다 — 그러나 *왜* 무동작인지는 알려주지 않는다. 운영자는 다음 세 가지를 구분할 수 있어야 한다:
  1. 스케줄러가 의도적으로 스킵했음 (이번 케이스, `last_skip_reason="in_flight_self"`)
  2. 봇 추론이 행 걸림 (어댑터 인퍼런스 latency 폭주)
  3. 엔진 상태가 깨져 다음 액터를 결정할 수 없음
- 추론-스텝-재스케줄은 본질적으로 *agent serving loop*다. 이 루프가 self-deadlock 상태를 자가 회복하지 못한다는 것은 ML 서빙 SLO 관점에서 P0다.
- 회귀 방지를 위해 `tests/test_bot_only_progress.py`에서 봇 추론을 결정론 스텁으로 교체해 *모델 품질*과 *오케스트레이터 liveness*를 분리 검증해야 한다.

### 1.3 프론트엔드 셸에 새로고침 연속성이 누락됨

**근거**

- `frontend/src/hooks/useAuthBootstrap.ts`는 `login` 또는 `rooms`만 복원한다.
- `frontend/src/App.tsx`는 `screen`, `gameId`, `myPlayerId`, `isSpectator`, 로비/게임 컨텍스트를 컴포넌트 상태로만 저장한다.
- 영속화된 `active_game_context`가 없고, "이 인증된 사용자가 지금 어떤 활성 게임으로 다시 들어가야 하는가?"를 반환하는 백엔드 엔드포인트도 없다.

**실제 문제**

- 백엔드에서 게임이 살아 있어도 새로고침 시 방/게임 컨텍스트가 손실된다.
- 현재 복구 작업이 서버 재시작 후 엔진을 복원하지만, 프론트엔드는 사용자를 올바른 게임에 다시 붙일 라우트/세션 메모리가 없다.

### 1.4 15분 Redis 증상은 PostgreSQL 미스터리가 아니라 프로세스 라이프사이클을 가리킴

**근거**

- `error_logs.md`에 `Redis listener error ... Connection closed by server.` 직전에 `INFO: Shutting down`이 포함되어 있다.
- `backend/app/main.py`는 lifespan 종료 중 Redis를 닫는다.
- `backend/app/services/game_service.py`는 활성 게임 캐시/메타 키에 대해 Redis TTL을 900초로 설정한다.
- `/health`는 검사가 저하되어도 항상 HTTP 200을 반환한다.

**실제 문제**

- 가시적인 Redis 에러는 서버 종료 또는 인스턴스 교체의 다운스트림 증상이며, PostgreSQL이 게임플레이 연속성에 충분히 건강함을 증명하지 않는다.
- 현재 헬스 시맨틱은 "봇 게임이 멈췄는데 `/health`는 ok라고 함"을 진단하기에 너무 약하다.

### 1.5 봇/스톨 관측성은 존재하지만 복구 액션이 불완전함

**근거**

- `backend/app/services/game_service.py`는 `_bot_stall_watchdogs`를 생성하지만, 타임아웃을 로깅만 한다.
- `backend/app/api/channel/ws.py`는 이미 연결 시 `ensure_engine_loaded()`를 실행하며, 이는 좋다.
- `docs/shutdown_error.md`는 이미 lazy 복구 및 봇 재개를 의도된 방향으로 공식화했다.

**실제 문제**

- 스톨을 감지할 수 있지만, 강한 운영자 가시 신호를 발하거나 멈춘 봇 턴에 대해 안전한 재구동 경로를 수행하지는 못한다.

### 1.6 콜드 스타트 비용은 실재하지만 본 계획의 범위 밖임

**근거**

- `error_logs.md`는 Render 초기 배포가 "너무 느리다"고 언급하지만 비긴급으로 표시한다.
- 별도 보고서 `docs/2026-05-04_deployment_runtime_optimization_report.md`가 이미 Dockerfile 컨텍스트 크기, torch 설치 비용, `PuCo_RL` 복사 풋프린트를 분석하고 Phase 1/2/3 완화책을 제안한다.

**실제 문제**

- 콜드 스타트는 배포/재시작 지연에는 영향을 주지만, 위에 나열된 사용자 가시 *게임플레이* 장애를 발생시키지는 않는다. 둘을 섞으면 안정화 패치가 희석된다.

**결정**

- 본 계획은 의도적으로 Dockerfile, 베이스 이미지, 마이그레이션 엔트리포인트를 **재작성하지 않는다**. 이는 최적화 보고서의 영역이다.
- 교차 참조만: 본 계획의 Task 4 readiness 작업이 시작 순서를 건드릴 때, 최적화 보고서가 의존하는 Phase 1 항목들(`frontend/.dockerignore`, PPO 워밍업, 브로드캐스트 병렬화)을 회귀시키면 안 된다.

### 1.7 봇 카탈로그와 모델 인벤토리가 현재 제품 요구보다 광범위함

**근거**

- `backend/app/services/agent_registry.py`는 여전히 `ppo`, `hppo`, `advanced_rule`, `factory_rule`을 노출한다.
- `frontend/src/components/RoomListScreen.tsx`는 `/api/bot-types`를 가져와 백엔드가 노출하는 모든 것을 렌더링한다.
- `error_logs.md`는 라이브 봇 세트 축소와 오래된 모델 아티팩트 제거를 명시적으로 요청한다.

**실제 문제**

- 서빙이 여전히 불안정한 동안 운영 복잡도가 필요 이상으로 높다.
- 오래된 봇 타입과 오래된 모델 파일은 잘못된 선택, 메타데이터 노후화, 혼란스러운 QA의 표면적을 늘린다.

## 2. 권장 워크스트림

본 계획은 증상이 동일한 라이브 게임 경로에서 겹치므로 현재 에러 세트를 의도적으로 한 문서에 유지한다:

1. PPO 서빙 부트스트랩 강화
2. 봇 액션 → `STATE_UPDATE` 전달 보장
3. 새로고침/재참여 연속성
4. Render/런타임 관측성 및 재시작 허용
5. 안정화 후 봇 카탈로그 정리

실행 순서:

1. 워크스트림 A
2. 워크스트림 B
3. 워크스트림 C
4. 워크스트림 D
5. 워크스트림 E

AWS 마이그레이션은 **첫 번째 수정이어서는 안 된다**. 현재 깨짐의 대부분은 애플리케이션 계약 수준이며, 변경 없이 AWS로 옮겨도 재현될 것이다.

## 3. 파일 맵

### 백엔드 런타임 / 서빙

- 수정: `backend/app/services/agent_registry.py`
- 수정: `backend/app/services/model_registry.py`
- 수정: `backend/app/main.py`
- 생성: `backend/app/services/serving_health.py`
- 테스트: `backend/tests/test_agent_registry_bundle.py`
- 테스트: `backend/tests/test_model_registry_bootstrap.py`
- 테스트: `backend/tests/test_env_secrets.py`

### 백엔드 상태 전달 / 봇 복구

- 수정: `backend/app/services/bot_service.py`
- 수정: `backend/app/services/game_service.py`
- 수정: `backend/app/services/ws_manager.py`
- 수정: `backend/app/api/channel/ws.py`
- 테스트: `backend/tests/test_mayor_slot_contract.py`
- 테스트: `backend/tests/test_priority2_ws_delivery_contract.py`
- 테스트: `backend/tests/test_recovery_bot_resume.py`
- 생성: `backend/tests/test_bot_stall_recovery.py`

### 프론트엔드 새로고침 연속성

- 수정: `frontend/src/App.tsx`
- 수정: `frontend/src/hooks/useAuthBootstrap.ts`
- 수정: `frontend/src/hooks/useGameWebSocket.ts`
- 생성: `frontend/src/lib/activeGameSession.ts`
- 생성: `backend/app/api/channel/session.py`
- 테스트: `frontend/src/__tests__/App.auth-flow.test.tsx`
- 생성: `frontend/src/__tests__/App.refresh-rejoin.test.tsx`
- 생성: `backend/tests/test_active_game_session.py`

### 운영 헬스 / Render 준비도

- 수정: `backend/app/main.py`
- 수정: `backend/app/services/game_service.py`
- 생성: `backend/tests/test_runtime_health_contract.py`
- 갱신: `docs/2026-04-27_render_vercel_deployment_guide.md`
- 생성: `docs/2026-05-05_render_runtime_runbook.md`

### 봇 카탈로그 정리

- 수정: `backend/app/services/agent_registry.py`
- 수정: `backend/app/api/legacy/deps.py`
- 수정: `frontend/src/components/RoomListScreen.tsx`
- 다음 하위 테스트 갱신:
  - `frontend/src/components/__tests__/RoomListScreen.test.tsx`
  - `frontend/src/components/__tests__/EndGamePanel.test.tsx`
  - `backend/tests/test_agent_registry_bundle.py`

## 4. 태스크 계획

### Task 1: PPO 서빙 오설정 시 즉시 실패시키기

**파일:**

- 수정: `backend/app/services/agent_registry.py`
- 수정: `backend/app/services/model_registry.py`
- 생성: `backend/app/services/serving_health.py`
- 수정: `backend/app/main.py`
- 테스트: `backend/tests/test_agent_registry_bundle.py`
- 테스트: `backend/tests/test_model_registry_bootstrap.py`

- [ ] **Step 1: 시작-안전 서빙 검증기 추가**

활성 PPO 아티팩트를 정확히 한 번 해석하고 구조화된 결과를 반환하는 헬퍼를 만든다:

```python
@dataclass(frozen=True)
class ServingHealth:
    ok: bool
    bot_type: str
    source: str | None
    artifact_name: str | None
    detail: str | None = None
```

검증기는 다음을 수행해야 한다:

- `resolve_model_artifact("ppo")`를 해석한다
- `use_adapter=True`일 때 `get_adapter_runtime("ppo")`를 시도한다
- 잡히지 않은 런타임 예외를 발생시키지 않고 구조화된 실패를 반환한다

- [ ] **Step 2: 배포 계약 표준화**

검증기가 하나의 명확한 Render 프로덕션 규칙을 강제하게 한다:

- `MODEL_TYPE=ppo`
- `PPO_BUNDLE_DIR=ppo-pr-server-semantic293-20260419` (정규 post-refactor 번들, obs_dim=293)
- 프로덕션에서 `PPO_MODEL_FILENAME` 비어있음

정규 서빙 아티팩트는 `PPO_test.pth`가 아니라 **번들**이다. 프로젝트 메모리에 따르면, 번들이 현재 리포에 존재하는 유일한 post-refactor(293-dim semantic obs / slot-direct mayor 200-action) 아티팩트이며, `PuCo_RL/models/` 아래의 단독 `.pth` 파일은 pre-refactor이고 **자동 승격되어서는 안 된다**.

따라서:

- 번들 경로가 유일한 1급 프로덕션 타깃이다.
- `PPO_MODEL_FILENAME` basename 자동 해석은 문서화된 레거시 폴백 드릴(예: 번들 장애 디버깅)로만 남긴다. 본 패치에서 승격 로직을 받지 않는다.
- 번들과 모델 오버라이드가 모두 설정되면, 선택된 우선순위에 대해 경고를 한 번 로그하고 서빙 헬스 출력에 노출한다. 검증기는 "레거시 오버라이드에서 실행 중"임을 명확히 표시해 프로덕션에서 조용히 일어날 수 없게 해야 한다.

- [ ] **Step 3: 운영자 친화적 엔드포인트에 서빙 상태 노출**

헬스 출력에 `serving` 하위 섹션 추가:

```json
{
  "status": "ok",
  "checks": {
    "postgresql": "ok",
    "redis": "ok",
    "serving": {
      "status": "ok",
      "artifact_name": "ppo-pr-server-semantic293-20260419",
      "metadata_source": "bundle_v2"
    }
  }
}
```

PPO 오설정만으로 부팅을 충돌시키지 말고, 실패를 즉시 가시화한다.

- [ ] **Step 4: 집중 테스트 추가**

다음을 커버:

- 누락된 번들 manifest → 저하된 서빙 헬스, 충돌 없음
- 누락된 번들 체크포인트 → 정확한 사유와 함께 저하된 서빙 헬스
- 번들 + env 오버라이드 우선순위 → 결정론적인 선택 아티팩트

실행:

```bash
docker compose exec backend pytest \
  tests/test_agent_registry_bundle.py \
  tests/test_model_registry_bootstrap.py \
  tests/test_env_secrets.py \
  -q
```

### Task 2: 모든 봇 턴에 가시적인 최종 `STATE_UPDATE` 보장

**파일:**

- 수정: `backend/app/services/bot_service.py`
- 수정: `backend/app/services/game_service.py`
- 수정: `backend/app/services/ws_manager.py`
- 테스트: `backend/tests/test_mayor_slot_contract.py`
- 테스트: `backend/tests/test_priority2_ws_delivery_contract.py`
- 생성: `backend/tests/test_bot_stall_recovery.py`

- [ ] **Step 1: Mayor 배치 종료 시 최종 가시 상태 플러시**

`_run_mayor_batch_turn()`이 하나 이상의 억제된 액션 후 종료할 때, 마지막 적용 액션이 이미 발행하지 않았다면 정확히 하나의 최종 상태 동기화를 강제한다.

핵심 규칙:

- 엔진이 진행되었음
- 아직 공개 브로드캐스트가 일어나지 않았음
- 어떤 이유로든 배치가 종료됨

이때 단일 보상 발행 경로를 호출한다.

- [ ] **Step 2: "내부 단계 억제"와 "UI 업데이트가 전혀 없음"을 분리**

봇 배치 로직이 가시 발행이 여전히 빚져 있는지 알도록 작은 누적 객체를 추가한다:

```python
@dataclass
class BotTurnDeliveryState:
    visible_publish_emitted: bool = False
    actions_applied: int = 0
```

이는 로그에서 추론하는 것이 아니라 봇 배치 경로가 소유해야 한다.

- [ ] **Step 3: WebSocket 브로드캐스트 동작 강화**

`ws_manager.py`의 `_broadcast()`를 다음과 같이 갱신한다:

- `asyncio.gather(..., return_exceptions=True)`로 동시 전송
- `active_connections`에서 죽은 소켓 제거
- 룸이 진정으로 활성 소켓 0개가 될 때까지 Redis 리스너 유지

이는 "죽은 소켓 하나가 룸을 멈춤"을 줄여준다.

- [ ] **Step 4: 스톨 워치독을 단순 로깅에서 구조화 신호로 전환**

자동 게임플레이는 보수적으로 유지하되, 워치독 타임아웃 시:

- `game_id`, `actor_id` (봇 id), `bot_type`, `phase` (예: 역할 선택 / 건축가 픽 / 빌드 / mayor-batch), `active_player_id`, `last_applied_revision`, `revisions_since_last_visible_publish`, `seconds_since_last_action`을 포함하는 구조화된 로그 레코드를 발행
- 선택적으로 `BOT_STALLED`를 admin/debug 소비자(프론트엔드 옵트인)에게 발행

이는 관찰된 `action_value`×3 봇 전용 장애(역할 선택을 지나 진행했고 건축가 픽에서 잠긴 후 멈춤)를 구체적으로 다뤄야 하므로, 구조화된 레코드가 세션을 다시 돌리지 않고도 *어느 단계*가 얼어붙었는지 알려줄 충분한 컨텍스트를 가져야 한다.

첫 안정화 패치에서는 아직 자동 몰수를 **하지 마라**. 자동 복구 / 몰수 정책은 연기됨 (§5 범위 노트 참조).

- [ ] **Step 5: 전달 계약 테스트 추가**

다음을 커버:

- 억제된 중간 액션이 있는 Mayor 배치도 하나의 가시 `STATE_UPDATE`로 종료됨
- Redis 발행 실패 시 직접 폴백을 트리거함
- 죽은 웹소켓이 제거되며 다른 수신자를 막지 않음

실행:

```bash
docker compose exec backend pytest \
  tests/test_mayor_slot_contract.py \
  tests/test_priority2_ws_delivery_contract.py \
  tests/test_recovery_bot_resume.py \
  tests/test_bot_stall_recovery.py \
  -q
```

- [ ] **Step 6: lazy 종료 복구가 실제로 진행 중인 게임을 재구동하는지 검증**

`error_logs.md`는 최근 머지된 종료 복구 흐름("commit 7b350e7 feat(recovery): add lazy shutdown recovery flow")이 아직 프로덕션 시맨틱으로 종단 간 확인되지 않았음을 표시한다.

다음을 수행하는 통합 수준 스모크를 추가:

- 2-인간 / 1-봇 게임(또는 현재 룸 규칙에 따른 1-인간 / 2-봇 게임)을 시작하고, 최소 2개 리비전 진행
- PostgreSQL 액션 로그 + Redis 캐시는 유지하면서 인메모리 `active_engines`를 비워 서버 재시작을 시뮬레이션
- 웹소켓 재부착 시, `ensure_engine_loaded()`가 엔진을 재구성하고 액션 로그를 재생하며 마지막 영속화된 리비전과 일치하는 정확히 하나의 가시 `STATE_UPDATE`를 재발행하는지 확인
- 재시작 전 봇이 다음 턴을 소유했다면, 인간 푸시 없이 그 턴이 재개되는지 확인

`tests/test_recovery_bot_resume.py`와 픽스처를 공유하지만, Step 1의 *전달* 계약을 명시적으로 단언하므로, 양쪽 어느 쪽의 회귀도 이 단일 테스트가 실패하게 된다.

### Task 2A: 봇 전용 게임에서 다음 봇 턴이 항상 트리거되도록 스케줄러 자가 회복 보장 (§1.2.1 대응)

이 태스크는 Task 2와 분리되어 있다. Task 2가 *전달 가시성*(STATE_UPDATE 발행)을 다룬다면, Task 2A는 *스케줄러 liveness*(다음 봇 턴 트리거)를 다룬다. 두 문제는 사용자에게 동일한 "멈춤"으로 보이지만 수정 위치가 다르고, 봇 전용 게임이 끝까지 진행되려면 둘 다 고쳐야 한다.

**파일:**

- 수정: `backend/app/services/game_service.py`
  - `_schedule_next_bot_turn_if_needed` (line ~519)
  - `_make_bot_task_done_callback` (line ~637)
- 생성: `backend/tests/test_bot_only_progress.py`

- [ ] **Step 1: `task_done` 콜백에서 다음 봇 턴 재시도**

  `_make_bot_task_done_callback`이 `_bot_tasks` 슬롯을 비우고 워치독을 취소한 *직후*, 다음 조건이 모두 참이면 `_schedule_next_bot_turn_if_needed`를 한 번 더 호출한다:

  - 게임이 종료/일시정지 상태가 아님
  - `active_engines[game_id]`가 살아있음
  - 엔진의 현재 액터가 여전히 `BOT_*`로 시작
  - 직전 태스크가 *정상 종료*됨 (`cancelled`나 `exception`이 아님 — 그렇지 않으면 무한 루프 위험)

  핵심 규칙:

  - 슬롯이 비워진 **후**에 호출해야 새 스케줄이 자기 자신을 다시 스킵하지 않는다.
  - 이벤트 루프 재진입 안전성을 위해 `loop.call_soon(...)`으로 다음 틱에 디스패치하는 것을 권장 (현재 콜백 컨텍스트 안에서 직접 호출하면 또다시 자기 자신과 경쟁할 수 있음).
  - 예외/취소된 태스크는 재시도하지 않고 *구조화된* 로그(`scheduler_skipped_failed_task` + `actor_id`, `last_revision`, `exception_repr`)만 남긴다.

- [ ] **Step 2: 스케줄러 스킵 사유를 운영 가시 신호로 승격**

  `schedule_skip_existing_task`는 현재 정상 동작 중에도 발생하는 빈도 높은 이벤트인데 사유 정보가 부족하다. 다음을 추가:

  - 스킵 시 `existing_task_actor`, `engine_revision`, `current_player_idx`, `seconds_since_existing_task_started`를 함께 로그
  - Task 2 Step 4의 구조화 워치독 페이로드에 `last_skip_reason`(`in_flight_self` | `paused` | `idx_out_of_range` 등) 필드 추가
  - 스킵 후 N초 이내에 새 태스크가 만들어지지 않으면 워치독이 발화하도록 워치독 시계를 *마지막 스킵 시각*도 함께 추적

- [ ] **Step 3: 봇 전용 게임 진행 회귀 테스트**

  `backend/tests/test_bot_only_progress.py` 신규:

  - 결정론적 봇(예: `random` 시드 고정 또는 `BotService.get_action`을 결정론 스텁으로 패치)으로 3-봇 게임 시작
  - 첫 봇 액션 적용 후 `await asyncio.sleep(0)` 한 틱 안에 다음 봇 태스크가 생성되는지 단언 (`_bot_tasks[game_id]`가 새 객체로 교체됨)
  - N=10개 연속 액션이 외부 트리거 없이 진행되는지 단언
  - 회귀 가드: 스케줄러가 `schedule_skip_existing_task`를 한 번 발화하더라도, 그 직후 `task_done` → 새 `task_created`가 짝을 이뤄 발생하는지 카운트로 단언

- [ ] **Step 4: Task 2 Step 4 워치독과 통합 — 안전망 유지**

  Step 1을 적용해도 워치독은 마지막 안전망으로 유지한다. 만약 `task_done`이 어떤 이유로든 호출되지 않거나(예외 삼킴, GC race), 재스케줄이 또 다른 미세 버그로 실패하면 워치독이 단일 알람 소스가 된다. Step 1은 워치독을 **대체하지 않고 보완**한다.

  워치독은 새로 추가된 `last_skip_reason`을 페이로드에 포함해, 운영자가 "스케줄러가 의도적으로 스킵했지만 회복 못 함" vs "봇 추론이 행 걸림"을 즉시 구분할 수 있게 한다.

- [ ] **실행:**

  ```bash
  docker compose exec backend pytest \
    tests/test_bot_only_progress.py \
    tests/test_recovery_bot_resume.py \
    tests/test_bot_stall_recovery.py \
    -q
  ```

### Task 3: 새로고침 시 활성 게임 컨텍스트 복원

**파일:**

- 수정: `frontend/src/App.tsx`
- 수정: `frontend/src/hooks/useAuthBootstrap.ts`
- 생성: `frontend/src/lib/activeGameSession.ts`
- 생성: `backend/app/api/channel/session.py`
- 테스트: `frontend/src/__tests__/App.auth-flow.test.tsx`
- 생성: `frontend/src/__tests__/App.refresh-rejoin.test.tsx`
- 생성: `backend/tests/test_active_game_session.py`

- [ ] **Step 1: 로컬에 활성 게임 셸 컨텍스트 영속화**

다음 형태의 작은 헬퍼 작성:

```ts
type ActiveGameSession = {
  gameId: string
  screen: 'lobby' | 'game'
  myPlayerId: string | null
  myName: string | null
  isSpectator: boolean
  isMultiplayer: boolean
}
```

다음 시점에 영속화:

- 룸 입장
- `GAME_STARTED` 수신
- 봇 전용 관전 게임 입장

다음 시점에 클리어:

- 룸 떠남
- 로그아웃
- 게임 수동 포기

- [ ] **Step 2: 인증된 재진입을 위한 백엔드 지원 추가**

존재한다면 사용자의 현재 활성 룸/게임을 반환하는 경량 엔드포인트 노출:

```json
{
  "has_active_game": true,
  "game_id": "<uuid>",
  "status": "WAITING|PROGRESS|RECOVERY_BLOCKED",
  "is_host": true,
  "is_player": true
}
```

이는 프론트엔드가 오래된 로컬 스토리지를 맹목적으로 신뢰하는 것을 방지한다.

- [ ] **Step 3: auth 부트스트랩을 `login|rooms` 너머로 확장**

`/auth/me` 성공 후 부트스트랩은:

1. 영속화된 활성 세션을 읽음
2. 백엔드 활성 게임 엔드포인트로 검증
3. 여전히 유효하면 `lobby` 또는 `game`으로 복원
4. 그렇지 않으면 `rooms`로 폴백

- [ ] **Step 4: 게임 새로고침 시 재참여 동작**

복원 타깃이 `game`이면 게임 웹소켓을 즉시 재연결.  
복원 타깃이 `lobby`이면 로비 웹소켓을 즉시 재연결.

복구가 차단되면, 마지막 알려진 상태를 화면에 유지하고 사용자를 룸으로 떨어뜨리는 대신 기존 `RECOVERY_BLOCKED` 모달을 보여준다.

- [ ] **Step 5: 새로고침 테스트 추가**

다음을 커버:

- 로비 중 새로고침 → 로비로 복귀
- 진행 중 게임 중 새로고침 → 게임으로 복귀
- 오래된 로컬 활성 게임 캐시는 거부되고 룸으로 폴백

실행:

```bash
docker compose exec backend pytest tests/test_active_game_session.py -q
docker compose exec frontend npm run test -- \
  src/__tests__/App.auth-flow.test.tsx \
  src/__tests__/App.refresh-rejoin.test.tsx
```

### Task 4: Liveness와 게임플레이 Readiness 분리

**파일:**

- 수정: `backend/app/main.py`
- 수정: `backend/app/services/game_service.py`
- 생성: `backend/tests/test_runtime_health_contract.py`
- 갱신: `docs/2026-04-27_render_vercel_deployment_guide.md`
- 생성: `docs/2026-05-05_render_runtime_runbook.md`

- [ ] **Step 1: 저렴한 Render liveness 엔드포인트 보존**

"프로세스가 떠 있음" 검사를 위해 `/health`를 유지하거나 `/live` 추가.

이 엔드포인트는 게임플레이 준비도를 주장해서는 안 된다. 다음만 답한다:

- 프로세스 살아있음
- 이벤트 루프 살아있음

- [ ] **Step 2: 더 깊은 readiness/런타임 엔드포인트 추가**

다음을 포함하는 더 풍부한 readiness 뷰 생성:

- PostgreSQL 연결성
- Redis 연결성
- PPO 서빙 헬스
- 활성 엔진이 없는 `PROGRESS` 게임의 선택적 카운트
- 실행 중인 봇 태스크 / 멈춘 워치독의 선택적 카운트

이는 인간이 "서버는 ok라는데 게임이 얼었다"를 진단할 때 사용하는 엔드포인트다.

- [ ] **Step 3: Render 해석 문서화**

런북은 명시적으로 다음을 진술해야 한다:

- `Shutting down` 직후의 `Redis listener error ... Connection closed by server`는 프로세스 종료 중 예상되는 동작
- 900초 Redis 키 TTL은 캐시 만료이며 프로세스 종료의 근본 원인이 아님
- 장기 유휴 장애 진단 시 런타임 readiness + Render 배포 이벤트를 함께 사용

- [ ] **Step 4: 테스트 추가 및 문서 갱신**

다음 계약 테스트 추가:

- liveness 엔드포인트가 200을 유지함
- readiness 엔드포인트가 저하된 serving/redis/db 상태를 정확히 보여줌
- 현재 `tests/test_health_endpoint.py`의 기대치가 옛 "저하 시 503" 가정 대신 새로운 분리 계약과 정렬됨

실행:

```bash
docker compose exec backend pytest \
  tests/test_health_endpoint.py \
  tests/test_runtime_health_contract.py \
  -q
```

### Task 5: 런타임이 안정된 후 봇 카탈로그 축소

**파일:**

- 수정: `backend/app/services/agent_registry.py`
- 수정: `backend/app/api/legacy/deps.py`
- 수정: `frontend/src/components/RoomListScreen.tsx`
- 매칭 테스트 갱신

- [ ] **Step 1: 공개 선택 가능한 봇 목록 동결**

제품이 여전히 노출하기를 원하는 봇 타입만 유지:

- `random`
- `action_value`
- `shipping_rush`
- `ppo` (의도된 `PPO_test.pth` 또는 승인된 번들 타깃이 백엔드)

`hppo`, `advanced_rule`, `factory_rule`을 사용자 대상 카탈로그에서 먼저 제거.

- [ ] **Step 2: 카탈로그 정리와 아티팩트 삭제 분리**

런타임 안정화를 변경하는 동일 패치에서 모델 파일을 삭제하지 말 것.  
먼저 런타임을 안전하게 만들고, 그 다음 짧은 스모크 테스트로 인벤토리 제거 패치를 진행.

- [ ] **Step 3: UI 기본값 및 테스트 갱신**

룸/봇-게임 셀렉터가 좁혀진 카탈로그만 보여주게 하고, 관련 스냅샷/테스트 갱신.

실행:

```bash
docker compose exec frontend npm run test -- \
  src/components/__tests__/RoomListScreen.test.tsx \
  src/components/__tests__/EndGamePanel.test.tsx
docker compose exec backend pytest tests/test_agent_registry_bundle.py -q
```

## 5. 범위 노트

### 지금 포함

- PPO 서빙 시작 검증
- 봇 액션 → 프론트엔드 전달 보장
- 새로고침/재참여 연속성
- Render 런타임 진단 시맨틱

### 다음 안정화 계획으로 연기

- 동시 참여 / 호스트 변경에 대한 전체 멀티플레이어 레이스 방지
- AWS 마이그레이션 결정
- 리플레이 페이로드 크기 최적화
- 봇 스톨 후 적극적 자동 복구
- 오래된 모델 아티팩트의 물리적 삭제

## 6. 권장되는 첫 PR 슬라이스

가장 좋은 첫 PR:

1. **Task 2A** (봇 전용 게임이 첫 액션 후 즉시 멈추는 라이브 P0 — 가장 빠른 사용자 가시 효과)
2. Task 1
3. Task 2
4. 세 태스크의 최소 테스트 (`test_bot_only_progress.py` 포함)

이유:

- Task 2A는 §1.2.1의 라이브 재현된 데드락이며, 봇 전용 / 1-사람-2-봇 게임이 끝까지 진행되려면 *전제*다.
- Task 1은 PPO 서빙이 깨졌을 때 운영자에게 즉각 신호를 줘 Task 2A 디버깅 시 모델 자체 문제와 오케스트레이터 문제를 빠르게 분리시킨다.
- Task 2는 새로고침/세션 작업 전에 "봇 로그는 움직였는데 UI는 안 움직임" 모호함을 제거한다.
- 셋을 한 PR로 묶으면, "엔진은 진행됐지만 UI 안 움직임"(Task 2)과 "엔진 자체가 진행 안 됨"(Task 2A)이 같은 회귀 스위트에서 동시에 가드된다.

## 7. 핵심 결정

1. 애플리케이션 수준 계약을 고치기 전에 AWS로 마이그레이션하지 않는다.
2. `/health ok`를 게임플레이가 건강하다는 증거로 취급하지 않는다.
3. 서빙이 여전히 모호한 동안 오래된 봇/모델 옵션을 노출된 채로 두지 않는다.
4. Redis TTL 동작에 의존해 프로세스 종료를 설명하지 않는다. 여기서 Redis는 영속적 진실이 아닌 캐시/팬아웃이다.
5. 억제된 봇 배치가 마지막 공개 상태 플러시 없이 종료되게 두지 않는다.

## 8. 기대 결과

Task 1-4 이후:

- PPO 서빙 설정이 잘못되었을 때 Render 배포가 큰 소리로 진단 가능하게 실패한다.
- 봇 턴이 항상 프론트엔드의 가시적 상태 전이로 이어진다.
- 새로고침이 사용자를 룸 목록 대신 활성 로비/게임으로 되돌린다.
- 운영자가 프로세스 liveness와 실제 게임플레이 readiness를 구별할 수 있다.
- 복구/재시작 디버깅이 추측 기반 대신 증거 기반이 된다.
