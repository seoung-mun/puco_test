# backend/app/schemas

이 폴더는 API request/response payload의 명시적 타입 경계입니다.

## 주요 파일

- [auth.py](auth.py): auth 관련 payload
- [game.py](game.py): room/game/lobby 관련 payload

## 의존성

- inbound: [../api/README.md](../api/README.md)
- outbound: FastAPI/Pydantic serialization

## 변경 시 체크

- frontend가 소비하는 shape와 이름이 바뀌면 channel API와 함께 문서화합니다.
- domain object 전체를 노출하기보다 API contract에 맞는 shape만 둡니다.
