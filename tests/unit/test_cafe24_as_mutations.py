from unittest.mock import AsyncMock, patch

import pytest

from app.domain.orders.models import Order, OrderChannel, OrderItem, OrderStatus
from app.infrastructure.channels.cafe24 import Cafe24Adapter, build_order_from_payload


def test_build_order_prefers_order_item_code():
    order = build_order_from_payload(
        "20261028-0000012",
        "mall",
        {
            "order_status": "N",
            "items": [
                {
                    "order_item_code": "20261028-0000012-01",
                    "product_no": 991,
                    "product_name": "세럼",
                    "quantity": 1,
                    "product_price": 1000,
                }
            ],
        },
    )
    assert order.items[0].item_id == "20261028-0000012-01"
    assert order.items[0].product_no == "991"


@pytest.mark.asyncio
async def test_cancel_posts_cancellation_endpoint():
    adapter = Cafe24Adapter(mall_id="demo", access_token="tok")
    fake_order = Order(
        order_id="20261028-0000012",
        customer_id="g",
        mall_id="demo",
        status=OrderStatus.PAID,
        items=[
            OrderItem(
                item_id="20261028-0000012-01",
                product_name="세럼",
                quantity=1,
                unit_price=1000,
                product_no="991",
            )
        ],
        channel=OrderChannel.CAFE24,
    )

    class FakeResp:
        status_code = 201
        text = "{}"

    captured = {}

    async def fake_post(path, body, idempotency_key=None):
        captured["path"] = path
        captured["body"] = body
        captured["key"] = idempotency_key
        return FakeResp()

    with patch.object(adapter, "get_order", AsyncMock(return_value=fake_order)):
        with patch.object(adapter, "_post_json", AsyncMock(side_effect=fake_post)):
            ok = await adapter.cancel_order("20261028-0000012", "변심", "idemp-1")
    assert ok is True
    assert captured["path"] == "/cancellation"
    assert captured["body"]["order_id"] == "20261028-0000012"
    assert captured["body"]["items"][0]["order_item_code"] == "20261028-0000012-01"


@pytest.mark.asyncio
async def test_return_posts_accepted_status():
    adapter = Cafe24Adapter(mall_id="demo", access_token="tok")

    class FakeResp:
        status_code = 201
        text = "{}"

    captured = {}

    async def fake_post(path, body, idempotency_key=None):
        captured["path"] = path
        captured["body"] = body
        return FakeResp()

    with patch.object(adapter, "_post_json", AsyncMock(side_effect=fake_post)):
        ok = await adapter.request_partial_return(
            "20261028-0000012",
            ["20261028-0000012-01"],
            {"20261028-0000012-01": 1},
            "불량",
            "idemp-2",
        )
    assert ok is True
    assert captured["path"] == "/return"
    assert captured["body"]["status"] == "accepted"


@pytest.mark.asyncio
async def test_exchange_requires_product_no():
    adapter = Cafe24Adapter(mall_id="demo", access_token="tok")
    fake_order = Order(
        order_id="20261028-0000012",
        customer_id="g",
        mall_id="demo",
        status=OrderStatus.DELIVERED,
        items=[
            OrderItem(
                item_id="LINE-1",
                product_name="세럼",
                quantity=1,
                unit_price=1000,
                product_no="",  # missing
            )
        ],
        channel=OrderChannel.CAFE24,
    )
    with patch.object(adapter, "get_order", AsyncMock(return_value=fake_order)):
        ok = await adapter.request_exchange(
            "20261028-0000012", ["LINE-1"], "L사이즈", "사이즈", "idemp-3"
        )
    assert ok is False
