## Docker 밖의 PostgreSQL을 따로 쓰고 싶다면

현재 compose DB도 충분히 영속적이지만, 로컬 네이티브 Postgres나 별도 서버 DB를 쓰고 싶다면 아래 순서로 하면 됩니다.

### 1. DB와 계정 생성

예시 SQL:

```sql
CREATE USER puco_user WITH PASSWORD 'change-me-strong-db-password';
CREATE DATABASE puco_rl OWNER puco_user;
```

### 2. `DATABASE_URL` 변경

백엔드를 로컬 프로세스로 실행하면:

```bash
DATABASE_URL=postgresql://puco_user:change-me-strong-db-password@localhost:5432/puco_rl
```

백엔드는 Docker 안에서 돌리고 DB만 호스트에 두려면 macOS 기준:

```bash
DATABASE_URL=postgresql://puco_user:change-me-strong-db-password@host.docker.internal:5432/puco_rl
```

### 3. 마이그레이션 적용

```bash
cd backend
alembic upgrade head
```

이 단계가 끝나야 `users`, `games`, `game_logs` 같은 테이블이 만들어집니다.
