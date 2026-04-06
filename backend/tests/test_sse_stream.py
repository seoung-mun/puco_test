"""
TDD: /api/events/stream SSE 엔드포인트

테스트 전략:
- 헤더/응답 코드: TestClient stream 모드로 확인 (iterate 없이 즉시 종료)
- publish 동작: anyio + EventBus 직접 구독으로 검증 (SSE 스트림 iterate 블로킹 회피)
"""
import asyncio
import json
import os, sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sse.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.legacy import router as legacy_router
from app.services.session_manager import session as _session
from app.services.event_bus import event_bus


@pytest.fixture(autouse=True)
def reset_session():
    _session.reset()
    yield
    _session.reset()


@pytest.fixture()
def client_and_key():
    mini_app = FastAPI()
    mini_app.include_router(legacy_router, prefix="/api")
    with TestClient(mini_app) as c:
        api_key = os.getenv("INTERNAL_API_KEY", "")
        if api_key:
            c.headers.update({"X-API-Key": api_key})
        res = c.post("/api/multiplayer/init", json={"host_name": "Alice"})
        key = res.json()["session_key"]
        for i in range(2):
            c.post("/api/lobby/add-bot", json={
                "key": key, "host_name": "Alice",
                "bot_name": f"Bot{i+1}", "bot_type": "random",
            })
        yield c, key


# ================================================================== #
#  Feature 1: SSE 엔드포인트 기본 동작                               #
# ================================================================== #

class TestSSEEndpointExists:

    def test_invalid_key_returns_403(self, client_and_key):
        """잘못된 key로 접속하면 403 (스트림 시작 전 즉시 거부)."""
        client, _ = client_and_key
        resp = client.get("/api/events/stream?key=WRONG&name=Alice")
        assert resp.status_code == 403


# ================================================================== #
#  Feature 2: lobby/start 후 event_bus에 state_update가 발행된다       #
# (SSE 스트림 직접 iterate 대신 EventBus 구독으로 검증)                #
# ================================================================== #

class TestSSEPublishOnLobbyStart:

    @pytest.mark.anyio
    async def test_lobby_start_publishes_state_update_to_event_bus(self, client_and_key):
        """lobby/start 호출 후 event_bus에 state_update 이벤트가 발행된다."""
        client, key = client_and_key
        received = []

        async with event_bus.subscribe(key) as queue:
            # lobby/start는 async 엔드포인트이므로 TestClient 호출과 동시에 publish
            # TestClient가 동기 컨텍스트이므로 별도 태스크로 실행
            import anyio

            async def call_lobby_start():
                await anyio.to_thread.run_sync(
                    lambda: client.post("/api/lobby/start", json={"key": key, "name": "Alice"})
                )

            async with anyio.create_task_group() as tg:
                tg.start_soon(call_lobby_start)
                event = await asyncio.wait_for(queue.get(), timeout=5.0)
                received.append(event)

        assert len(received) >= 1
        assert received[0]["type"] == "state_update"

    @pytest.mark.anyio
    async def test_lobby_start_state_update_data_contains_meta(self, client_and_key):
        """state_update 이벤트의 data는 GameState(meta 포함) JSON이다."""
        client, key = client_and_key

        async with event_bus.subscribe(key) as queue:
            import anyio
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    anyio.to_thread.run_sync,
                    lambda: client.post("/api/lobby/start", json={"key": key, "name": "Alice"})
                )
                event = await asyncio.wait_for(queue.get(), timeout=5.0)

        data = json.loads(event["data"])
        assert "meta" in data, f"meta 키 없음: {list(data.keys())}"
        assert "phase" in data["meta"], "meta.phase 없음"

    @pytest.mark.anyio
    async def test_lobby_join_publishes_lobby_update(self):
        """lobby/join 후 event_bus에 lobby_update 이벤트가 발행된다."""
        _session.reset()
        mini_app = FastAPI()
        mini_app.include_router(legacy_router, prefix="/api")

        with TestClient(mini_app) as client:
            api_key = os.getenv("INTERNAL_API_KEY", "")
            if api_key:
                client.headers.update({"X-API-Key": api_key})
            res = client.post("/api/multiplayer/init", json={"host_name": "Alice"})
            key = res.json()["session_key"]

            import anyio
            async with event_bus.subscribe(key) as queue:
                async with anyio.create_task_group() as tg:
                    tg.start_soon(
                        anyio.to_thread.run_sync,
                        lambda: client.post("/api/lobby/join", json={"key": key, "name": "Bob"})
                    )
                    event = await asyncio.wait_for(queue.get(), timeout=3.0)

            assert event["type"] == "lobby_update"
