"""Pick Mock vs live Cafe24 adapters from the mall's OAuth connection.

When the store has entered Cafe24 API keys and completed OAuth (connected),
AS order lookup + cancel/return/exchange hit the real Admin API.
Otherwise showroom/test malls keep using MockCafe24Adapter (ORD-*).
"""
from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.commerce_service import commerce_service
from app.core.logging import logger
from app.domain.orders.models import Order
from app.domain.ports.channel_port import AsMutationPort, OrderChannelPort
from app.infrastructure.channels.cafe24 import (
    Cafe24Adapter,
    Cafe24AuthError,
    Cafe24RateLimited,
    Cafe24TransientError,
)
from app.infrastructure.channels.mock_cafe24 import MockCafe24Adapter
from app.core.security import decrypt_secret


class _CommerceOrderPort(OrderChannelPort):
    """Order read via commerce_service.lookup_order (token refresh included)."""

    def __init__(self, session: AsyncSession, mall_id: str, mock: MockCafe24Adapter):
        self._session = session
        self._mall_id = mall_id
        self._mock = mock

    async def get_order(self, order_id: str) -> Optional[Order]:
        order, _err = await commerce_service.lookup_order(
            self._session, self._mall_id, order_id
        )
        if order is not None:
            return order
        conn = await commerce_service.get_connection(self._session, self._mall_id)
        has_live = conn is not None and conn.status in ("connected", "refresh_expired")
        # Same rule as chat: never serve ORD-* mocks to a connected mall
        if has_live:
            return None
        return await self._mock.get_order(order_id)


class _LiveAsMutationPort(AsMutationPort):
    """Mutations with fresh access token; auth failure → one refresh retry."""

    def __init__(self, session: AsyncSession, mall_id: str, mock: MockCafe24Adapter):
        self._session = session
        self._mall_id = mall_id
        self._mock = mock

    async def _live_adapter(self) -> Optional[Cafe24Adapter]:
        conn = await commerce_service.get_connection(self._session, self._mall_id)
        if conn is None or conn.status not in ("connected", "refresh_expired"):
            return None
        if not conn.cafe24_mall_id:
            return None
        access = await commerce_service._ensure_valid_access_token(self._session, conn)
        if not access:
            return None
        return Cafe24Adapter(mall_id=conn.cafe24_mall_id, access_token=access)

    async def _with_retry(self, op_name: str, call):
        adapter = await self._live_adapter()
        if adapter is None:
            conn = await commerce_service.get_connection(self._session, self._mall_id)
            # Connected mall must not silently hit Mock mutations
            if conn is not None and conn.status in ("connected", "refresh_expired"):
                logger.warning(
                    f"[AS] live token unavailable for {op_name} mall={self._mall_id}"
                )
                return False
            return await call(self._mock)
        try:
            return await call(adapter)
        except Cafe24AuthError:
            conn = await commerce_service.get_connection(self._session, self._mall_id)
            if conn and await commerce_service.refresh_access_token(self._session, conn):
                access = decrypt_secret(conn.access_token_encrypted)
                adapter2 = Cafe24Adapter(
                    mall_id=conn.cafe24_mall_id, access_token=access
                )
                return await call(adapter2)
            logger.warning(f"[AS] Cafe24 auth failed for {op_name} mall={self._mall_id}")
            return False
        except (Cafe24TransientError, Cafe24RateLimited) as e:
            logger.warning(f"[AS] Cafe24 {op_name} transient: {e}")
            return False

    async def cancel_order(
        self, order_id: str, reason: str, idempotency_key: str
    ) -> bool:
        return await self._with_retry(
            "cancel",
            lambda a: a.cancel_order(order_id, reason, idempotency_key),
        )

    async def request_exchange(
        self,
        order_id: str,
        line_ids: list,
        exchange_option: str,
        reason: str,
        idempotency_key: str,
    ) -> bool:
        return await self._with_retry(
            "exchange",
            lambda a: a.request_exchange(
                order_id, line_ids, exchange_option, reason, idempotency_key
            ),
        )

    async def request_partial_return(
        self,
        order_id: str,
        line_ids: list,
        quantities: dict,
        reason: str,
        idempotency_key: str,
    ) -> bool:
        return await self._with_retry(
            "return",
            lambda a: a.request_partial_return(
                order_id, line_ids, quantities, reason, idempotency_key
            ),
        )


async def resolve_as_ports(
    session: AsyncSession, mall_id: str
) -> Tuple[OrderChannelPort, AsMutationPort]:
    """Return (order_port, mutation_port) for this mall."""
    mock = MockCafe24Adapter()
    conn = await commerce_service.get_connection(session, mall_id)
    if conn is None or conn.status == "pending":
        return mock, mock
    # connected or refresh_expired → try live (refresh_expired still attempts ensure token)
    return (
        _CommerceOrderPort(session, mall_id, mock),
        _LiveAsMutationPort(session, mall_id, mock),
    )
