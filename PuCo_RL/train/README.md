# PuCo_RL/train

학습 entrypoint 스크립트를 모은 폴더입니다.

## 현재 파일

- `train_ppo_selfplay_local.py`
- `train_ppo_selfplay_server.py`

## 관련 상위 스크립트

- 루트에도 `train_hppo_*`, `train_phase_ppo_*`, `train_ppo_selfplay_server.py` 같은 thin entrypoint가 존재합니다.

## 의존성

- outbound: [../env/README.md](../env/README.md), [../agents/README.md](../agents/README.md), [../models/README.md](../models/README.md), [../runs/README.md](../runs/README.md)
