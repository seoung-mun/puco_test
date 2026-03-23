import os
import redis
import redis.asyncio as async_redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Sync client — used by game_service.py (sync SQLAlchemy context)
sync_redis_client = redis.from_url(REDIS_URL)

# Async client — used by ws_manager.py (async WebSocket context)
async_redis_client = async_redis.from_url(REDIS_URL)
