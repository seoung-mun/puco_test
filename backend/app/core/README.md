# backend/app/core

이 폴더는 런타임 공통 인프라 유틸리티를 담습니다.

## 주요 파일

- [env_secrets.py](env_secrets.py): 환경 변수/시크릿 bootstrap
- [redis.py](redis.py): sync/async Redis client
- [security.py](security.py): JWT, auth helper

## 의존성

- inbound: [../api/README.md](../api/README.md), [../services/README.md](../services/README.md), [../dependencies.py](../dependencies.py)
- outbound: Redis, JWT/Google auth 설정

## 변경 시 체크

- framework 전역 설정과 비즈니스 로직을 섞지 않습니다.
- Redis key shape 변경은 ws/lobby/state sync 경로를 함께 확인합니다.
