from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.as_channel_factory import resolve_as_ports
from app.infrastructure.channels.mock_cafe24 import MockCafe24Adapter


@pytest.mark.asyncio
async def test_resolve_ports_uses_mock_when_not_connected(monkeypatch):
    session = MagicMock()

    async def no_conn(*a, **k):
        return None

    monkeypatch.setattr(
        "app.application.as_channel_factory.commerce_service.get_connection",
        no_conn,
    )
    orders, mutations = await resolve_as_ports(session, "unknown_mall")
    assert isinstance(orders, MockCafe24Adapter)
    assert isinstance(mutations, MockCafe24Adapter)
    order = await orders.get_order("ORD-NORMAL")
    assert order is not None


@pytest.mark.asyncio
async def test_live_mutation_no_mock_fallback_when_connected(monkeypatch):
    session = MagicMock()
    conn = MagicMock()
    conn.status = "connected"
    conn.cafe24_mall_id = "c24mall"
    conn.access_token_encrypted = "x"

    async def get_conn(*a, **k):
        return conn

    async def no_token(*a, **k):
        return None

    monkeypatch.setattr(
        "app.application.as_channel_factory.commerce_service.get_connection",
        get_conn,
    )
    monkeypatch.setattr(
        "app.application.as_channel_factory.commerce_service._ensure_valid_access_token",
        no_token,
    )
    _orders, mutations = await resolve_as_ports(session, "live_mall")
    ok = await mutations.cancel_order("20261028-0000012", "변심", "k1")
    assert ok is False
