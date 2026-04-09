# PuCo_RL/logs

`PuCo_RL` 자체의 오프라인 학습/평가 스크립트가 남기는 로그 산출물 폴더입니다.

## 현재 구조

- `replay/`
  - 평가 스크립트가 생성한 replay JSON
  - `analyze_replay.py` 같은 후처리 스크립트가 이 경로를 읽습니다.

## `data/logs`와의 차이

- `data/logs`
  - backend 실게임 런타임 로그
- `PuCo_RL/logs`
  - 오프라인 평가/실험 산출물
