# models

제품 레벨에서 따로 관리하는 모델 산출물 루트입니다.

## 하위 문서

- [ppo_checkpoints/README.md](ppo_checkpoints/README.md)

## 현재 상태

- 현재 커밋된 파일은 거의 없고, 로컬 학습 산출물이 생길 때 채워지는 자리입니다.
- `PuCo_RL/train/train_ppo_selfplay_local.py` 같은 스크립트가 `models/ppo_checkpoints/`를 출력 경로로 사용할 수 있습니다.

## `PuCo_RL/models`와의 차이

- `PuCo_RL/models`
  - 현재 서버가 실제로 참조하는 기본 체크포인트와 sidecar 메타데이터
- `models/`
  - 로컬 실험/학습 산출물을 별도로 두기 위한 저장소
