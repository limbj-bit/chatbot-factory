from datetime import datetime, timedelta, timezone
import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.application.admin_service import AdminService
from app.infrastructure.database.models import ClaimModel, StoreModel, WebhookAlertLogModel
from app.infrastructure.database.session import async_session_factory


@pytest.fixture(autouse=True)
def no_real_webhook_calls():
    """Keep tests offline: stores use an http webhook, so delivery must be faked."""
    with patch(
        "app.application.notification_service.NotificationService._deliver_http",
        new=AsyncMock(return_value="SENT"),
    ):
        yield


async def _make_claim(status: str, age_hours: float) -> str:
    claim_id = str(uuid.uuid4())
    async with async_session_factory() as session:
        if await session.get(StoreModel, "store_demo") is None:
            session.add(
                StoreModel(
                    id="store_demo",
                    mall_id="demo_mall",
                    store_name="테스트매장",
                    webhook_url="https://example.invalid/hook",
                    contact_email="",
                )
            )
        session.add(
            ClaimModel(
                id=claim_id,
                mall_id="demo_mall",
                order_id="order_1",
                customer_id="cust_1",
                claim_type="DAMAGE",
                status=status,
                description="test claim",
                created_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
            )
        )
        await session.commit()
    return claim_id


async def _alert_types(claim_id: str) -> list[str]:
    async with async_session_factory() as session:
        res = await session.execute(
            select(WebhookAlertLogModel.alert_type).where(
                WebhookAlertLogModel.claim_id == claim_id
            )
        )
        return [row[0] for row in res.fetchall()]


@pytest.mark.asyncio
async def test_breach_alert_sent_once_then_deduplicated():
    claim_id = await _make_claim("MANUAL_REVIEW", age_hours=30)
    svc = AdminService()

    async with async_session_factory() as session:
        first = await svc.check_sla_alerts(session, sla_hours=24, warning_hours=4)
    async with async_session_factory() as session:
        second = await svc.check_sla_alerts(session, sla_hours=24, warning_hours=4)

    assert first["checked"] == 1
    assert first["notified"] == 1
    assert first["skipped_duplicates"] == 0
    # Second sweep must not notify the same claim again.
    assert second["notified"] == 0
    assert second["skipped_duplicates"] == 1
    assert await _alert_types(claim_id) == ["SLA_BREACH"]


@pytest.mark.asyncio
async def test_warning_level_alert_for_aging_claim():
    claim_id = await _make_claim("RECEIVED", age_hours=5)
    svc = AdminService()

    async with async_session_factory() as session:
        result = await svc.check_sla_alerts(session, sla_hours=24, warning_hours=4)

    assert result["notified"] == 1
    assert await _alert_types(claim_id) == ["SLA_WARNING"]


@pytest.mark.asyncio
async def test_fresh_or_finalized_claims_are_ignored():
    await _make_claim("MANUAL_REVIEW", age_hours=1)  # inside warning window
    await _make_claim("COMPLETED", age_hours=48)  # finalized, not pending
    svc = AdminService()

    async with async_session_factory() as session:
        result = await svc.check_sla_alerts(session, sla_hours=24, warning_hours=4)

    assert result["checked"] == 0
    assert result["notified"] == 0


@pytest.mark.asyncio
async def test_failed_delivery_is_not_retried_every_cycle():
    """A broken webhook must not flood the merchant: attempts are one-shot.

    notify_merchant_alert logs FAILED deliveries, and the dedup guard counts
    any existing log row (regardless of status) as "already attempted".
    """
    claim_id = await _make_claim("MANUAL_REVIEW", age_hours=30)
    svc = AdminService()

    with patch(
        "app.application.notification_service.NotificationService._deliver_http",
        new=AsyncMock(return_value="FAILED"),
    ):
        async with async_session_factory() as session:
            first = await svc.check_sla_alerts(session, sla_hours=24, warning_hours=4)
        async with async_session_factory() as session:
            second = await svc.check_sla_alerts(session, sla_hours=24, warning_hours=4)

    assert first["notified"] == 1
    assert second["notified"] == 0
    assert second["skipped_duplicates"] == 1
    assert await _alert_types(claim_id) == ["SLA_BREACH"]
    async with async_session_factory() as session:
        res = await session.execute(
            select(WebhookAlertLogModel.delivery_status).where(
                WebhookAlertLogModel.claim_id == claim_id
            )
        )
        assert res.scalar_one() == "FAILED"


@pytest.mark.asyncio
async def test_manual_sla_check_endpoint_returns_sweep_summary():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    await _make_claim("MANUAL_REVIEW", age_hours=30)
    headers = {"X-Admin-Key": "admin-dev-secret-key-change-in-prod"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/admin/sla/check", params={"sla_hours": 24}, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["sla_hours"] == 24
    assert body == {"sla_hours": 24, "checked": 1, "notified": 1, "skipped_duplicates": 0}


@pytest.mark.asyncio
async def test_sla_loop_disabled_when_interval_zero():
    from app.main import sla_alert_loop

    from app.core.config import settings

    original = settings.SLA_CHECK_INTERVAL_MINUTES
    settings.SLA_CHECK_INTERVAL_MINUTES = 0
    try:
        # Returns immediately instead of awaiting the (would-be) 60s sleep.
        await asyncio.wait_for(sla_alert_loop(), timeout=5)
    finally:
        settings.SLA_CHECK_INTERVAL_MINUTES = original
