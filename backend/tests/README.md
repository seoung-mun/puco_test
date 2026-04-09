# backend/tests

이 폴더는 backend contract와 회귀를 보호하는 테스트 스위트입니다.

## 테스트 축

- API/auth/lobby/WebSocket contract
- `game_service` turn validation과 multiplayer 흐름
- serializer/action index contract
- replay/ml logger/model registry metadata
- scenario regression harness
- import guard와 serving wrapper safety

## 참고 문서

- 상위 문서: [../README.md](../README.md)
- 서비스 구조: [../app/services/README.md](../app/services/README.md)
- 엔진 경계: [../app/services/engine_gateway/README.md](../app/services/engine_gateway/README.md)

## 새 테스트를 추가할 때

- 단순 import 존재 확인보다 실제 규칙/예외 상황을 검증하는 쪽을 우선합니다.
- `PuCo_RL` 직접 import를 테스트에서 새로 늘리기보다 backend 공개 contract를 통해 검증합니다.
- scenario성 회귀는 fixture보다 서술적인 테스트 이름으로 남기는 편이 좋습니다.
