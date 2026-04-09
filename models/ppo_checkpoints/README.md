# models/ppo_checkpoints

로컬 실험이나 학습 스크립트가 PPO 체크포인트를 저장하는 자리입니다.

## 현재 상태

- 현재 저장소에는 README만 있고, 필요할 때 `.pth` 파일이 생성됩니다.
- 대표적으로 `PuCo_RL/train/train_ppo_selfplay_local.py`가 이 경로를 출력 대상으로 사용합니다.

## 메모

- 실제 서빙 기본 모델은 [../../PuCo_RL/models/README.md](../../PuCo_RL/models/README.md)를 봅니다.
- 체크포인트 이름 규칙과 실험 메타데이터를 같이 남겨 두는 편이 이후 비교에 유리합니다.
