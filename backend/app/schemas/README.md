# backend/app/schemas

이 폴더는 API request/response payload의 명시적 타입 경계입니다.

## 주요 파일

- [auth.py](auth.py): auth 관련 payload
- [game.py](game.py): room/game/lobby 관련 payload (`ActionRequestPayload` 포함)
- [playback.py](playback.py): 배속/일시정지 컨트롤 payload
- [replay.py](replay.py): 리플레이 목록/상세 응답 shape

## 의존성

- inbound: [../api/README.md](../api/README.md)
- outbound: FastAPI/Pydantic serialization

## 계약 메모

- `ActionRequestPayload`는 `extra="forbid"`이며 supported 키는 `schema_version`, `action_index` (필수), `canonical_id` (선택)다.
- `canonical_id`가 디코드 결과와 다르면 channel router가 422 + `canonical_id_mismatch` detail을 반환한다.
- payload shape 변경 시 `contract.md` §2.5/§4.4와 frontend 타입을 같이 갱신한다.

## 변경 시 체크

- frontend가 소비하는 shape와 이름이 바뀌면 channel API와 함께 문서화합니다.
- domain object 전체를 노출하기보다 API contract에 맞는 shape만 둡니다.
