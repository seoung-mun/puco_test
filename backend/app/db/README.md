# backend/app/db

이 폴더는 backend의 정본 데이터 모델을 정의합니다.

## 주요 파일

- [models.py](models.py): `User`, `GameSession`, `GameLog`

## 역할

- 운영 게임 메타데이터와 액션 로그의 정규화 기준 제공
- Alembic migration의 source-of-truth 역할

## 의존성

- inbound: [../services/README.md](../services/README.md), [../../alembic/README.md](../../alembic/README.md), 테스트 스위트
- outbound: PostgreSQL/SQLite

## 변경 시 체크

- 새 필드 추가 시 Alembic revision과 테스트 fixture를 같이 갱신합니다.
- JSON 컬럼 shape를 바꾸면 `vis/`와 replay 분석 루트까지 같이 확인합니다.
