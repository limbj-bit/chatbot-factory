from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from app.domain.orders.models import Order, OrderChannel, OrderItem, OrderStatus
from app.domain.ports.channel_port import ClaimChannelPort, OrderChannelPort


class MockCafe24Adapter(OrderChannelPort, ClaimChannelPort):
    """Deterministic Mock Adapter for Cafe24 (and general e-commerce) channel operations."""

    def __init__(self):
        self._submitted_returns: Dict[str, dict] = {}

    async def get_order(self, order_id: str) -> Optional[Order]:
        now = datetime.now(timezone.utc)

        if order_id == "ORD-NORMAL" or order_id == "ORD-2026-NORMAL":
            return Order(
                order_id=order_id,
                customer_id="CUST-001",
                mall_id="demo_mall",
                status=OrderStatus.DELIVERED,
                items=[
                    OrderItem(
                        item_id="PROD-STRAWBERRY-01",
                        product_name="설향 딸기 1kg (특등급)",
                        quantity=1,
                        unit_price=24000,
                        category="fresh_food",
                    )
                ],
                total_amount=24000,
                channel=OrderChannel.CAFE24,
                paid_at=now - timedelta(days=2),
                delivered_at=now - timedelta(hours=8),
                shipping_code="CJ1234567890",
                carrier_name="CJ대한통운",
            )

        if order_id == "ORD-EXPIRED":
            return Order(
                order_id=order_id,
                customer_id="CUST-002",
                mall_id="demo_mall",
                status=OrderStatus.DELIVERED,
                items=[
                    OrderItem(
                        item_id="PROD-TOMATO-01",
                        product_name="대저 짭짤이 토마토 1kg",
                        quantity=1,
                        unit_price=16000,
                        category="fresh_food",
                    )
                ],
                total_amount=16000,
                channel=OrderChannel.CAFE24,
                paid_at=now - timedelta(days=6),
                delivered_at=now - timedelta(days=4),  # > 2 days (expired window)
                shipping_code="CJ9876543210",
                carrier_name="CJ대한통운",
            )

        if order_id == "ORD-SHIPPING":
            return Order(
                order_id=order_id,
                customer_id="CUST-003",
                mall_id="demo_mall",
                status=OrderStatus.SHIPPING,
                items=[
                    OrderItem(
                        item_id="PROD-APPLE-01",
                        product_name="안동 사과 2kg",
                        quantity=1,
                        unit_price=19000,
                        category="fresh_food",
                    )
                ],
                total_amount=19000,
                channel=OrderChannel.CAFE24,
                paid_at=now - timedelta(hours=10),
                delivered_at=None,
                shipping_code="HANJIN112233",
                carrier_name="한진택배",
            )

        if order_id.startswith("ORD-"):
            # Generative fallback for arbitrary test order IDs
            return Order(
                order_id=order_id,
                customer_id="CUST-DYNAMIC",
                mall_id="demo_mall",
                status=OrderStatus.DELIVERED,
                items=[
                    OrderItem(
                        item_id="PROD-DEFAULT",
                        product_name="제철 신선 과일 세트",
                        quantity=1,
                        unit_price=30000,
                    )
                ],
                total_amount=30000,
                channel=OrderChannel.CAFE24,
                paid_at=now - timedelta(days=1),
                delivered_at=now - timedelta(hours=5),
            )

        return None

    async def register_return_request(
        self,
        order_id: str,
        reason: str,
        claim_id: str,
        idempotency_key: str,
    ) -> bool:
        # Idempotency check: if already submitted under this key, return True without double mutate
        if idempotency_key in self._submitted_returns:
            return True

        self._submitted_returns[idempotency_key] = {
            "order_id": order_id,
            "claim_id": claim_id,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return True
