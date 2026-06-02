from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.security import create_access_token
from app.db.models import GameSession, User
from app.dependencies import SessionLocal


def upsert_loadtest_users(count: int) -> list[dict[str, str]]:
    payloads: list[dict[str, str]] = []

    with SessionLocal() as db:
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

        user_ids = [str(user.id) for user in users]
        (
            db.query(GameSession)
            .filter(GameSession.status == "WAITING", GameSession.host_id.in_(user_ids))
            .delete(synchronize_session=False)
        )
        db.commit()

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
    parser = argparse.ArgumentParser(description="Prepare backend-local users and JWTs for load testing.")
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--output", default="/app/loadtest_tokens.json")
    args = parser.parse_args()

    payloads = upsert_loadtest_users(count=args.count)
    output_path = Path(args.output)
    output_path.write_text(json.dumps(payloads, indent=2), encoding="utf-8")
    print(json.dumps({"created_users": len(payloads), "output": str(output_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
