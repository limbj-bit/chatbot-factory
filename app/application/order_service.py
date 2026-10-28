from typing import Optional
from app.core.config import settings
from app.domain.orders.models import Order
from app.domain.ports.channel_port import OrderChannelPort
from app.infrastructure.channels.cafe24 import Cafe24Adapter
from app.infrastructure.channels.mock_cafe24 import MockCafe24Adapter


class OrderService:
    """Application Service for order verification and inquiries across e-commerce channels."""

    def __init__(self, channel_adapter: Optional[OrderChannelPort] = None):
        if channel_adapter:
            self.channel_adapter = channel_adapter
        elif settings.MOCK_CAFE24:
            self.channel_adapter = MockCafe24Adapter()
        else:
            self.channel_adapter = Cafe24Adapter()

    async def get_order_details(self, order_id: str) -> Optional[Order]:
        return await self.channel_adapter.get_order(order_id)
