# PuCo_RL/train

학습 entrypoint 스크립트를 모은 폴더입니다.

## 현재 파일

- `train_ppo_selfplay_local.py`
- `train_ppo_selfplay_server.py`

## 관련 상위 스크립트

- 루트에도 `train_hppo_*`, `train_phase_ppo_*`, `train_ppo_selfplay_server.py` 같은 thin entrypoint가 존재합니다.

## 주요 출력

- `runs/<run_name>`
  - TensorBoard/학습 로그가 생성되는 기본 위치
- `models/ppo_checkpoints/`
  - 일부 로컬 학습 스크립트가 체크포인트를 저장하는 위치

## 의존성

- outbound: [../env/README.md](../env/README.md), [../agents/README.md](../agents/README.md), [../models/README.md](../models/README.md), [../../models/ppo_checkpoints/README.md](../../models/ppo_checkpoints/README.md)
