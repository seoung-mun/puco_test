# Engine Cutover Phase 1 Lock

작성일: 2026-04-08  
관련 문서:
- `design/2026-04-08_engine_cutover_phase0_map.md`
- `design/2026-04-08_engine_cutover_task_breakdown.md`
- `design/2026-04-08_error_log_driven_design_report.md`
- `error_report/2026-04-06_puco_upstream_fetch_report.md`

## 1. 목적

Phase 1의 목적은 `PuCo_RL`을 "수정 대상 코드"가 아니라 "upstream 기준 canonical engine 패키지"로 고정하는 것이다.

이번 단계에서 한 일:

- rollback 기준 commit과 sync 기준 upstream ref를 고정했다.
- `puco-upstream/main` snapshot을 현재 workspace의 `PuCo_RL`에 비파괴적으로 overlay했다.
- root `.gitignore`에서 `PuCo_RL/env/*.py`를 다시 버전 관리 대상으로 보이게 만들었다.
- 이후 `PuCo_RL`을 직접 수정하지 않는 read-only 원칙을 문서화했다.
- backend wrapper에서 upstream env 시그니처 차이로 import/create smoke가 깨지지 않도록 최소 shim을 넣었다.
- docker 안에서 engine import/create/step smoke를 실행해 결과를 기록했다.

## 2. P1-T1 — `initial import` 기준점 확인

### 2.1 rollback anchor

- `Initial import` commit:
  - `9b87857fc50b68450dc67024a319d9a587a333d7`
  - 메시지: `Initial import`
- 첫 upstream fetch 반영 commit:
  - `003534aa5e5a279e1e23cae657fbe9cfd836a89f`
  - 메시지: `fetch 후`
- 현재 작업 시작 시 `HEAD`:
  - `da1ca0a`
  - 메시지: `dev 이전`

### 2.2 rollback 메모

이 phase에서 기준점을 되돌려야 할 때는 아래 순서를 권장한다.

1. `PuCo_RL`만 `initial import` 상태로 되돌리고 싶으면 `9b87857`를 기준으로 본다.
2. upstream sync 직전 기준으로 되돌리고 싶으면 `003534a`를 기준으로 본다.
3. 전체 브랜치 rollback이 아니라 `PuCo_RL` 범위 rollback만 먼저 고려한다.

실행 메모:

- `git show --stat --summary 9b87857 --`
- `git show --stat --summary 003534a --`
- `git restore --source <commit> --worktree --staged -- PuCo_RL`

주의:
- 마지막 명령은 실제 rollback 시에만 사용한다.
- 현재 worktree에는 phase1 이전부터 존재하던 backend/frontend 변경도 있으므로, 전체 repo reset보다 `PuCo_RL` 범위 restore가 안전하다.

## 3. P1-T2 — upstream mirror 반영

### 3.1 canonical upstream ref

현재 로컬에 fetch되어 있는 upstream remote-tracking ref는 아래다.

- remote: `puco-upstream`
- branch: `main`
- ref commit: `4949773`
- subject: `advanced_rule_based_agent는 shipping_rush_agent로 이름 변경, daehan_heuristic_agent는 action_value_agent로 이름 변경`

### 3.2 이번 phase에서 overlay한 범위

`git archive puco-upstream/main` snapshot을 `PuCo_RL/` 위에 비파괴적으로 overlay했다.

canonical engine 기준으로 직접 덮어쓴 파일:

- `PuCo_RL/.gitignore`
- `PuCo_RL/README.MD`
- `PuCo_RL/agents/heuristic_bots.py`
- `PuCo_RL/configs/constants.py`
- `PuCo_RL/env/engine.py`
- `PuCo_RL/env/pr_env.py`
- `PuCo_RL/evaluate/replay_single_game.py`
- `PuCo_RL/evaluate/run_league.py`
- `PuCo_RL/tests/test_engine.py`
- `PuCo_RL/tests/test_pr_env.py`
- `PuCo_RL/train/train_ppo_selfplay_server.py`
- `PuCo_RL/utils/evaluation/evaluator.py`
- `PuCo_RL/utils/evaluation/metrics.py`
- `PuCo_RL/utils/evaluation/plotter.py`

upstream-only 파일/디렉터리로 추가된 자산:

