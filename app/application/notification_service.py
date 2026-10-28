import json
import uuid
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger
from app.infrastructure.database.models import StoreModel, WebhookAlertLogModel


class NotificationService:
    """Application Service for sending real-time merchant alerts (Slack/Telegram/Discord/Webhook) on claim escalation."""

    async def notify_merchant_alert(
        self,
        session: AsyncSession,
        mall_id: str,
        alert_type: str,
        title: str,
        message: str,
        claim_id: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[WebhookAlertLogModel]:
        q = select(StoreModel).where(StoreModel.mall_id == mall_id)
        res = await session.execute(q)
        store = res.scalar_one_or_none()

        webhook_url = store.webhook_url if store and store.webhook_url else "mock://merchant-alert"
        store_name = store.store_name if store else mall_id

        payload = {
            "text": f"🚨 [{store_name}] {title}\n{message}",
            "mall_id": mall_id,
            "store_name": store_name,
            "alert_type": alert_type,
            "claim_id": claim_id,
            "extra": extra_data or {},
        }
        payload_str = json.dumps(payload, ensure_ascii=False)

        delivery_status = "MOCK_LOGGED"
        if webhook_url.startswith("http://") or webhook_url.startswith("https://"):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(webhook_url, json=payload)
                    delivery_status = "SENT" if resp.status_code < 400 else f"HTTP_{resp.status_code}"
            except Exception as e:
                logger.warning(f"Webhook delivery failed for mall={mall_id}: {e}")
                delivery_status = "FAILED"

        alert_log = WebhookAlertLogModel(
            id=str(uuid.uuid4()),
            mall_id=mall_id,
            claim_id=claim_id,
            alert_type=alert_type,
            webhook_url=webhook_url,
            payload_json=payload_str,
            delivery_status=delivery_status,
        )
        session.add(alert_log)
        await session.commit()
        await session.refresh(alert_log)
        logger.info(
            f"Merchant webhook alert recorded: mall={mall_id} type={alert_type} status={delivery_status}"
        )
        return alert_log

    async def list_alerts(
        self, session: AsyncSession, mall_id: str
    ) -> List[Dict[str, Any]]:
        q = (
            select(WebhookAlertLogModel)
            .where(WebhookAlertLogModel.mall_id == mall_id)
            .order_by(WebhookAlertLogModel.created_at.desc())
        )
        res = await session.execute(q)
        logs = res.scalars().all()
        return [
            {
                "id": item.id,
                "mall_id": item.mall_id,
                "claim_id": item.claim_id,
                "alert_type": item.alert_type,
                "webhook_url": item.webhook_url,
                "payload": json.loads(item.payload_json),
                "delivery_status": item.delivery_status,
                "created_at": item.created_at.isoformat(),
            }
            for item in logs
        ]


notification_service = NotificationService()
