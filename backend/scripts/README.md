# backend/scripts

운영/정비용 스크립트를 모아 둔 폴더입니다.

## 주요 파일

- [bootstrap_env_secrets.py](bootstrap_env_secrets.py): 시크릿 bootstrap 보조
- [cleanup_all_waiting_rooms.py](cleanup_all_waiting_rooms.py): 대기방 정리
- [migrate_transition_logs_to_per_game.py](migrate_transition_logs_to_per_game.py): 일간 JSONL을 game 단위로 분리
- [analyze_bot_transitions.py](analyze_bot_transitions.py): bot transition 분석

## 의존성

- inbound: 운영 작업, 로그 정비, 수동 분석
- outbound: [../app/README.md](../app/README.md), [../tests/README.md](../tests/README.md), [../../data/README.md](../../data/README.md)

## 메모

- 스크립트는 idempotent 여부와 대상 경로를 README/주석으로 명시하는 편이 좋습니다.
