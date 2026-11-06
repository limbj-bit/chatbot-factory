import json
import os
import uuid
from typing import Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logging import logger
from app.core.security import (
    ai_generated_suspicion,
    compute_perceptual_hash,
    compute_sha256,
    extract_image_metadata,
    hamming_distance,
    normalize_uploaded_image,
    validate_image_file,
)
from app.domain.claims.models import (
    ClaimStatus,
    ClaimType,
    ClaimVisionObservation,
    DefectType,
    ImageQuality,
)
from app.domain.policies.models import PolicyConfig, PolicyDecisionResult, PolicyDecisionType
from app.domain.policies.refund_policy import RefundPolicyEngine
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.router import AIProviderRouter
from app.infrastructure.database.models import (
    ClaimEventModel,
    ClaimImageModel,
    ClaimModel,
    StoreModel,
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

    async def _industry_for_mall(self, session: AsyncSession, mall_id: Optional[str]) -> Optional[str]:
        """Return the store's industry so vision diagnosis can use industry-specific prompts."""
        if not mall_id:
            return None
        try:
            q = await session.execute(select(StoreModel).where(StoreModel.mall_id == mall_id))
            store = q.scalar_one_or_none()
            return store.industry if store else None
        except Exception as e:
            logger.warning(f"[Claim] Failed to load industry for {mall_id}: {e}")
            return None

    async def _policy_engine_for_mall(
        self, session: AsyncSession, mall_id: Optional[str]
    ) -> RefundPolicyEngine:
        """Build a RefundPolicyEngine using the store's own claim policy settings.

        Reads policy_config_json.claim_policy written by the showroom "고급 설정"
        (min_vision_confidence / max_claim_days / full_refund_damage_ratio /
        partial_refund_damage_ratio). Falls back to global settings when the
        store has no override. Values are clamped to sane ranges.
        """
        cfg = PolicyConfig(
            full_refund_damage_ratio=settings.POLICY_FULL_REFUND_DAMAGE_RATIO,
            partial_refund_damage_ratio=settings.POLICY_PARTIAL_REFUND_DAMAGE_RATIO,
            max_claim_days=settings.POLICY_MAX_CLAIM_DAYS,
            min_vision_confidence=settings.POLICY_MIN_VISION_CONFIDENCE,
        )
        if mall_id:
            try:
                q = await session.execute(select(StoreModel).where(StoreModel.mall_id == mall_id))
                store = q.scalar_one_or_none()
                if store and store.policy_config_json:
                    policy = json.loads(store.policy_config_json)
                    claim_policy = policy.get("claim_policy") if isinstance(policy, dict) else None
                    if isinstance(claim_policy, dict):
                        cfg = PolicyConfig(
                            min_vision_confidence=min(
                                0.95, max(0.50, float(claim_policy.get("min_vision_confidence", cfg.min_vision_confidence)))
                            ),
                            max_claim_days=min(
                                30, max(1, int(claim_policy.get("max_claim_days", cfg.max_claim_days)))
                            ),
                            full_refund_damage_ratio=min(
                                100, max(1, int(claim_policy.get("full_refund_damage_ratio", cfg.full_refund_damage_ratio)))
                            ),
                            partial_refund_damage_ratio=min(
                                100, max(0, int(claim_policy.get("partial_refund_damage_ratio", cfg.partial_refund_damage_ratio)))
                            ),
                        )
            except Exception as e:
                logger.warning(f"[Claim] Failed to load per-mall claim policy for {mall_id}: {e}")
        return RefundPolicyEngine(cfg)

    async def process_image_and_evaluate(
        self,
        session: AsyncSession,
        claim_id: str,
        file_bytes: bytes,
        filename: str,
        declared_mime: str,
        role: str = "primary",
    ) -> Tuple[ClaimModel, PolicyDecisionResult]:
        # 1. Fetch Claim
        claim_q = await session.execute(select(ClaimModel).where(ClaimModel.id == claim_id))
        claim = claim_q.scalar_one_or_none()
        if not claim:
            raise ValueError(f"Claim not found: {claim_id}")

        # 1b. Normalize HEIC/HEIF to JPEG (mobile upload support)
        file_bytes, declared_mime, norm_err = normalize_uploaded_image(
            file_bytes, filename, declared_mime
        )
        if norm_err:
            raise ValueError(norm_err)

        # 2. Security & MIME Magic Byte Validation
        is_valid, detected_mime, err = validate_image_file(file_bytes, filename, declared_mime)
        if not is_valid:
            prev_status = claim.status
            claim.status = ClaimStatus.IMAGE_RETAKE_REQUIRED.value
            event = ClaimEventModel(
                id=str(uuid.uuid4()),
                claim_id=claim_id,
                event_type="IMAGE_REJECTED",
                from_status=prev_status,
                to_status=ClaimStatus.IMAGE_RETAKE_REQUIRED.value,
                actor="SECURITY_GATE",
                reason=err or "Invalid image file",
            )
            session.add(event)
            await session.commit()
            raise ValueError(err)

        # 3. Check Duplicate Image Hash (Fraud Signal) + near-duplicate (pHash)
        img_hash = compute_sha256(file_bytes)
        p_hash = compute_perceptual_hash(file_bytes)
        dup_q = await session.execute(
            select(func.count(ClaimImageModel.id)).where(ClaimImageModel.file_hash == img_hash)
        )
        duplicate_count = dup_q.scalar_one() or 0
        is_duplicate = duplicate_count > 0
        if p_hash and not is_duplicate:
            ph_q = await session.execute(
                select(ClaimImageModel.perceptual_hash).where(
                    ClaimImageModel.perceptual_hash.is_not(None)
                )
            )
            for (existing_ph,) in ph_q.all():
                if hamming_distance(existing_ph, p_hash) <= 5:
                    is_duplicate = True
                    break

        # Save image file to local uploads directory (basename only — block path traversal)
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        safe_name = os.path.basename(filename or "upload.jpg").replace("\x00", "")
        if not safe_name or safe_name in (".", ".."):
            safe_name = "upload.jpg"
        saved_filename = f"{claim_id}_{img_hash[:10]}_{safe_name}"
        saved_path = os.path.join(settings.UPLOAD_DIR, saved_filename)
        # Defense in depth: resolved path must stay under UPLOAD_DIR
        upload_root = os.path.abspath(settings.UPLOAD_DIR)
        if not os.path.abspath(saved_path).startswith(upload_root + os.sep):
            raise ValueError("Invalid upload path.")
        with open(saved_path, "wb") as f:
            f.write(file_bytes)

        # 4. Vision Observation (AI analyzes physical properties ONLY)
        claim.status = ClaimStatus.IMAGE_ANALYZING.value
        await session.commit()

        industry = await self._industry_for_mall(session, claim.mall_id)
        observation = await self.ai_router.analyze_claim_image(file_bytes, detected_mime, industry)

        image_record = ClaimImageModel(
            id=str(uuid.uuid4()),
            claim_id=claim_id,
            file_path=saved_path,
            file_hash=img_hash,
            role=role or "primary",
            is_primary=(role in (None, "primary", "primary")),
            perceptual_hash=p_hash,
            exif_json=json.dumps(
                {**extract_image_metadata(file_bytes), "ai_suspicion_score": ai_generated_suspicion(extract_image_metadata(file_bytes))},
                ensure_ascii=False,
            ),
            defect_type=observation.defect_type.value,
            damage_ratio=observation.damage_ratio_estimate,
            confidence=observation.confidence,
            evidence_json=json.dumps(observation.visible_evidence, ensure_ascii=False),
            image_quality=observation.image_quality.value,
        )
        session.add(image_record)

        # 4b. Aggregate multi-image evidence bundle (max damage, min confidence,
        # worst quality). Evaluation uses the aggregate, not just the latest image.
        agg_images_q = await session.execute(
            select(ClaimImageModel).where(ClaimImageModel.claim_id == claim_id)
        )
        agg_observations: list[ClaimVisionObservation] = []
        for img in agg_images_q.scalars().all():
            try:
                dt = DefectType(img.defect_type) if img.defect_type else observation.defect_type
            except ValueError:
                dt = observation.defect_type
            try:
                iq = ImageQuality(img.image_quality) if img.image_quality else observation.image_quality
            except ValueError:
                iq = observation.image_quality
            agg_observations.append(
                ClaimVisionObservation(
                    defect_type=dt,
                    affected_items=observation.affected_items,
                    damage_ratio_estimate=int(img.damage_ratio or 0),
                    confidence=float(img.confidence or 0.0),
                    visible_evidence=json.loads(img.evidence_json or "[]"),
                    image_quality=iq,
                )
            )
        if agg_observations:
            max_damage = max(o.damage_ratio_estimate for o in agg_observations)
            min_conf = min(o.confidence for o in agg_observations)
            quality = observation.image_quality
            for o in agg_observations:
                if o.image_quality != ImageQuality.ACCEPTABLE:
                    quality = o.image_quality
                    break
            primary_obs = max(agg_observations, key=lambda o: o.damage_ratio_estimate)
            merged_evidence = []
            for o in agg_observations:
                for ev in o.visible_evidence:
                    if ev not in merged_evidence:
                        merged_evidence.append(ev)
            observation = ClaimVisionObservation(
                defect_type=primary_obs.defect_type,
                affected_items=primary_obs.affected_items,
                damage_ratio_estimate=max_damage,
                confidence=min_conf,
                visible_evidence=merged_evidence,
                image_quality=quality,
            )

        # 5. Order Verification & History
        order = await self.order_service.get_order_details(claim.order_id)

        prior_claims_q = await session.execute(
            select(func.count(ClaimModel.id)).where(
                ClaimModel.customer_id == claim.customer_id,
                ClaimModel.id != claim_id,
            )
        )
        customer_claim_count = prior_claims_q.scalar_one() or 0

        # 6. Deterministic Policy Evaluation (Rule Engine — per-mall policy)
        claim.status = ClaimStatus.POLICY_EVALUATING.value
        policy_engine = await self._policy_engine_for_mall(session, claim.mall_id)
        decision = policy_engine.evaluate(
            order=order,
            observation=observation,
            customer_claim_count_30d=customer_claim_count,
            is_duplicate_image=is_duplicate,
            is_suspicious_image=ai_generated_suspicion(extract_image_metadata(file_bytes)) >= 70,
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

    async def finalize_claim(
        self,
        session: AsyncSession,
        claim_id: str,
    ) -> Tuple[ClaimModel, PolicyDecisionResult, ClaimVisionObservation]:
        claim_q = await session.execute(select(ClaimModel).where(ClaimModel.id == claim_id))
        claim = claim_q.scalar_one_or_none()
        if not claim:
            raise ValueError(f"Claim not found: {claim_id}")

        imgs_q = await session.execute(
            select(ClaimImageModel).where(ClaimImageModel.claim_id == claim_id)
        )
        imgs = list(imgs_q.scalars().all())
        if not imgs:
            raise ValueError("No images uploaded for this claim.")

        agg_observations = []
        for img in imgs:
            try:
                dt = DefectType(img.defect_type) if img.defect_type else DefectType.UNCLEAR
            except ValueError:
                dt = DefectType.UNCLEAR
            try:
                iq = ImageQuality(img.image_quality) if img.image_quality else ImageQuality.ACCEPTABLE
            except ValueError:
                iq = ImageQuality.ACCEPTABLE
            agg_observations.append(
                ClaimVisionObservation(
                    defect_type=dt,
                    affected_items=1,
                    damage_ratio_estimate=int(img.damage_ratio or 0),
                    confidence=float(img.confidence or 0.0),
                    visible_evidence=json.loads(img.evidence_json or "[]"),
                    image_quality=iq,
                )
            )

        max_damage = max(o.damage_ratio_estimate for o in agg_observations)
        min_conf = min(o.confidence for o in agg_observations)
        quality = ImageQuality.ACCEPTABLE
        for o in agg_observations:
            if o.image_quality != ImageQuality.ACCEPTABLE:
                quality = o.image_quality
                break
        primary_obs = max(agg_observations, key=lambda o: o.damage_ratio_estimate)
        merged_evidence = []
        for o in agg_observations:
            for ev in o.visible_evidence:
                if ev not in merged_evidence:
                    merged_evidence.append(ev)
        observation = ClaimVisionObservation(
            defect_type=primary_obs.defect_type,
            affected_items=primary_obs.affected_items,
            damage_ratio_estimate=max_damage,
            confidence=min_conf,
            visible_evidence=merged_evidence,
            image_quality=quality,
        )

        hashes = [i.file_hash for i in imgs]
        is_duplicate = len(hashes) != len(set(hashes))
        phs = [i.perceptual_hash for i in imgs if i.perceptual_hash]
        if not is_duplicate:
            for i in range(len(phs)):
                for j in range(i + 1, len(phs)):
                    if hamming_distance(phs[i], phs[j]) <= 5:
                        is_duplicate = True
                        break
                if is_duplicate:
                    break
        is_suspicious = False
        for img in imgs:
            try:
                meta = json.loads(img.exif_json or "{}")
            except Exception:
                meta = {}
            if ai_generated_suspicion(meta) >= 70:
                is_suspicious = True
                break

        order = await self.order_service.get_order_details(claim.order_id)
        prior_claims_q = await session.execute(
            select(func.count(ClaimModel.id)).where(
                ClaimModel.customer_id == claim.customer_id,
                ClaimModel.id != claim_id,
            )
        )
        customer_claim_count = prior_claims_q.scalar_one() or 0

        claim.status = ClaimStatus.POLICY_EVALUATING.value
        policy_engine = await self._policy_engine_for_mall(session, claim.mall_id)
        decision = policy_engine.evaluate(
            order=order,
            observation=observation,
            customer_claim_count_30d=customer_claim_count,
            is_duplicate_image=is_duplicate,
            is_suspicious_image=is_suspicious,
        )

        if decision.decision in (PolicyDecisionType.FULL_REFUND, PolicyDecisionType.PARTIAL_REFUND):
            claim.status = ClaimStatus.AUTO_APPROVED.value
            claim.refund_amount = decision.calculated_amount or 0
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
        elif decision.decision == PolicyDecisionType.REJECT:
            claim.status = ClaimStatus.REJECTED.value

        await session.commit()
        await session.refresh(claim)
        return claim, decision, observation
