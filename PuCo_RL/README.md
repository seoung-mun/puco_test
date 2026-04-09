# PuCo_RL

`PuCo_RL/`은 Castone이 참조하는 canonical Puerto Rico 엔진 서브트리입니다. 게임 규칙, env/action mask, agent 구현, 학습/평가 스크립트가 여기 있습니다.

## 하위 문서

- [agents/README.md](agents/README.md)
- [configs/README.md](configs/README.md)
- [env/README.md](env/README.md)
- [evaluate/README.md](evaluate/README.md)
- [tests/README.md](tests/README.md)
- [train/README.md](train/README.md)
- [utils/README.md](utils/README.md)
- [web/README.md](web/README.md)
- [models/README.md](models/README.md)
- [logs/README.md](logs/README.md)
- [runs/README.md](runs/README.md)
- [extract_documents/README.md](extract_documents/README.md)

## Castone에서의 역할

- backend가 step을 위임하는 실제 규칙 엔진
- action mask와 observation shape의 원천
- heuristic/PPO agent 구현 저장소
- offline league, benchmark, replay 분석 스크립트 저장소

## 현재 중요한 계약

- `env/pr_env.py`의 action space가 frontend/backend와 맞아야 합니다.
- Mayor는 strategy-first band `69-71`을 사용합니다.
- backend는 이 폴더를 직접 넓게 import하지 않고, `backend/app/services/engine_gateway`를 통해 접근하는 것이 원칙입니다.

## 런타임 흐름

1. [env/engine.py](env/engine.py)가 순수 게임 상태 머신을 구현합니다.
2. [env/pr_env.py](env/pr_env.py)가 PettingZoo/Gym-style env와 action mask를 제공합니다.
3. [agents/README.md](agents/README.md)의 agent들이 mask 기반으로 action을 선택합니다.
4. [evaluate/README.md](evaluate/README.md)와 [train/README.md](train/README.md)가 학습/평가 루프를 돌립니다.

## 의존성

- 상위 문서: [../README.md](../README.md)
- backend bridge: [../backend/app/services/engine_gateway/README.md](../backend/app/services/engine_gateway/README.md)
- frontend contract consumer: [../frontend/README.md](../frontend/README.md)

## 변경 시 체크

- action mapping이나 serializer에 영향 주는 변경은 backend/frontend 문서와 테스트를 같이 갱신합니다.
- upstream 동기화와 local delta는 분리해서 관리하는 편이 좋습니다.
