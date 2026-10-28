from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class OrderStatus(str, Enum):
    PAID = "paid"
    PREPARING = "preparing"
    SHIPPING = "shipping"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class OrderChannel(str, Enum):
    CAFE24 = "cafe24"
    SMARTSTORE = "smartstore"
    COUPANG = "coupang"
    CUSTOM = "custom"


@dataclass(frozen=True)
class OrderItem:
    item_id: str
    product_name: str
    quantity: int
    unit_price: int
    category: str = "fresh_food"
    total_price: int = 0

    def __post_init__(self):
        if not self.total_price:
            object.__setattr__(self, "total_price", self.unit_price * self.quantity)


@dataclass
class Order:
    order_id: str
    customer_id: str
    mall_id: str
    status: OrderStatus
    items: List[OrderItem] = field(default_factory=list)
    total_amount: int = 0
    channel: OrderChannel = OrderChannel.CAFE24
    paid_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    shipping_code: Optional[str] = None
    carrier_name: Optional[str] = None

    def is_delivered(self) -> bool:
        return self.status == OrderStatus.DELIVERED and self.delivered_at is not None
