# Engine Cutover Promotion Gate

작성일: 2026-04-08  
연결 backlog: `design/2026-04-08_engine_cutover_task_breakdown.md`  
대상 task: `P5-T5`

## 1. 목적

모델 승격 시 "학습에서는 강하지만 실제 serving/replay에서는 다른 계약으로 동작하는" 문제를 막는다.

승격은 아래 4개 게이트를 모두 통과한 경우에만 허용한다.

## 2. Gate 정의

### Gate A. Compatibility Gate

아래 fingerprint가 serving 시점 canonical 값과 일치해야 한다.

- `action_space`
- `mayor_semantics`
- `env`

판정 기준:

- `model_registry`가 sidecar metadata를 우선 사용하되, 빠진 값은 canonical fingerprint로 backfill 한다.
- `build_replay_parity_snapshot()` 결과에서 `mismatched_players`가 비어 있어야 한다.

실패 조건:

- fingerprint key 누락
- `mismatched_players` 비어 있지 않음
- canonical env fingerprint와 다른 upstream ref 사용

관련 코드:

- `backend/app/services/model_registry.py`
- `backend/app/services/replay_logger.py`

관련 테스트:

- `backend/tests/test_model_registry_bootstrap.py`
- `backend/tests/test_model_version_snapshot.py`
- `backend/tests/test_replay_logger.py`
- `backend/tests/test_replay_logging_integration.py`

### Gate B. Offline Head-to-Head Gate

신규 모델은 최소한 아래 기준선 상대를 이겨야 한다.

- `random`
- `factory_rule`
- `shipping_rush`
- 현행 champion

권장 기준:

- champion 대비 승률이 하한선 이하로 떨어지지 않을 것
- 기준선 봇 상대로 명백한 열세가 없을 것

현재 저장소에는 승격 자동화 CLI가 아직 없으므로, 이 단계는 evaluation job 또는 별도 league 실행 결과를 decision log로 남긴다.

필수 기록 항목:

- 평가에 사용한 checkpoint / branch / commit
- seed set
- opponent pool
- 요약 승률표

### Gate C. Scenario Regression Gate

다음 known-bad 행동을 반드시 막아야 한다.

- Trader over-selection
- high-doubloon role priority miss
- Mayor strategy band drift

실행 기준:

```bash
docker compose exec backend pytest tests/test_scenario_regression_harness.py -q
```

통과 조건:

- scenario harness가 green
- fallback/random retry가 아니라 expected band/action 조건을 만족

관련 코드:

- `backend/app/services/scenario_regression.py`

### Gate D. Replay Parity Gate

실제 서비스 경로에서 생성된 replay 파일이 canonical fingerprint/parity를 담고 있어야 한다.

통과 조건:

- replay JSON에 top-level `parity` 존재
- `parity.expected.action_space == "castone.action-space.strategy-first.v1"`
- `parity.expected.mayor_semantics == "castone.mayor.strategy-first.v1"`
- `parity.mismatched_players == []`

권장 추가 확인:

- human Mayor smoke 1회
- bot Mayor smoke 1회
- replay entry의 `action` 설명이 strategy-first 의미를 반영할 것

## 3. 승격 절차

1. sidecar metadata와 bootstrap fingerprint를 확인한다.
2. compatibility/replay parity 테스트를 실행한다.
3. scenario regression harness를 실행한다.
4. offline head-to-head 결과를 decision log에 남긴다.
5. human/bot smoke replay를 확인한다.
6. 위 결과를 모두 첨부한 뒤에만 champion alias 또는 serving 기본값을 갱신한다.

## 4. 최소 실행 세트

아래 명령은 승격 전 최소 검증 세트다.

```bash
docker compose exec backend pytest \
  tests/test_model_registry_bootstrap.py \
  tests/test_model_version_snapshot.py \
  tests/test_replay_logger.py \
  tests/test_replay_logging_integration.py \
  tests/test_ml_logger.py \
  tests/test_scenario_regression_harness.py -q
```

추가로 최종 컷오버 기준선 확인 시 아래를 같이 실행한다.

```bash
docker compose exec backend pytest -q
docker compose exec frontend npm test
docker compose exec frontend npm run build
```

## 5. 차단 규칙

아래 중 하나라도 참이면 승격 금지다.

- fingerprint mismatch
- replay parity mismatch
- scenario regression fail
- full backend/frontend verification fail
- smoke replay에서 human/bot Mayor strategy 흐름 불일치

## 6. 현재 canonical fingerprint

- `action_space`: `castone.action-space.strategy-first.v1`
- `mayor_semantics`: `castone.mayor.strategy-first.v1`
- `env`: `puco-upstream/main@4949773`
