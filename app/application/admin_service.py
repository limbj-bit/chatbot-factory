import json
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
            .order_by(desc(ClaimModel.created_at))
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

        decision = PolicyDecisionResult(
            decision=PolicyDecisionType.FULL_REFUND if refund_amount >= claim.refund_amount else PolicyDecisionType.PARTIAL_REFUND,
            reason_code=PolicyReasonCode.SEVERE_DAMAGE,
            requires_manual_review=False,
            refund_ratio=100,
            explanation=f"Admin manual override: {reason}",
            suggested_customer_message="관리자 검토 결과 환불 승인되었습니다.",
            calculated_amount=refund_amount,
        )

        success = await self.refund_service.execute_refund(
            session=session,
            claim=claim,
            decision_result=decision,
            operation_id=f"admin_override_{claim_id}_{uuid.uuid4().hex[:6]}",
            actor=actor,
        )
        return success

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
