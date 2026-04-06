"""
SSE 엔드포인트 — GET /events/stream

클라이언트는 이 엔드포인트를 구독하면 게임/로비 상태 변화를
서버 푸시(text/event-stream)로 수신한다.

이벤트 종류:
  state_update  — 게임 상태 변화 (GameState JSON)
  lobby_update  — 로비 플레이어 목록 변화
  ping          — 30초 keep-alive
"""
import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.session_manager import session
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)
router = APIRouter()

_PING_INTERVAL = 30.0  # seconds


async def _event_generator(key: str) -> AsyncGenerator[str, None]:
    """SSE 포맷 이벤트를 yield하는 async generator."""
    async with event_bus.subscribe(key) as queue:
        # 연결 확인용 즉시 ping (클라이언트 연결 감지 + 테스트 블로킹 방지)
        yield "event: ping\ndata: {}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_PING_INTERVAL)
                yield f"event: {event['type']}\ndata: {event['data']}\n\n"
            except asyncio.TimeoutError:
                yield "event: ping\ndata: {}\n\n"


@router.get("/events/stream")
async def sse_stream(key: str, name: str):
    """
    SSE 스트림 연결.
    key: 세션 키
    name: 플레이어 이름 (로깅/검증용)
    """
    if session.lobby_key != key:
        raise HTTPException(status_code=403, detail="Invalid session key")

    return StreamingResponse(
        _event_generator(key),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx proxy buffering 비활성화
        },
    )
