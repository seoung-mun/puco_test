# PuCo_RL/agents

엔진 위에서 action을 선택하는 heuristic/RL agent 구현 폴더입니다.

## 주요 구성

- 기초 인터페이스: `base.py`
- rule/random 계열: `random_agent.py`, `rule_based_agent.py`, `factory_rule_based_agent.py`, `advanced_rule_based_agent.py`
- heuristic 특화 계열: `heuristic_bots.py`, `factory_heuristic_agent.py`, `shipping_rush_agent.py`, `action_value_agent.py`
- 탐색 계열: `mcts_agent.py`, `mcts_agent_spite.py`
- 정책 모델 계열: `ppo_agent.py`
- backend/serving adapter: `wrappers.py`, `__init__.py`

## 의존성

- outbound: [../env/README.md](../env/README.md), [../configs/README.md](../configs/README.md)
- inbound: [../../backend/app/services/engine_gateway/README.md](../../backend/app/services/engine_gateway/README.md), [../evaluate/README.md](../evaluate/README.md), [../train/README.md](../train/README.md)

## 메모

- 새 agent는 mask 기반 action 선택을 명시적으로 지켜야 합니다.
- backend serving과 학습용 래퍼를 섞지 않도록 주의합니다.
