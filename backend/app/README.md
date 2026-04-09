# backend/app

`backend/app`은 서버 런타임의 실제 애플리케이션 패키지입니다.

## 하위 문서

- [api/README.md](api/README.md)
- [core/README.md](core/README.md)
- [db/README.md](db/README.md)
- [engine_wrapper/README.md](engine_wrapper/README.md)
- [schemas/README.md](schemas/README.md)
- [services/README.md](services/README.md)
- [game/README.md](game/README.md)

## 구조 요약

- [main.py](main.py): FastAPI 앱 진입점
- [dependencies.py](dependencies.py): DB 세션과 공용 의존성
- `api/`: HTTP/WebSocket boundary
- `services/`: 게임 진행과 로그 저장의 orchestration
- `engine_wrapper/`: backend 친화적인 env wrapper
- `db/`: SQLAlchemy 모델

## 의존성

- 상위 문서: [../README.md](../README.md)
- 외부 엔진: [../../PuCo_RL/README.md](../../PuCo_RL/README.md)

## 변경 시 체크

- 새 runtime dependency는 `main.py`가 아니라 `core/` 또는 `dependencies.py`에 수렴시키는 편이 좋습니다.
- 도메인 규칙 변경은 먼저 `services/`와 `engine_gateway` 경계를 통해 반영합니다.
