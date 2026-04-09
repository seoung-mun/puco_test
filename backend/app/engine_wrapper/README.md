# backend/app/engine_wrapper

이 폴더는 backend 관점에서 `PuCo_RL` env를 감싸는 얇은 adapter입니다.

## 주요 파일

- [wrapper.py](wrapper.py): `EngineWrapper`, backend-friendly create/step/get_state API

## 역할

- `PuertoRicoEnv`를 backend 서비스가 쓰기 쉬운 객체로 노출
- state snapshot, action mask, info를 일관된 shape로 반환
- upstream env signature와 backend caller 사이의 호환 shim 제공

## 의존성

- inbound: [../services/game_service.py](../services/game_service.py), [../services/engine_gateway/README.md](../services/engine_gateway/README.md)
- outbound: [../../../PuCo_RL/env/README.md](../../../PuCo_RL/env/README.md)

## 변경 시 체크

- path bootstrap이나 env kwargs 처리는 여기 또는 `engine_gateway`에만 둡니다.
- service 레이어가 `PuCo_RL` 내부 타입을 직접 만지지 않도록 경계를 유지합니다.
