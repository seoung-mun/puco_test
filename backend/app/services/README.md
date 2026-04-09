# backend/app/services

이 폴더는 backend의 비즈니스 로직 중심지입니다.

## 하위 문서

- [engine_gateway/README.md](engine_gateway/README.md)
- [agents/README.md](agents/README.md)

## 핵심 역할

- room 생성과 game start/step orchestration
- bot turn scheduling과 model registry 조회
- serializer, replay, transition logging
- websocket/lobby/event fan-out
- scenario regression과 startup cleanup

## 주요 파일

- [game_service.py](game_service.py): 게임 수명주기와 step 처리
- [game_service_support.py](game_service_support.py): player/model/state helper
- [bot_service.py](bot_service.py): bot actor 실행
- [state_serializer.py](state_serializer.py): frontend-friendly rich state 생성
- [replay_logger.py](replay_logger.py): 사람 친화적 replay 로그
- [ml_logger.py](ml_logger.py): ML용 transition JSONL
- [model_registry.py](model_registry.py): artifact/fingerprint metadata
- [scenario_regression.py](scenario_regression.py): known-bad scenario 자동 검증

## 의존성

- inbound: [../api/README.md](../api/README.md)
- outbound: [../db/README.md](../db/README.md), [../engine_wrapper/README.md](../engine_wrapper/README.md), [engine_gateway/README.md](engine_gateway/README.md), Redis, file logs

## 설계 메모

- `PuCo_RL` 직접 import는 `engine_gateway`나 wrapper로 수렴시키는 것이 원칙입니다.
- 새 도메인 로직은 `game_service.py`에만 계속 키우기보다 support/helper 파일로 분리하는 편이 낫습니다.