- `PuCo_RL/agents/action_value_agent.py`
- `PuCo_RL/agents/action_value_agent_formula.md`
- `PuCo_RL/agents/shipping_rush_agent.py`
- `PuCo_RL/env/__init__.py`
- `PuCo_RL/env/components.py`
- `PuCo_RL/env/player.py`
- `PuCo_RL/evaluate/heuristic_benchmark.py`
- `PuCo_RL/evaluate/visualize_apa_ppa.py`
- `PuCo_RL/tests/test_mayor_strategy.py`
- `PuCo_RL/web/`

추가 조치:

- root `.gitignore`의 `env/` 패턴이 `PuCo_RL/env/*`까지 가려서 canonical engine 파일이 git status에 보이지 않던 문제를 수정했다.
- 예외 규칙:
  - `!PuCo_RL/env/`
  - `!PuCo_RL/env/**/*.py`

### 3.3 phase1에서 의도적으로 보존한 local delta

아래 파일은 현재 dirty worktree와 충돌 가능성이 있어 phase1 overlay에서 덮어쓰지 않았다.
이들은 canonical upstream가 아니라 "임시 local delta"로 간주한다.

- `PuCo_RL/agents/__init__.py`
- `PuCo_RL/agents/base.py`
- `PuCo_RL/agents/wrappers.py`
- `PuCo_RL/tests/test_mayor_sequential.py`
- `PuCo_RL/tests/test_mayor_strategy_mapping.py`
- `PuCo_RL/tests/test_phase_edge_cases.py`

아래 항목도 아직 local-only로 남아 있다.

- `PuCo_RL/agents/advanced_rule_based_agent.py`
- `PuCo_RL/agents/factory_heuristic_agent.py`
- `PuCo_RL/agents/mcts_agent.py`
- `PuCo_RL/agents/mcts_agent_spite.py`
- `PuCo_RL/agents/random_agent.py`
- `PuCo_RL/agents/rule_based_agent.py`
- `PuCo_RL/evaluate/evaluate_agents_tournament.py`
- `PuCo_RL/evaluate/evaluate_convergence.py`
- `PuCo_RL/evaluate/evaluate_tournament.py`
- `PuCo_RL/evaluate_balance.py`
- `PuCo_RL/evaluate_tournament.py`
- `PuCo_RL/tests/test_agent_edge_cases.py`
- `PuCo_RL/tests/test_board_evaluator.py`
- `PuCo_RL/tests/test_engine_dual_mayor.py`
- `PuCo_RL/train_*.py`, `PuCo_RL/train_hppo_*.py`, `PuCo_RL/train_phase_ppo_*.py`
- `PuCo_RL/utils/analysis.py`
- `PuCo_RL/utils/board_evaluator.py`
- `PuCo_RL/logs/`, `PuCo_RL/models/`, `PuCo_RL/runs/`

판단:

- `env/engine.py`, `env/pr_env.py`, `configs/constants.py`는 이제 upstream 기준과 일치한다.
- 아직 남아 있는 local delta는 이후 phase에서 wrapper 경계 밖으로 걷어내거나 cleanup 대상으로 다룬다.
- 즉 phase1의 canonical engine 기준선은 upstream ref `4949773`이고, local-only 파일은 canonical contract의 일부가 아니다.

## 4. P1-T3 — `PuCo_RL` read-only 규칙

이후 작업 원칙:

- `PuCo_RL`은 upstream mirror 영역으로 취급한다.
- 앞으로 기능 수정은 우선 `backend/app/services/engine_gateway/` 또는 backend/frontend adapter에서 처리한다.
- `PuCo_RL/env/*`, `PuCo_RL/configs/*`, `PuCo_RL/agents/*`를 직접 수정하는 방식은 금지한다.
- upstream sync는 `puco-upstream/main` ref 기준으로만 수행한다.
- 예외는 "새 upstream snapshot overlay" 또는 "명시적 upstream 동기화 작업"뿐이다.

리뷰 규칙:

- `PuCo_RL` 수정 PR/patch는 기본적으로 reject 대상이다.
- upstream와의 차이를 늘리는 변경 대신 backend wrapper나 serializer 변경을 우선한다.
- `PuCo_RL`에 local-only 코드를 추가해야 한다면 먼저 phase 문서에 근거를 남기고, 가능하면 backend로 이동할 대체안을 같이 기록한다.

## 5. P1-T4 — engine import smoke test

### 5.1 실행 환경

