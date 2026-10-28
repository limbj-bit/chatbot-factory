from typing import List, Optional
from pydantic import BaseModel


class OrderItemSchema(BaseModel):
    item_id: str
    product_name: str
    quantity: int
    unit_price: int
    total_price: int


class OrderResponse(BaseModel):
    order_id: str
    customer_id: str
    status: str
    total_amount: int
    channel: str
    delivered_at: Optional[str]
    carrier_name: Optional[str] = None
    shipping_code: Optional[str] = None
    items: List[OrderItemSchema]
