# PuCo_RL/evaluate

오프라인 benchmark, league, replay 생성 스크립트를 모은 폴더입니다.

## 주요 파일

- `evaluate_agents_tournament.py`, `evaluate_tournament.py`: 대전 평가
- `evaluate_convergence.py`: 학습 경향 점검
- `heuristic_benchmark.py`: heuristic baseline 비교
- `run_league.py`: 리그 실행
- `replay_single_game.py`: 단일 게임 replay 생성
- `visualize_apa_ppa.py`: 평가 시각화

## 주요 출력

- `logs/replay/`
  - `replay_single_game.py`가 남기는 replay JSON
- 콘솔 표/CSV/그래프
  - 스크립트 옵션에 따라 추가 산출물이 생길 수 있습니다.

## 의존성

- outbound: [../agents/README.md](../agents/README.md), [../env/README.md](../env/README.md), [../utils/evaluation/README.md](../utils/evaluation/README.md)
- 로그 출력: [../logs/README.md](../logs/README.md)

## 메모

- backend 런타임 replay와 이 폴더의 replay는 생성 주체가 다릅니다.
