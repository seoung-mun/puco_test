# data

Castone 런타임이 남기는 로컬 데이터 산출물의 루트 폴더입니다.

## 하위 문서

- [logs/README.md](logs/README.md)

## 현재 구조

- `logs/games/*.jsonl`
  - backend `ml_logger.py`가 남기는 raw transition 로그
- `logs/replay/*.json`
  - backend `replay_logger.py`가 남기는 사람 친화적 replay 로그

## 메모

- 코드 정본은 아니지만, 운영/분석/재현성 측면에서 중요한 증거 저장소입니다.
- `vis/` 리포트는 주로 이 폴더와 DB를 함께 읽습니다.
- 개발 중 생성된 예시 로그가 커밋되어 있을 수 있습니다.
