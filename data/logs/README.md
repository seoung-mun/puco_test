# data/logs

Castone backend가 런타임 중 생성하는 로그 출력 루트입니다.

## 현재 구조

- `games/`
  - `game_id`별 JSONL transition 로그
- `replay/`
  - `game_id`별 replay JSON

## 생성 주체

- `backend/app/services/ml_logger.py`
- `backend/app/services/replay_logger.py`

## 메모

- `games/`는 ML/lineage 분석용, `replay/`는 사람 확인용으로 보는 편이 맞습니다.
