import pytest
from app.domain.orders.models import OrderStatus
from app.infrastructure.channels.mock_cafe24 import MockCafe24Adapter


@pytest.mark.asyncio
async def test_mock_cafe24_order_lookup_delivered():
    adapter = MockCafe24Adapter()
    order = await adapter.get_order("ORD-NORMAL")
    assert order is not None
    assert order.order_id == "ORD-NORMAL"
    assert order.status == OrderStatus.DELIVERED
    assert len(order.items) == 1
    assert order.items[0].product_name == "설향 딸기 1kg (특등급)"
    assert order.total_amount == 24000
    assert order.is_delivered() is True


@pytest.mark.asyncio
async def test_mock_cafe24_order_lookup_shipping():
    adapter = MockCafe24Adapter()
    order = await adapter.get_order("ORD-SHIPPING")
    assert order is not None
    assert order.status == OrderStatus.SHIPPING
    assert order.is_delivered() is False


@pytest.mark.asyncio
async def test_mock_cafe24_order_lookup_not_found():
    adapter = MockCafe24Adapter()
    order = await adapter.get_order("INVALID_ORDER_ID")
    assert order is None


@pytest.mark.asyncio
async def test_mock_cafe24_return_registration_idempotency():
    adapter = MockCafe24Adapter()
    idempotency_key = "idemp-test-999"

    # First call
    success1 = await adapter.register_return_request(
        order_id="ORD-NORMAL",
        reason="Severe mold on strawberries",
        claim_id="CLM-001",
        idempotency_key=idempotency_key,
    )
    assert success1 is True

    # Duplicate call with same key should succeed without duplicate entries
    success2 = await adapter.register_return_request(
        order_id="ORD-NORMAL",
        reason="Severe mold on strawberries",
        claim_id="CLM-001",
        idempotency_key=idempotency_key,
    )
    assert success2 is True
    assert len(adapter._submitted_returns) == 1
