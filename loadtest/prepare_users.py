from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def build_local_database_url(env_values: dict[str, str]) -> str:
    username = env_values["POSTGRES_USER"]
    password = env_values["POSTGRES_PASSWORD"]
    database = "puco_rl"
    return str(
        URL.create(
            drivername="postgresql+psycopg2",
            username=username,
            password=password,
            host="127.0.0.1",
            port=5432,
            database=database,
        )
    )


def ensure_runtime_secrets(env_values: dict[str, str]) -> None:
    for key in ("SECRET_KEY", "INTERNAL_API_KEY"):
        value = env_values.get(key)
        if value:
            os.environ[key] = value


def upsert_loadtest_users(db: Session, count: int) -> list[dict[str, str]]:
    from app.core.security import create_access_token
    from app.db.models import GameSession, User

    users: list[User] = []

    for index in range(1, count + 1):
        google_id = f"loadtest-google-{index}"
        email = f"loadtest{index}@example.com"
        nickname = f"loadtest{index}"

        user = db.query(User).filter(User.google_id == google_id).first()
        if user is None:
            user = User(
                google_id=google_id,
                email=email,
                nickname=nickname,
            )
            db.add(user)
        else:
            user.email = email
            user.nickname = nickname

        users.append(user)

    db.commit()

    # Remove stale waiting rooms so each run starts cleanly for room-create tasks.
    user_ids = [str(user.id) for user in users]
    (
        db.query(GameSession)
        .filter(GameSession.status == "WAITING", GameSession.host_id.in_(user_ids))
        .delete(synchronize_session=False)
    )
    db.commit()

    payloads: list[dict[str, str]] = []
    for user in users:
        db.refresh(user)
        payloads.append(
            {
                "user_id": str(user.id),
                "nickname": str(user.nickname),
                "token": create_access_token(subject=str(user.id)),
            }
        )

    return payloads


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare local load test users and JWT tokens.")
    parser.add_argument("--count", type=int, default=30, help="Number of users/tokens to generate.")
    parser.add_argument(
        "--env-file",
        default=str(ROOT / ".env"),
        help="Path to the environment file that contains DB credentials and secrets.",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "loadtest" / "tokens.json"),
        help="Where to write the generated token list.",
    )
    args = parser.parse_args()

    env_file = Path(args.env_file).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    env_values = parse_env_file(env_file)
    ensure_runtime_secrets(env_values)
    database_url = build_local_database_url(env_values)

    engine = create_engine(database_url, pool_pre_ping=True)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with session_local() as db:
        payloads = upsert_loadtest_users(db, count=args.count)

    output_path.write_text(json.dumps(payloads, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "created_users": len(payloads),
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
