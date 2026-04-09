# backend/app/api/legacy

이 폴더는 이전 API surface와 호환성을 유지하기 위한 경계입니다.

## 역할

- 구 프론트/스크립트/운영 도구가 아직 기대하는 REST 경로 제공
- channel contract로 완전히 이관되지 않은 읽기/보조 흐름 유지
- `X-API-Key` 기반 내부 호출 호환

## 주요 파일

- [actions.py](actions.py): legacy write endpoint
- [game.py](game.py): legacy game 조회/흐름
- [lobby.py](lobby.py): legacy lobby endpoint
- [events.py](events.py): 이벤트 관련 bridge
- [deps.py](deps.py): legacy auth/dependency
- [schemas.py](schemas.py): legacy payload

## 의존성

- outbound: [../../services/README.md](../../services/README.md), [../../schemas/README.md](../../schemas/README.md)
- 상위 문서: [../README.md](../README.md)

## 운영 메모

- 새 기능의 기본 추가 위치는 아닙니다.
- 실제 사용자 경로가 `channel`로 고정된 기능은 여기서 더 확장하지 않는 편이 안전합니다.
