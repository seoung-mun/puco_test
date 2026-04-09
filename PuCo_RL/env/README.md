# PuCo_RL/env

게임 규칙과 env contract의 핵심 폴더입니다.

## 주요 파일

- [engine.py](engine.py): `PuertoRicoGame` 상태 머신
- [pr_env.py](pr_env.py): `PuertoRicoEnv` PettingZoo/Gym wrapper
- [player.py](player.py): 플레이어 보드와 자원 상태
- [components.py](components.py): `CargoShip` 등 보조 데이터 구조

## 역할

- 역할 선택, phase 전이, 점수 계산, 종료 조건 처리
- 유효 action mask 계산
- observation/action space 정의
- 자동 진행 가능한 하위 phase 처리

## 중요한 계약

- action space `0-199`
- Mayor strategy `69-71`
- Captain/Trader/Craftsman/Hacienda 등의 phase-specific rule 처리

## 의존성

- outbound: [../configs/README.md](../configs/README.md)
- inbound: [../agents/README.md](../agents/README.md), [../../backend/app/engine_wrapper/README.md](../../backend/app/engine_wrapper/README.md)