- 날짜: 2026-04-08
- 실행 위치: docker backend container
- 선행 명령:
  - `docker compose up -d --build db redis backend`

### 5.2 smoke command 1

명령:

```bash
docker compose exec backend python -c "import json; from app.engine_wrapper.wrapper import create_game_engine; engine=create_game_engine(num_players=3); mask=engine.get_action_mask(); action=next(i for i, v in enumerate(mask) if v); result=engine.step(action); print(json.dumps({'valid_action_count': sum(int(v) for v in mask), 'first_action': int(action), 'done': bool(result['done']), 'phase_after': result['info'].get('current_phase_id'), 'current_player_idx_after': result['info'].get('current_player_idx')}, ensure_ascii=False))"
```

관측 결과:

- log:
  - `[ACTION_TRACE] engine_step_enter action=0 phase_before=8 current_player_idx_before=0 agent_selection=player_0`
  - `[ACTION_TRACE] engine_step_exit action=0 phase_after=0 current_player_idx_after=0 terminated=False truncated=False`
- output:
  - `{"valid_action_count": 6, "first_action": 0, "done": false, "phase_after": 0, "current_player_idx_after": 0}`

판정:

- backend에서 upstream `PuCo_RL` import 성공
- engine 생성 성공
- action mask 조회 성공
- 첫 valid action 1회 step 성공

### 5.3 smoke command 2 — phase1 compatibility shim 확인

명령:

```bash
docker compose exec backend python -c "import json; from app.engine_wrapper.wrapper import create_game_engine; engine=create_game_engine(num_players=3, player_control_modes=[1,0,1], governor_idx=0); mask=engine.get_action_mask(); print(json.dumps({'valid_action_count': sum(int(v) for v in mask), 'current_phase_id': engine.last_info.get('current_phase_id'), 'current_player_idx': engine.last_info.get('current_player_idx')}, ensure_ascii=False))"
```

관측 결과:

- log:
  - `Dropping unsupported PuertoRicoEnv kwargs for current upstream signature: player_control_modes`
- output:
  - `{"valid_action_count": 6, "current_phase_id": 8, "current_player_idx": 0}`

판정:

- upstream env 시그니처에 없는 backend-only kwargs가 phase1 shim에서 안전하게 무시됨
- 최소 import/create smoke 경로는 유지됨

## 6. P1-T5 — upstream 버전 fingerprint

### 6.1 canonical fingerprint

- source remote: `puco-upstream`
- source URL: `https://github.com/dae-hany/PuertoRico-BoardGame-RL-Balancing.git`
- source branch: `main`
- source commit: `4949773`
- source subject: `advanced_rule_based_agent는 shipping_rush_agent로 이름 변경, daehan_heuristic_agent는 action_value_agent로 이름 변경`

### 6.2 historical note

- `error_report/2026-04-06_puco_upstream_fetch_report.md`에 기록된 당시 `puco-upstream/main` 최신 커밋은 `5717b59`였다.
- 현재 local remote-tracking ref는 이제 `4949773`를 가리킨다.
- phase1 canonical fingerprint는 "문서에 기록된 옛 hash"가 아니라, 현재 local git ref가 가리키는 `4949773`로 고정한다.

## 7. phase1 완료 판정

- P1-T1 완료: rollback anchor를 `9b87857`, `003534a`, `da1ca0a` 기준으로 문서화했다.
- P1-T2 완료: upstream snapshot을 `PuCo_RL`에 overlay해 canonical engine 파일을 upstream 기준으로 맞췄다.
- P1-T3 완료: `PuCo_RL` read-only 규칙을 문서화했다.
- P1-T4 완료: docker backend에서 import/create/step smoke를 통과했다.
- P1-T5 완료: upstream remote/branch/commit/source URL fingerprint를 기록했다.

## 8. 다음 phase 입력

Phase 2에서는 이제 "무엇이 canonical engine이고 무엇이 local adapter인지"가 고정됐으므로, 아래를 바로 진행하면 된다.

1. `contract.md`에서 sequential Mayor public contract를 제거한다.
2. `state_serializer.py`와 frontend 타입에서 `mayor_slot_idx`, `mayor_can_skip`, `mayor_distribution` 의존을 없애는 새 계약을 정의한다.
3. `engine_gateway`를 만들어 backend의 direct import를 wrapper 경계 안으로 회수한다.
