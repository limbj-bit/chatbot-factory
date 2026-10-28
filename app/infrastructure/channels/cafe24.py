from datetime import datetime, timezone
from typing import Optional
import httpx
from app.core.config import settings
from app.core.logging import logger
from app.domain.orders.models import Order, OrderChannel, OrderItem, OrderStatus
from app.domain.ports.channel_port import ClaimChannelPort, OrderChannelPort


class Cafe24OrderError(Exception):
    """Base error for Cafe24 live order lookup."""


class Cafe24OrderNotFound(Cafe24OrderError):
    """Order id does not exist in the mall (HTTP 404)."""


class Cafe24RateLimited(Cafe24OrderError):
    """Cafe24 rate limit exceeded (HTTP 429)."""


class Cafe24TransientError(Cafe24OrderError):
    """Timeout / 5xx / network blip. Safe to tell customer to retry later."""


class Cafe24AuthError(Cafe24OrderError):
    """Access token rejected (HTTP 401/403). Caller should refresh & retry once."""


# Cafe24 order_status single-letter codes -> domain OrderStatus
_CAFE24_STATUS_MAP = {
    "N": OrderStatus.PAID,        # 주문
    "B": OrderStatus.PREPARING,   # 상품준비중
    "P": OrderStatus.SHIPPING,    # 배송중
    "D": OrderStatus.DELIVERED,   # 배송완료
    "C": OrderStatus.CANCELLED,   # 주문취소
    "E": OrderStatus.SHIPPING,    # 교환접수
    "R": OrderStatus.REFUNDED,    # 반품접수
}


def map_cafe24_status(raw: str) -> OrderStatus:
    code = (raw or "").strip().upper()
    if code in _CAFE24_STATUS_MAP:
        return _CAFE24_STATUS_MAP[code]
    # Fall back to word matching for verbose payloads
    lowered = code.lower()
    if "delivered" in lowered or "shipped" in lowered:
        return OrderStatus.DELIVERED
    if "cancel" in lowered:
        return OrderStatus.CANCELLED
    if "refund" in lowered or "return" in lowered:
        return OrderStatus.REFUNDED
    if "prep" in lowered:
        return OrderStatus.PREPARING
    return OrderStatus.SHIPPING


def build_order_from_payload(order_id: str, mall_id: str, data: dict) -> Order:
    """Map a Cafe24 order payload to the domain Order (PII excluded by design)."""
    raw_status = data.get("order_status", "")
    status = map_cafe24_status(raw_status)

    delivered_at = None
    if data.get("delivered_date"):
        try:
            delivered_at = datetime.fromisoformat(str(data["delivered_date"]))
        except Exception:
            delivered_at = None

    items = []
    for item in data.get("items", []) or []:
        items.append(
            OrderItem(
                item_id=str(item.get("product_no", "")),
                product_name=item.get("product_name", "상품"),
                quantity=int(item.get("quantity", 1) or 1),
                unit_price=int(float(item.get("product_price", 0) or 0)),
            )
        )

    # Delivery tracking (carrier + tracking number)
    carrier_name = None
    shipping_code = None
    deliveries = data.get("deliveries") or data.get("delivery") or []
    if isinstance(deliveries, list) and deliveries:
        first = deliveries[0] or {}
        carrier_name = first.get("delivery_company_name") or first.get("delivery_company")
        shipping_code = first.get("tracking_number") or first.get("tracking_code")

    total_amount = 0
    actual = data.get("actual_order_amount") or {}
    if isinstance(actual, dict):
        total_amount = int(float(actual.get("order_price_amount", 0) or 0))
    else:
        total_amount = int(float(data.get("order_price_amount", 0) or 0))

    return Order(
        order_id=order_id,
        customer_id="guest",
        mall_id=mall_id,
        status=status,
        items=items,
        total_amount=total_amount,
        channel=OrderChannel.CAFE24,
        delivered_at=delivered_at,
        shipping_code=shipping_code,
        carrier_name=carrier_name,
    )


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

    async def fetch_order_payload(self, order_id: str, access_token: str) -> dict:
        """Fetch raw order payload with explicit access_token.

        Raises typed errors so callers can distinguish not-found / rate-limit /
        transient failures instead of collapsing everything to None.
        """
        url = f"{self.base_url}/orders/{order_id}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Cafe24-Api-Version": self.api_version,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(url, headers=headers)
            except httpx.TimeoutException as e:
                raise Cafe24TransientError("timeout") from e
            except httpx.HTTPError as e:
                raise Cafe24TransientError("network") from e

            if resp.status_code == 404:
                raise Cafe24OrderNotFound(order_id)
            if resp.status_code == 429:
                raise Cafe24RateLimited(order_id)
            if resp.status_code in (401, 403):
                raise Cafe24AuthError(order_id)
            if resp.status_code >= 500:
                raise Cafe24TransientError(f"http_{resp.status_code}")
            if resp.status_code >= 400:
                # Other 4xx treated as transient-safe (do not leak details to customer)
                raise Cafe24TransientError(f"http_{resp.status_code}")

            return resp.json().get("order", {}) or {}

    async def get_order(self, order_id: str) -> Optional[Order]:
        if not self.access_token:
            logger.warning("Cafe24 access token not configured.")
            return None

        try:
            payload = await self.fetch_order_payload(order_id, self.access_token)
            return build_order_from_payload(order_id, self.mall_id, payload)
        except Cafe24OrderError as e:
            logger.warning(f"Cafe24 live order lookup failed for {order_id}: {type(e).__name__}")
            return None
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
