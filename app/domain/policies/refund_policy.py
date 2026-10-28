from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.domain.claims.models import DefectType, ImageQuality, ClaimVisionObservation
from app.domain.orders.models import Order
from app.domain.policies.models import (
    PolicyConfig,
    PolicyDecisionResult,
    PolicyDecisionType,
    PolicyReasonCode,
)


class RefundPolicyEngine:
    """Pure deterministic domain service for evaluating refund decisions.
    
    Zero dependencies on AI providers, databases, or HTTP frameworks.
    AI delivers observations; this engine makes deterministic decisions.
    """

    def __init__(self, config: Optional[PolicyConfig] = None):
        self.config = config or PolicyConfig()

    def evaluate(
        self,
        order: Optional[Order],
        observation: ClaimVisionObservation,
        customer_claim_count_30d: int = 0,
        is_duplicate_image: bool = False,
        now: Optional[datetime] = None,
    ) -> PolicyDecisionResult:
        current_time = now or datetime.now(timezone.utc)

        # 1. Order Existence & Delivery Check
        if order is None:
            return PolicyDecisionResult(
                decision=PolicyDecisionType.MANUAL_REVIEW,
                reason_code=PolicyReasonCode.ORDER_NOT_FOUND,
                requires_manual_review=True,
                refund_ratio=0,
                explanation="Order could not be verified in the channel.",
                suggested_customer_message="주문 정보를 확인할 수 없어 담당자가 확인 후 연락드리겠습니다.",
            )

        if not order.is_delivered():
            return PolicyDecisionResult(
                decision=PolicyDecisionType.REJECT,
                reason_code=PolicyReasonCode.ORDER_NOT_DELIVERED,
                requires_manual_review=False,
                refund_ratio=0,
                explanation="Order is not delivered yet.",
                suggested_customer_message="배송 완료 전인 주문입니다. 배송 완료 후 상품에 이상이 있는 경우 다시 접수해 주세요.",
            )

        # 2. Claim Window Check
        if order.delivered_at:
            # Ensure timezone awareness
            delivered_at = order.delivered_at
            if delivered_at.tzinfo is None:
                delivered_at = delivered_at.replace(tzinfo=timezone.utc)

            elapsed = current_time - delivered_at
            if elapsed.total_seconds() > self.config.max_claim_days * 86400:
                return PolicyDecisionResult(
                    decision=PolicyDecisionType.REJECT,
                    reason_code=PolicyReasonCode.EXPIRED_WINDOW,
                    requires_manual_review=False,
                    refund_ratio=0,
                    explanation=f"Claim submitted after {self.config.max_claim_days} days limit.",
                    suggested_customer_message=f"신선식품 특성상 배송 완료 후 {self.config.max_claim_days}일 이내에만 접수 가능합니다.",
                )

        # 3. Fraud / Abuse Signal Check
        if is_duplicate_image:
            return PolicyDecisionResult(
                decision=PolicyDecisionType.MANUAL_REVIEW,
                reason_code=PolicyReasonCode.SUSPICIOUS_CLAIM,
                requires_manual_review=True,
                refund_ratio=0,
                explanation="Duplicate image submission detected.",
                suggested_customer_message="제출하신 사진에 대한 정밀 확인이 필요하여 담당 부서에서 검토 후 안내해 드리겠습니다.",
            )

        if customer_claim_count_30d >= 3:
            return PolicyDecisionResult(
                decision=PolicyDecisionType.MANUAL_REVIEW,
                reason_code=PolicyReasonCode.SUSPICIOUS_CLAIM,
                requires_manual_review=True,
                refund_ratio=0,
                explanation=f"High claim frequency ({customer_claim_count_30d} claims in 30 days).",
                suggested_customer_message="클레임 이력 조회를 위해 담당 상담원이 확인 후 신속히 연락드리겠습니다.",
            )

        # 4. Image Quality Gate
        if not observation.is_acceptable_quality():
            return PolicyDecisionResult(
                decision=PolicyDecisionType.RETAKE_IMAGE,
                reason_code=PolicyReasonCode.POOR_IMAGE_QUALITY,
                requires_manual_review=False,
                refund_ratio=0,
                explanation=f"Image quality is {observation.image_quality.value}.",
                suggested_customer_message="사진이 흐리거나 어두워 손상 확인이 어렵습니다. 밝은 곳에서 과일 전체와 손상 부위를 다시 촬영해 주세요.",
            )

        # 5. Low Confidence or Unclear Defect Gate
        if observation.confidence < self.config.min_vision_confidence:
            return PolicyDecisionResult(
                decision=PolicyDecisionType.MANUAL_REVIEW,
                reason_code=PolicyReasonCode.CONFIDENCE_TOO_LOW,
                requires_manual_review=True,
                refund_ratio=0,
                explanation=f"Confidence {observation.confidence:.2f} below threshold {self.config.min_vision_confidence}.",
                suggested_customer_message="사진 판독 신뢰도가 기준치 미만이어서 전문 상담원이 직접 확인 후 안내해 드리겠습니다.",
            )

        if observation.defect_type == DefectType.UNCLEAR:
            return PolicyDecisionResult(
                decision=PolicyDecisionType.MANUAL_REVIEW,
                reason_code=PolicyReasonCode.UNCLEAR_DEFECT,
                requires_manual_review=True,
                refund_ratio=0,
                explanation="Defect type could not be clearly classified by vision provider.",
                suggested_customer_message="손상 유형이 명확하지 않아 담당자가 직접 확인 후 신속히 처리해 드리겠습니다.",
            )

        # 6. Normal Product Check
        if observation.defect_type == DefectType.NORMAL and observation.damage_ratio_estimate == 0:
            return PolicyDecisionResult(
                decision=PolicyDecisionType.REJECT,
                reason_code=PolicyReasonCode.NORMAL_PRODUCT,
                requires_manual_review=False,
                refund_ratio=0,
                explanation="Normal fresh product observed with 0% damage.",
                suggested_customer_message="사진상 상품에 변질이나 손상이 발견되지 않았습니다. 추가 증상이 있다면 손상 부위를 가까이 촬영해 다시 접수해 주세요.",
            )

        # 7. Cosmetic Defect Check
        if observation.defect_type == DefectType.COSMETIC_DEFECT and observation.damage_ratio_estimate < self.config.partial_refund_damage_ratio:
            return PolicyDecisionResult(
                decision=PolicyDecisionType.REJECT,
                reason_code=PolicyReasonCode.COSMETIC_DEFECT,
                requires_manual_review=False,
                refund_ratio=0,
                explanation="Minor cosmetic defect within acceptable agricultural tolerance.",
                suggested_customer_message="신선 농산물 특성상 발생할 수 있는 경미한 외관 흠집으로 확인되어 환불 대상에 해당하지 않습니다.",
            )

        # 8. Damage Ratio Threshold Evaluation
        damage = observation.damage_ratio_estimate

        if damage >= self.config.full_refund_damage_ratio:
            return PolicyDecisionResult(
                decision=PolicyDecisionType.FULL_REFUND,
                reason_code=PolicyReasonCode.SEVERE_DAMAGE,
                requires_manual_review=False,
                refund_ratio=100,
                explanation=f"Severe damage ratio {damage}% >= {self.config.full_refund_damage_ratio}%.",
                suggested_customer_message="상품의 손상도가 심각한 상태로 확인되어 전액 환불 처리가 접수되었습니다.",
                calculated_amount=order.total_amount,
            )

        if damage >= self.config.partial_refund_damage_ratio:
            partial_amount = int(order.total_amount * (damage / 100.0))
            return PolicyDecisionResult(
                decision=PolicyDecisionType.PARTIAL_REFUND,
                reason_code=PolicyReasonCode.PARTIAL_DAMAGE,
                requires_manual_review=False,
                refund_ratio=damage,
                explanation=f"Partial damage ratio {damage}% between {self.config.partial_refund_damage_ratio}% and {self.config.full_refund_damage_ratio}%.",
                suggested_customer_message=f"상품 손상률(약 {damage}%)에 따라 부분 환불 처리가 접수되었습니다.",
                calculated_amount=partial_amount,
            )

        # damage < partial_refund_damage_ratio (e.g. 0% ~ 9%)
        return PolicyDecisionResult(
            decision=PolicyDecisionType.REJECT,
            reason_code=PolicyReasonCode.PARTIAL_DAMAGE,
            requires_manual_review=False,
            refund_ratio=0,
            explanation=f"Damage ratio {damage}% below partial refund threshold {self.config.partial_refund_damage_ratio}%.",
            suggested_customer_message=f"손상 면적(약 {damage}%)이 최소 보상 기준({self.config.partial_refund_damage_ratio}%)에 미달하여 환불이 어렵습니다.",
        )
