from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class CachePort(ABC):
    """Abstract port for key-value caching and rate limiting."""

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        pass

    @abstractmethod
    async def set(self, key: str, value: str, expire_seconds: Optional[int] = None) -> bool:
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        pass
