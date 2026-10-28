from datetime import datetime, timezone
from typing import Optional
import httpx
from app.core.config import settings
from app.core.logging import logger
from app.domain.orders.models import Order, OrderChannel, OrderItem, OrderStatus
from app.domain.ports.channel_port import ClaimChannelPort, OrderChannelPort


class Cafe24Adapter(OrderChannelPort, ClaimChannelPort):
    """Production Adapter for Cafe24 Open API integration."""

    def __init__(
        self,
        mall_id: Optional[str] = None,
        access_token: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        self.mall_id = mall_id or settings.CAFE24_MALL_ID
        self.access_token = access_token or settings.CAFE24_ACCESS_TOKEN
        self.api_version = api_version or settings.CAFE24_API_VERSION
        self.base_url = f"https://{self.mall_id}.cafe24api.com/api/v2/admin"

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Cafe24-Api-Version": self.api_version,
        }

    async def get_order(self, order_id: str) -> Optional[Order]:
        if not self.access_token:
            logger.warning("Cafe24 access token not configured.")
            return None

        url = f"{self.base_url}/orders/{order_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url, headers=self._get_headers())
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                data = resp.json().get("order", {})

                # Map Cafe24 order status
                raw_status = data.get("order_status", "").lower()
                status = OrderStatus.DELIVERED if "delivered" in raw_status or "shipped" in raw_status else OrderStatus.SHIPPING

                delivered_at = None
                if data.get("delivered_date"):
                    try:
                        delivered_at = datetime.fromisoformat(data["delivered_date"])
                    except Exception:
                        delivered_at = datetime.now(timezone.utc)

                items = []
                for item in data.get("items", []):
                    items.append(
                        OrderItem(
                            item_id=str(item.get("product_no", "")),
                            product_name=item.get("product_name", "상품"),
                            quantity=int(item.get("quantity", 1)),
                            unit_price=int(float(item.get("product_price", 0))),
                        )
                    )

                return Order(
                    order_id=order_id,
                    customer_id=data.get("buyer_member_id", "guest"),
                    mall_id=self.mall_id,
                    status=status,
                    items=items,
                    total_amount=int(float(data.get("actual_order_amount", {}).get("order_price_amount", 0))),
                    channel=OrderChannel.CAFE24,
                    delivered_at=delivered_at,
                )
            except Exception as e:
                logger.error(f"Failed to fetch order {order_id} from Cafe24: {e}")
                return None

    async def register_return_request(
        self,
        order_id: str,
        reason: str,
        claim_id: str,
        idempotency_key: str,
    ) -> bool:
        if not self.access_token:
            logger.warning("Cafe24 access token not configured. Skipping live return mutation.")
            return True

        url = f"{self.base_url}/orders/{order_id}/claims"
        payload = {
            "request": {
                "claim_type": "return",
                "reason": reason,
                "claim_code": claim_id,
            }
        }
        headers = self._get_headers()
        headers["X-Idempotency-Key"] = idempotency_key

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return True
            except httpx.TimeoutException:
                logger.critical(f"Cafe24 return request timed out for claim {claim_id}. State is UNKNOWN.")
                raise RuntimeError("UNKNOWN_EXTERNAL_STATE: Cafe24 return mutation timed out")
            except Exception as e:
                logger.error(f"Cafe24 return request failed: {e}")
                raise
