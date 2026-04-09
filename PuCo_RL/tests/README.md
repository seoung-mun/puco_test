# PuCo_RL/tests

엔진/agent/env의 규칙 계약을 검증하는 테스트 폴더입니다.

## 현재 검증 축

- `test_engine.py`, `test_pr_env.py`: core engine/env contract
- `test_mayor_strategy.py`, `test_mayor_strategy_mapping.py`: Mayor strategy mapping
- `test_mayor_sequential.py`: legacy/transition coverage
- `test_phase_edge_cases.py`, `test_agent_edge_cases.py`: phase/agent edge case
- `test_board_evaluator.py`, `test_hppo_agent.py`: 분석 및 agent 보조 검증

## 의존성

- 대상 코드: [../env/README.md](../env/README.md), [../agents/README.md](../agents/README.md), [../utils/README.md](../utils/README.md)

## 메모

- backend contract 변경이 엔진 action space에 닿는 경우 이 폴더도 함께 봐야 합니다.
