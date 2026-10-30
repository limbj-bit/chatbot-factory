from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from app.domain.orders.models import Order


class OrderChannelPort(ABC):
    """Abstract port for querying order information from e-commerce platforms."""

    @abstractmethod
    async def get_order(self, order_id: str) -> Optional[Order]:
        """Fetch order details by order_id."""
        pass


class ClaimChannelPort(ABC):
    """Abstract port for executing return/refund mutations on e-commerce platforms."""

    @abstractmethod
    async def register_return_request(
        self,
        order_id: str,
        reason: str,
        claim_id: str,
        idempotency_key: str,
    ) -> bool:
        """Submit return/refund request to e-commerce platform."""
        pass


class AsMutationPort(ABC):
    """Cancel / exchange / partial-return. Real Cafe24 API fills this in later."""

    @abstractmethod
    async def cancel_order(
        self, order_id: str, reason: str, idempotency_key: str
    ) -> bool:
        pass

    @abstractmethod
    async def request_exchange(
        self,
        order_id: str,
        line_ids: List[str],
        exchange_option: str,
        reason: str,
        idempotency_key: str,
    ) -> bool:
        pass

    @abstractmethod
    async def request_partial_return(
        self,
        order_id: str,
        line_ids: List[str],
        quantities: Dict[str, int],
        reason: str,
        idempotency_key: str,
    ) -> bool:
        pass
