# backend/alembic/versions

이 폴더는 실제 적용 순서가 있는 Alembic revision 파일을 보관합니다.

## 현재 포함된 revision

- `001_initial_schema.py`: 초기 `users`, `games`, `game_logs` 스키마
- `002_add_user_email_created_at.py`: 사용자 메타데이터 확장
- `003_add_state_summary_to_game_logs.py`: 로그 조회용 요약 컬럼 추가
- `004_add_room_privacy.py`: 방 공개/비공개 관련 필드
- `005_add_host_id.py`: host 식별 필드
- `006_fix_title_unique_partial_index.py`: room title uniqueness 보정

## 의존성

- 상위 문서: [../README.md](../README.md)
- 모델 기준: [../../app/db/README.md](../../app/db/README.md)

## 운영 메모

- revision은 순서를 바꾸지 않습니다.
- 테스트용 SQLite와 운영 PostgreSQL 모두에서 의미가 맞는지 확인합니다.
