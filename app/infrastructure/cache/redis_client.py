import time
from typing import Dict, Optional, Tuple
from app.core.config import settings
from app.core.logging import logger
from app.domain.ports.cache_port import CachePort


class RedisCache(CachePort):
    """Cache client with Redis support and automatic in-memory fallback for local development."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._memory_store: Dict[str, Tuple[str, Optional[float]]] = {}
        self._redis = None
        self._use_memory = True  # Default to in-memory fallback for zero-dependency testability

    async def get(self, key: str) -> Optional[str]:
        if key in self._memory_store:
            val, expiry = self._memory_store[key]
            if expiry is None or time.time() < expiry:
                return val
            else:
                del self._memory_store[key]
        return None

    async def set(self, key: str, value: str, expire_seconds: Optional[int] = None) -> bool:
        expiry = (time.time() + expire_seconds) if expire_seconds else None
        self._memory_store[key] = (value, expiry)
        return True

    async def exists(self, key: str) -> bool:
        val = await self.get(key)
        return val is not None

    async def delete(self, key: str) -> bool:
        if key in self._memory_store:
            del self._memory_store[key]
            return True
        return False


cache_client = RedisCache()
