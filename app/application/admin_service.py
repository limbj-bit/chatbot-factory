import json
import logging
import uuid
from typing import List, Optional
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.domain.claims.models import ClaimStatus
from app.domain.policies.models import PolicyDecisionResult, PolicyDecisionType, PolicyReasonCode
from app.infrastructure.database.models import ClaimEventModel, ClaimModel
from app.application.refund_service import RefundService


class AdminService:
    """Application Service for admin review, claim overrides, and audit management."""

    def __init__(self, refund_service: Optional[RefundService] = None):
        self.refund_service = refund_service or RefundService()

    async def list_pending_claims(self, session: AsyncSession) -> List[ClaimModel]:
        q = (
            select(ClaimModel)
            .options(selectinload(ClaimModel.images), selectinload(ClaimModel.events))
            .where(ClaimModel.status.in_([ClaimStatus.MANUAL_REVIEW.value, ClaimStatus.RECEIVED.value]))
            .order_by(ClaimModel.created_at.asc())
        )
        res = await session.execute(q)
        return list(res.scalars().all())

    async def approve_claim(
        self,
        session: AsyncSession,
        claim_id: str,
        refund_amount: int,
        reason: str,
        actor: str = "ADMIN_OPERATOR",
    ) -> bool:
        q = select(ClaimModel).where(ClaimModel.id == claim_id)
        res = await session.execute(q)
        claim = res.scalar_one_or_none()
        if not claim:
            raise ValueError(f"Claim not found: {claim_id}")

        # Guard: do not re-execute a refund for an already-finalized claim.
        if claim.status in (
            ClaimStatus.AUTO_APPROVED.value,
            ClaimStatus.COMPLETED.value,
            ClaimStatus.REJECTED.value,
        ):
            logging.getLogger(__name__).warning(
                "Admin approve ignored for finalized claim=%s status=%s", claim_id, claim.status
            )
            return True

        decision = PolicyDecisionResult(
            decision=PolicyDecisionType.FULL_REFUND if refund_amount >= claim.refund_amount else PolicyDecisionType.PARTIAL_REFUND,
            reason_code=PolicyReasonCode.SEVERE_DAMAGE,
            requires_manual_review=False,
            refund_ratio=100,
            explanation=f"Admin manual override: {reason}",
            suggested_customer_message="관리자 검토 결과 환불 승인되었습니다.",
            calculated_amount=refund_amount,
        )

        # Deterministic idempotency key so repeated approvals cannot double-refund.
        success = await self.refund_service.execute_refund(
            session=session,
            claim=claim,
            decision_result=decision,
            operation_id=f"admin_override_{claim_id}",
            actor=actor,
        )
        return success

    async def check_sla_alerts(
        self,
        session,
        sla_hours: int = 24,
        warning_hours: int = 4,
    ) -> dict:
        """Detect SLA-aged pending claims and notify the merchant once per level.

        Returns {"checked", "notified", "skipped_duplicates"}.
        Deduplication key is (claim_id, alert_type): an already-attempted alert
        (even one whose delivery failed) is never retried, so a broken webhook
        cannot flood the merchant every check cycle.
        """
        from datetime import datetime, timedelta, timezone

        from app.application.notification_service import notification_service
        from app.infrastructure.database.models import WebhookAlertLogModel

        now = datetime.now(timezone.utc)
        warn_cutoff = now - timedelta(hours=warning_hours)
        breach_cutoff = now - timedelta(hours=sla_hours)

        q = select(ClaimModel).where(
            ClaimModel.status.in_([ClaimStatus.MANUAL_REVIEW.value, ClaimStatus.RECEIVED.value]),
            ClaimModel.created_at < warn_cutoff,
        )
        res = await session.execute(q)
        # Flatten before notifying: notify_merchant_alert commits, which expires
        # ORM instances and would break lazy attribute access mid-loop.
        claims = [
            (c.id, c.mall_id or "demo_mall", c.status, c.created_at)
            for c in res.scalars().all()
        ]

        checked = len(claims)
        notified = 0
        skipped = 0
        for claim_id, mall_id, status, created_at in claims:
            created = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
            breached = created < breach_cutoff
            age_minutes = int((now - created).total_seconds() / 60)
            alert_type = "SLA_BREACH" if breached else "SLA_WARNING"
            title = "SLA 초과 클레임" if breached else "SLA 경고 클레임"

            try:
                dup = await session.execute(
                    select(WebhookAlertLogModel.id)
                    .where(
                        WebhookAlertLogModel.claim_id == claim_id,
                        WebhookAlertLogModel.alert_type == alert_type,
                    )
                    .limit(1)
                )
                if dup.scalar_one_or_none() is not None:
                    skipped += 1
                    continue

                await notification_service.notify_merchant_alert(
                    session=session,
                    mall_id=mall_id,
                    alert_type=alert_type,
                    title=title,
                    message=(
                        f"claim_id={claim_id} status={status} "
                        f"경과={age_minutes}분 (경고 {warning_hours}h / 초과 {sla_hours}h)"
                    ),
                    claim_id=claim_id,
                    extra_data={"age_minutes": age_minutes, "level": alert_type},
                )
                notified += 1
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "SLA alert failed for claim=%s: %s", claim_id, exc
                )
                continue

        return {"checked": checked, "notified": notified, "skipped_duplicates": skipped}

    async def reject_claim(
        self,
        session: AsyncSession,
        claim_id: str,
        reason: str,
        actor: str = "ADMIN_OPERATOR",
    ) -> bool:
        q = select(ClaimModel).where(ClaimModel.id == claim_id)
        res = await session.execute(q)
        claim = res.scalar_one_or_none()
        if not claim:
            raise ValueError(f"Claim not found: {claim_id}")

        old_status = claim.status
        claim.status = ClaimStatus.REJECTED.value

        event = ClaimEventModel(
            id=str(uuid.uuid4()),
            claim_id=claim_id,
            event_type="ADMIN_REJECTED",
            from_status=old_status,
            to_status=ClaimStatus.REJECTED.value,
            actor=actor,
            reason=reason,
        )
        session.add(event)
        await session.commit()
        return True
