import json
import os
import uuid
from typing import Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logging import logger
from app.core.security import compute_sha256, validate_image_file
from app.domain.claims.models import ClaimStatus, ClaimType
from app.domain.policies.models import PolicyConfig, PolicyDecisionResult, PolicyDecisionType
from app.domain.policies.refund_policy import RefundPolicyEngine
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.router import AIProviderRouter
from app.infrastructure.database.models import (
    ClaimEventModel,
    ClaimImageModel,
    ClaimModel,
)
from app.application.notification_service import notification_service
from app.application.order_service import OrderService
from app.application.refund_service import RefundService


class ClaimService:
    """Application Service orchestrating the complete Claim lifecycle."""

    def __init__(
        self,
        ai_router: Optional[AIProviderPort] = None,
        order_service: Optional[OrderService] = None,
        refund_service: Optional[RefundService] = None,
        policy_engine: Optional[RefundPolicyEngine] = None,
    ):
        self.ai_router = ai_router or AIProviderRouter()
        self.order_service = order_service or OrderService()
        self.refund_service = refund_service or RefundService()
        self.policy_engine = policy_engine or RefundPolicyEngine(
            PolicyConfig(
                full_refund_damage_ratio=settings.POLICY_FULL_REFUND_DAMAGE_RATIO,
                partial_refund_damage_ratio=settings.POLICY_PARTIAL_REFUND_DAMAGE_RATIO,
                max_claim_days=settings.POLICY_MAX_CLAIM_DAYS,
                min_vision_confidence=settings.POLICY_MIN_VISION_CONFIDENCE,
            )
        )

    async def create_claim(
        self,
        session: AsyncSession,
        order_id: str,
        customer_id: str,
        claim_type: str,
        description: str,
        mall_id: str = "demo_mall",
    ) -> ClaimModel:
        claim_id = str(uuid.uuid4())
        claim = ClaimModel(
            id=claim_id,
            mall_id=mall_id,
            order_id=order_id,
            customer_id=customer_id,
            claim_type=claim_type,
            status=ClaimStatus.RECEIVED.value,
            description=description,
            idempotency_key=f"claim:{claim_id}:create",
        )
        session.add(claim)

        # Audit event
        event = ClaimEventModel(
            id=str(uuid.uuid4()),
            claim_id=claim_id,
            event_type="CLAIM_CREATED",
            from_status=None,
            to_status=ClaimStatus.RECEIVED.value,
            actor="CUSTOMER",
            reason="Customer submitted claim",
            payload_json=f'{{"order_id": "{order_id}", "claim_type": "{claim_type}"}}',
        )
        session.add(event)
        await session.commit()
        await session.refresh(claim)
        return claim

    async def process_image_and_evaluate(
        self,
        session: AsyncSession,
        claim_id: str,
        file_bytes: bytes,
        filename: str,
        declared_mime: str,
    ) -> Tuple[ClaimModel, PolicyDecisionResult]:
        # 1. Fetch Claim
        claim_q = await session.execute(select(ClaimModel).where(ClaimModel.id == claim_id))
        claim = claim_q.scalar_one_or_none()
        if not claim:
            raise ValueError(f"Claim not found: {claim_id}")

        # 2. Security & MIME Magic Byte Validation
        is_valid, detected_mime, err = validate_image_file(file_bytes, filename, declared_mime)
        if not is_valid:
            claim.status = ClaimStatus.IMAGE_RETAKE_REQUIRED.value
            event = ClaimEventModel(
                id=str(uuid.uuid4()),
                claim_id=claim_id,
                event_type="IMAGE_REJECTED",
                from_status=claim.status,
                to_status=ClaimStatus.IMAGE_RETAKE_REQUIRED.value,
                actor="SECURITY_GATE",
                reason=err or "Invalid image file",
            )
            session.add(event)
            await session.commit()
            raise ValueError(err)

        # 3. Check Duplicate Image Hash (Fraud Signal)
        img_hash = compute_sha256(file_bytes)
        dup_q = await session.execute(
            select(func.count(ClaimImageModel.id)).where(ClaimImageModel.file_hash == img_hash)
        )
        duplicate_count = dup_q.scalar_one() or 0
        is_duplicate = duplicate_count > 0

        # Save image file to local uploads directory
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        saved_filename = f"{claim_id}_{img_hash[:10]}_{filename}"
        saved_path = os.path.join(settings.UPLOAD_DIR, saved_filename)
        with open(saved_path, "wb") as f:
            f.write(file_bytes)

        # 4. Vision Observation (AI analyzes physical properties ONLY)
        claim.status = ClaimStatus.IMAGE_ANALYZING.value
        await session.commit()

        observation = await self.ai_router.analyze_claim_image(file_bytes, detected_mime)

        image_record = ClaimImageModel(
            id=str(uuid.uuid4()),
            claim_id=claim_id,
            file_path=saved_path,
            file_hash=img_hash,
            is_primary=True,
            defect_type=observation.defect_type.value,
            damage_ratio=observation.damage_ratio_estimate,
            confidence=observation.confidence,
            evidence_json=json.dumps(observation.visible_evidence, ensure_ascii=False),
            image_quality=observation.image_quality.value,
        )
        session.add(image_record)

        # 5. Order Verification & History
        order = await self.order_service.get_order_details(claim.order_id)

        prior_claims_q = await session.execute(
            select(func.count(ClaimModel.id)).where(
                ClaimModel.customer_id == claim.customer_id,
                ClaimModel.id != claim_id,
            )
        )
        customer_claim_count = prior_claims_q.scalar_one() or 0

        # 6. Deterministic Policy Evaluation (Rule Engine)
        claim.status = ClaimStatus.POLICY_EVALUATING.value
        decision = self.policy_engine.evaluate(
            order=order,
            observation=observation,
            customer_claim_count_30d=customer_claim_count,
            is_duplicate_image=is_duplicate,
        )

        # 7. Apply Decision
        if decision.decision in (PolicyDecisionType.FULL_REFUND, PolicyDecisionType.PARTIAL_REFUND):
            claim.status = ClaimStatus.AUTO_APPROVED.value
            claim.refund_amount = decision.calculated_amount or 0
            # Execute channel mutation
            await self.refund_service.execute_refund(
                session=session,
                claim=claim,
                decision_result=decision,
                operation_id=f"auto_{claim_id}",
                actor="RULE_ENGINE",
            )
        elif decision.decision == PolicyDecisionType.RETAKE_IMAGE:
            claim.status = ClaimStatus.IMAGE_RETAKE_REQUIRED.value
        elif decision.decision == PolicyDecisionType.MANUAL_REVIEW:
            claim.status = ClaimStatus.MANUAL_REVIEW.value
            await notification_service.notify_merchant_alert(
                session=session,
                mall_id=claim.mall_id or "demo_mall",
                alert_type="ESCALATE_TO_HUMAN",
                title="상담원 확인 필요 (긴급 클레임/진단서 확인 이관)",
                message=(
                    f"주문번호: {claim.order_id} / 고객: {claim.customer_id}\n"
                    f"사유코드: {decision.reason_code.value} / AI 판독 결함: {observation.defect_type.value} ({observation.damage_ratio_estimate}%)\n"
                    f"설명: {decision.explanation}"
                ),
                claim_id=claim.id,
                extra_data={
                    "order_id": claim.order_id,
                    "reason_code": decision.reason_code.value,
                    "defect_type": observation.defect_type.value,
                },
            )
        elif decision.decision == PolicyDecisionType.REJECT:
            claim.status = ClaimStatus.REJECTED.value

        event = ClaimEventModel(
            id=str(uuid.uuid4()),
            claim_id=claim_id,
            event_type=f"POLICY_DECIDED_{decision.decision.value}",
            from_status=ClaimStatus.POLICY_EVALUATING.value,
            to_status=claim.status,
            actor="RULE_ENGINE",
            reason=decision.explanation,
            payload_json=json.dumps(
                {
                    "decision": decision.decision.value,
                    "reason_code": decision.reason_code.value,
                    "refund_ratio": decision.refund_ratio,
                    "calculated_amount": decision.calculated_amount,
                    "defect_type": observation.defect_type.value,
                    "damage_ratio": observation.damage_ratio_estimate,
                },
                ensure_ascii=False,
            ),
        )
        session.add(event)
        await session.commit()
        await session.refresh(claim)

        return claim, decision
