# backend/app/services/engine_gateway

이 폴더는 backend에서 `PuCo_RL`에 접근할 때 사용하는 유일한 집합점입니다.

## 역할

- engine/env/constants/agent import를 한곳으로 수렴
- `sys.path` bootstrap과 canonical upstream 경계 고정
- backend 서비스가 `PuCo_RL` 내부 경로를 직접 import하지 않게 보호

## 주요 파일

- [factory.py](factory.py): canonical `create_game_engine()` entrypoint
- [bootstrap.py](bootstrap.py): path bootstrap
- [constants.py](constants.py): 엔진 상수 re-export
- [env.py](env.py): env type re-export
- [agents.py](agents.py): agent registry/adapter import bridge
- [__init__.py](__init__.py): lazy export로 circular import 방지

## 의존성

- inbound: [../game_service.py](../game_service.py), [../../engine_wrapper/wrapper.py](../../engine_wrapper/wrapper.py), import-guard 테스트
- outbound: [../../../../PuCo_RL/README.md](../../../../PuCo_RL/README.md)

## 변경 시 체크

- 새 `PuCo_RL` 의존성이 필요하면 먼저 여기로 끌어옵니다.
- lazy import를 깨면 backend startup 또는 smoke path에서 circular import가 다시 생길 수 있습니다.
