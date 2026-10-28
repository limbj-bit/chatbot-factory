import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logging import logger
from app.domain.claims.models import ClaimStatus
from app.domain.policies.models import PolicyDecisionResult, PolicyDecisionType
from app.domain.ports.channel_port import ClaimChannelPort
from app.infrastructure.channels.cafe24 import Cafe24Adapter
from app.infrastructure.channels.mock_cafe24 import MockCafe24Adapter
from app.infrastructure.database.models import ClaimEventModel, ClaimModel, RefundDecisionModel


class RefundService:
    """Application Service for executing refunds and channel mutations with strict idempotency."""

    def __init__(self, channel_adapter: Optional[ClaimChannelPort] = None):
        if channel_adapter:
            self.channel_adapter = channel_adapter
        elif settings.MOCK_CAFE24:
            self.channel_adapter = MockCafe24Adapter()
        else:
            self.channel_adapter = Cafe24Adapter()

    async def execute_refund(
        self,
        session: AsyncSession,
        claim: ClaimModel,
        decision_result: PolicyDecisionResult,
        operation_id: Optional[str] = None,
        actor: str = "RULE_ENGINE",
    ) -> bool:
        op_id = operation_id or str(uuid.uuid4())
        idempotency_key = f"claim:{claim.id}:refund:{op_id}"

        # 1. Idempotency Check in Database
        existing_q = await session.execute(
            select(RefundDecisionModel).where(RefundDecisionModel.idempotency_key == idempotency_key)
        )
        existing = existing_q.scalar_one_or_none()
        if existing:
            logger.warning(
                f"Duplicate refund operation prevented for claim={claim.id} key={idempotency_key}"
            )
            return True

        # 2. Record Decision as PENDING
        refund_record = RefundDecisionModel(
            id=str(uuid.uuid4()),
            claim_id=claim.id,
            decision=decision_result.decision.value,
            reason_code=decision_result.reason_code.value,
            refund_ratio=decision_result.refund_ratio,
            refund_amount=decision_result.calculated_amount or 0,
            idempotency_key=idempotency_key,
            execution_status="PENDING",
        )
        session.add(refund_record)
        await session.flush()

        # 3. Mutate Channel State (Cafe24 / Coupang / Smartstore)
        try:
            success = await self.channel_adapter.register_return_request(
                order_id=claim.order_id,
                reason=decision_result.explanation,
                claim_id=claim.id,
                idempotency_key=idempotency_key,
            )

            if success:
                refund_record.execution_status = "SUCCESS"
                claim.status = (
                    ClaimStatus.AUTO_APPROVED.value
                    if actor == "RULE_ENGINE"
                    else ClaimStatus.COMPLETED.value
                )
                claim.refund_amount = decision_result.calculated_amount or 0

                event = ClaimEventModel(
                    id=str(uuid.uuid4()),
                    claim_id=claim.id,
                    event_type="REFUND_EXECUTED",
                    from_status=claim.status,
                    to_status=claim.status,
                    actor=actor,
                    reason=decision_result.explanation,
                    payload_json=f'{{"refund_amount": {claim.refund_amount}, "idempotency_key": "{idempotency_key}"}}',
                )
                session.add(event)
                await session.commit()
                return True

            return False

        except Exception as e:
            # Handle unknown state / timeout: DO NOT RETRY BLINDLY
            logger.critical(
                f"External channel call failed for claim={claim.id}: {e}. Transitioning to UNKNOWN_EXTERNAL_STATE."
            )
            refund_record.execution_status = "UNKNOWN_EXTERNAL_STATE"
            claim.status = ClaimStatus.UNKNOWN_EXTERNAL_STATE.value

            event = ClaimEventModel(
                id=str(uuid.uuid4()),
                claim_id=claim.id,
                event_type="EXTERNAL_MUTATION_FAILED",
                from_status=claim.status,
                to_status=ClaimStatus.UNKNOWN_EXTERNAL_STATE.value,
                actor=actor,
                reason=f"Channel mutation failed or timed out: {e}",
            )
            session.add(event)
            await session.commit()
            return False
