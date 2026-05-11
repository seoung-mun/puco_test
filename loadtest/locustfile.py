from __future__ import annotations

import itertools
import json
import os
import random
import time
from pathlib import Path

from locust import HttpUser, between, task


DEFAULT_TOKENS_FILES = (
    Path(__file__).with_name("tokens.json"),
    Path(__file__).resolve().parents[1] / "backend" / "loadtest_tokens.json",
)


def resolve_tokens_file() -> Path:
    env_value = os.getenv("LOADTEST_TOKENS_FILE")
    if env_value:
        return Path(env_value).resolve()
    for candidate in DEFAULT_TOKENS_FILES:
        if candidate.exists():
            return candidate
    return DEFAULT_TOKENS_FILES[0]


class LobbyUser(HttpUser):
    wait_time = between(0.5, 1.5)

    _tokens: list[dict[str, str]] | None = None
    _user_counter = itertools.count()

    @classmethod
    def load_tokens(cls) -> list[dict[str, str]]:
        if cls._tokens is None:
            tokens_file = resolve_tokens_file()
            cls._tokens = json.loads(tokens_file.read_text(encoding="utf-8"))
            if not cls._tokens:
                raise RuntimeError(f"No tokens found in {tokens_file}")
        return cls._tokens

    def on_start(self) -> None:
        tokens = self.load_tokens()
        slot = next(self._user_counter) % len(tokens)
        identity = tokens[slot]
        self.nickname = identity["nickname"]
        self.headers = {"Authorization": f"Bearer {identity['token']}"}
        self._cleanup_waiting_room()

    def on_stop(self) -> None:
        self._cleanup_waiting_room()

    def _cleanup_waiting_room(self) -> None:
        active = self.client.get(
            "/api/puco/session/active-game",
            headers=self.headers,
            name="/api/puco/session/active-game",
        )
        if not active.ok:
            return
        payload = active.json()
        if payload.get("has_active_game") and payload.get("status") == "WAITING":
            room_id = payload.get("game_id")
            self.client.post(
                f"/api/puco/rooms/{room_id}/leave",
                headers=self.headers,
                name="/api/puco/rooms/[id]/leave",
            )

    @task(5)
    def list_rooms(self) -> None:
        self.client.get(
            "/api/puco/rooms/",
            headers=self.headers,
            name="/api/puco/rooms/",
        )

    @task(3)
    def active_game(self) -> None:
        self.client.get(
            "/api/puco/session/active-game",
            headers=self.headers,
            name="/api/puco/session/active-game",
        )

    @task(2)
    def bot_types(self) -> None:
        self.client.get("/api/bot-types", name="/api/bot-types")

    @task(1)
    def create_and_leave_room(self) -> None:
        self._cleanup_waiting_room()
        short_name = self.nickname[:8]
        short_ts = int(time.time() * 1000) % 100000
        title = f"lt-{short_name}-{short_ts}-{random.randint(10, 99)}"

        with self.client.post(
            "/api/puco/rooms/",
            headers=self.headers,
            json={"title": title, "is_private": False},
            name="/api/puco/rooms/ (create)",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"unexpected status={response.status_code} body={response.text[:200]}")
                return

            room_id = response.json()["id"]
            leave = self.client.post(
                f"/api/puco/rooms/{room_id}/leave",
                headers=self.headers,
                name="/api/puco/rooms/[id]/leave",
            )
            if not leave.ok:
                response.failure(
                    f"leave failed status={leave.status_code} body={leave.text[:200]}"
                )
