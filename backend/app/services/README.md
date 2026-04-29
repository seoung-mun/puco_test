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
- [session_manager.py](session_manager.py): per-game engine session wrapper
- [bot_service.py](bot_service.py): bot actor 실행
- [adapter_runtime.py](adapter_runtime.py): bundle 기반 model adapter 실행
- [agent_registry.py](agent_registry.py): bot_type → agent factory 매핑
- [model_registry.py](model_registry.py): artifact/fingerprint metadata
- [state_serializer.py](state_serializer.py) / [state_serializer_support.py](state_serializer_support.py): frontend-friendly rich state 생성
- [canonical_action.py](canonical_action.py): legal action을 canonical_id/engine_action_index로 카탈로그화
- [canonical_state.py](canonical_state.py): adapter 입력용 canonical state 변환
- [action_translator.py](action_translator.py): action_index ↔ semantic 변환
- [contracts.py](contracts.py): schema_version 상수 및 envelope 헬퍼
- [replay_logger.py](replay_logger.py): 사람 친화적 replay 로그
- [ml_logger.py](ml_logger.py): ML용 transition JSONL (canonical_id_match 포함)
- [event_bus.py](event_bus.py) / [ws_manager.py](ws_manager.py) / [lobby_manager.py](lobby_manager.py): 실시간 fan-out
- [scenario_regression.py](scenario_regression.py): known-bad scenario 자동 검증
- [startup_cleanup.py](startup_cleanup.py): 진행 중 게임 정리

## 의존성

- inbound: [../api/README.md](../api/README.md)
- outbound: [../db/README.md](../db/README.md), [../engine_wrapper/README.md](../engine_wrapper/README.md), [engine_gateway/README.md](engine_gateway/README.md), Redis, file logs

## 설계 메모

- `PuCo_RL` 직접 import는 `engine_gateway`나 wrapper로 수렴시키는 것이 원칙입니다.
- 새 도메인 로직은 `game_service.py`에만 계속 키우기보다 support/helper 파일로 분리하는 편이 낫습니다.
