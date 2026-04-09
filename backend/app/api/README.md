# backend/app/api

이 폴더는 backend의 네트워크 경계입니다.

## 하위 문서

- [channel/README.md](channel/README.md)
- [legacy/README.md](legacy/README.md)
- [v1/README.md](v1/README.md)

## 역할

- 인증/인가 후 request를 service 호출로 변환
- REST와 WebSocket contract를 분리
- legacy compatibility surface를 현재 채널 경계와 분리 관리

## 주요 파일

- [deps.py](deps.py): 공용 API dependency
- [channel/](channel/): 현재 프론트가 주로 사용하는 경로
- [legacy/](legacy/): 호환용/이전 경로

## 의존성

- outbound: [../schemas/README.md](../schemas/README.md), [../services/README.md](../services/README.md), [../core/README.md](../core/README.md)

## 변경 시 체크

- 새 write endpoint가 필요한 경우 `channel` contract인지 `legacy` bridge인지 먼저 정합니다.
- action index나 serialized state를 직접 조합하지 말고 `services/`를 거쳐야 합니다.
