# backend/alembic

이 폴더는 backend의 데이터베이스 마이그레이션 경계입니다.

## 역할

- SQLAlchemy 모델 변경을 실제 DB 스키마 변경으로 연결
- `env.py`에서 `DATABASE_URL`과 metadata를 읽어 migration context 구성
- revision 파일을 순서대로 관리

## 주요 파일

- [env.py](env.py): Alembic 실행 컨텍스트
- [versions/README.md](versions/README.md): 개별 revision 설명
- [script.py.mako](script.py.mako): 새 revision 템플릿

## 의존성

- inbound: backend 배포/로컬 개발, 테스트 DB 초기화
- outbound: [app/db/README.md](../app/db/README.md), PostgreSQL

## 변경 시 체크

- 모델 필드 추가/삭제 시 revision을 먼저 만들고, 테스트 DB 경로도 같이 확인합니다.
- 운영 기록 테이블(`games`, `game_logs`, `users`) 변경은 replay/vis 흐름과 함께 검토합니다.
