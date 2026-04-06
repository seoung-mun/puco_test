"""
TDD: EventBus (asyncio.Queue 기반 인메모리 Pub/Sub)

RED phase: EventBus가 없으므로 모든 테스트 실패 예상.
"""
import asyncio
import os, sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_event_bus.db")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../PuCo_RL")))

import pytest
from app.services.event_bus import EventBus


# ================================================================== #
#  Feature 1: publish → subscriber가 이벤트를 받는다                   #
# ================================================================== #

class TestEventBusBasic:

    @pytest.mark.anyio
    async def test_subscriber_receives_published_event(self):
        """publish 후 subscriber는 같은 key의 이벤트를 받는다."""
        bus = EventBus()
        received = []

        async with bus.subscribe("room-abc") as queue:
            await bus.publish("room-abc", "state_update", '{"meta": {}}')
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            received.append(event)

        assert len(received) == 1
        assert received[0]["type"] == "state_update"
        assert received[0]["data"] == '{"meta": {}}'

    @pytest.mark.anyio
    async def test_different_key_does_not_receive_event(self):
        """다른 key로 publish한 이벤트는 받지 않는다."""
        bus = EventBus()

        async with bus.subscribe("room-abc") as queue:
            await bus.publish("room-xyz", "state_update", '{"meta": {}}')
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(queue.get(), timeout=0.1)

    @pytest.mark.anyio
    async def test_multiple_subscribers_same_key_all_receive(self):
        """같은 key에 구독자가 2명이면 둘 다 이벤트를 받는다."""
        bus = EventBus()
        results = []

        async with bus.subscribe("room-abc") as q1:
            async with bus.subscribe("room-abc") as q2:
                await bus.publish("room-abc", "lobby_update", '[]')
                e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
                e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
                results.extend([e1, e2])

        assert len(results) == 2
        assert all(r["type"] == "lobby_update" for r in results)

    @pytest.mark.anyio
    async def test_unsubscribed_queue_removed(self):
        """context manager 종료 후 구독자가 제거된다."""
        bus = EventBus()

        async with bus.subscribe("room-abc"):
            assert bus.subscriber_count("room-abc") == 1

        assert bus.subscriber_count("room-abc") == 0


# ================================================================== #
#  Feature 2: 이벤트 타입 필드가 정확히 포함된다                        #
# ================================================================== #

class TestEventBusEventShape:

    @pytest.mark.anyio
    async def test_event_has_type_and_data_fields(self):
        """이벤트 dict에 type, data 키가 있다."""
        bus = EventBus()

        async with bus.subscribe("room-1") as queue:
            await bus.publish("room-1", "ping", "{}")
            event = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert "type" in event
        assert "data" in event

    @pytest.mark.anyio
    async def test_publish_lobby_update_event_type(self):
        """lobby_update 타입으로 publish하면 type 필드가 lobby_update다."""
        bus = EventBus()

        async with bus.subscribe("room-1") as queue:
            await bus.publish("room-1", "lobby_update", '{"players": []}')
            event = await asyncio.wait_for(queue.get(), timeout=1.0)

        assert event["type"] == "lobby_update"
