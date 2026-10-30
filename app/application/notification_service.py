import json
import smtplib
import uuid
from email.message import EmailMessage
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logging import logger
from app.infrastructure.database.models import StoreModel, WebhookAlertLogModel


class NotificationService:
    """Merchant (store staff) alerts: Telegram Bot API, generic webhook, optional SMTP email."""

    async def notify_merchant_alert(
        self,
        session: AsyncSession,
        mall_id: str,
        alert_type: str,
        title: str,
        message: str,
        claim_id: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        ticket_url: Optional[str] = None,
    ) -> Optional[WebhookAlertLogModel]:
        q = select(StoreModel).where(StoreModel.mall_id == mall_id)
        res = await session.execute(q)
        store = res.scalar_one_or_none()

        webhook_url = store.webhook_url if store and store.webhook_url else "mock://merchant-alert"
        store_name = store.store_name if store else mall_id
        staff_email = (store.contact_email if store else None) or ""

        text = f"[{store_name}] {title}\n{message}"
        if ticket_url:
            text = f"{text}\n열기: {ticket_url}"

        payload = {
            "text": text,
            "mall_id": mall_id,
            "store_name": store_name,
            "alert_type": alert_type,
            "claim_id": claim_id,
            "ticket_url": ticket_url,
            "extra": extra_data or {},
        }
        payload_str = json.dumps(payload, ensure_ascii=False)

        statuses: List[str] = []
        if webhook_url.startswith("http://") or webhook_url.startswith("https://"):
            statuses.append(await self._deliver_http(webhook_url, text, payload))
        else:
            statuses.append("MOCK_LOGGED")

        email_status = await self._deliver_email(staff_email, store_name, title, text)
        if email_status:
            statuses.append(email_status)

        delivery_status = "+".join(statuses)

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
            f"Merchant alert recorded: mall={mall_id} type={alert_type} status={delivery_status}"
        )
        return alert_log

    async def _deliver_http(self, webhook_url: str, text: str, payload: dict) -> str:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                if "api.telegram.org" in webhook_url and "/sendMessage" in webhook_url:
                    parsed = urlparse(webhook_url)
                    qs = parse_qs(parsed.query)
                    chat_id = (qs.get("chat_id") or [None])[0]
                    if not chat_id:
                        return "TELEGRAM_MISSING_CHAT_ID"
                    # Strip query for POST body style
                    base = webhook_url.split("?")[0]
                    resp = await client.post(
                        base, json={"chat_id": chat_id, "text": text}
                    )
                else:
                    resp = await client.post(webhook_url, json=payload)
                return "SENT" if resp.status_code < 400 else f"HTTP_{resp.status_code}"
        except Exception as e:
            logger.warning(f"Webhook delivery failed: {e}")
            return "FAILED"

    async def _deliver_email(
        self, to_email: str, store_name: str, title: str, body: str
    ) -> Optional[str]:
        """Send to store contact_email when SMTP env is configured; else skip."""
        if not to_email or "@" not in to_email:
            return None
        host = getattr(settings, "STAFF_ALERT_SMTP_HOST", "") or ""
        if not host.strip():
            logger.info(f"Email alert skipped (no SMTP): to={to_email} title={title}")
            return "EMAIL_SKIPPED_NO_SMTP"
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[{store_name}] {title}"
            msg["From"] = getattr(settings, "STAFF_ALERT_FROM", None) or "noreply@chatbot-factory.local"
            msg["To"] = to_email
            msg.set_content(body)
            port = int(getattr(settings, "STAFF_ALERT_SMTP_PORT", 587) or 587)
            user = getattr(settings, "STAFF_ALERT_SMTP_USER", "") or ""
            password = getattr(settings, "STAFF_ALERT_SMTP_PASSWORD", "") or ""
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.starttls()
                if user:
                    smtp.login(user, password)
                smtp.send_message(msg)
            return "EMAIL_SENT"
        except Exception as e:
            logger.warning(f"Email alert failed to={to_email}: {e}")
            return "EMAIL_FAILED"

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
