"""
EventBus — asyncio.Queue 기반 인메모리 Pub/Sub.

단일 프로세스(uvicorn single worker) 환경 전용.
멀티 프로세스가 필요해지면 Redis Pub/Sub으로 교체.
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, List
from dataclasses import dataclass


@dataclass
class _Event:
    type: str
    data: str


class EventBus:
    def __init__(self):
        # session_key -> list of subscriber queues
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

    @asynccontextmanager
    async def subscribe(self, key: str) -> AsyncGenerator[asyncio.Queue, None]:
        """주어진 key의 이벤트를 수신할 Queue를 반환하는 context manager."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(key, []).append(queue)
        try:
            yield queue
        finally:
            self._subscribers[key].remove(queue)
            if not self._subscribers[key]:
                del self._subscribers[key]

    async def publish(self, key: str, event_type: str, data: str) -> None:
        """key를 구독 중인 모든 subscriber에게 이벤트를 전달."""
        event = {"type": event_type, "data": data}
        for queue in self._subscribers.get(key, []):
            await queue.put(event)

    def subscriber_count(self, key: str) -> int:
        return len(self._subscribers.get(key, []))


# 모듈 수준 싱글턴
event_bus = EventBus()
