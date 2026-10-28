from datetime import datetime, timedelta, timezone
import pytest

from app.domain.claims.models import DefectType, ImageQuality, ClaimVisionObservation
from app.domain.orders.models import Order, OrderChannel, OrderItem, OrderStatus
from app.domain.policies.models import (
    PolicyConfig,
    PolicyDecisionType,
    PolicyReasonCode,
)
from app.domain.policies.refund_policy import RefundPolicyEngine


@pytest.fixture
def policy_engine() -> RefundPolicyEngine:
    return RefundPolicyEngine(
        PolicyConfig(
            full_refund_damage_ratio=30,
            partial_refund_damage_ratio=10,
            max_claim_days=2,
            min_vision_confidence=0.70,
        )
    )


@pytest.fixture
def delivered_order() -> Order:
    now = datetime.now(timezone.utc)
    return Order(
        order_id="ORD-TEST-001",
        customer_id="CUST-100",
        mall_id="demo_mall",
        status=OrderStatus.DELIVERED,
        items=[
            OrderItem(
                item_id="PROD-STRAWBERRY",
                product_name="설향 딸기 1kg",
                quantity=1,
                unit_price=20000,
            )
        ],
        total_amount=20000,
        channel=OrderChannel.CAFE24,
        delivered_at=now - timedelta(hours=12),
    )


def test_boundary_damage_ratio_0(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """damage_ratio = 0 with normal product should be REJECT."""
    observation = ClaimVisionObservation(
        defect_type=DefectType.NORMAL,
        affected_items=0,
        damage_ratio_estimate=0,
        confidence=0.95,
        visible_evidence=["정상 신선 과일"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.REJECT
    assert result.reason_code == PolicyReasonCode.NORMAL_PRODUCT
    assert result.refund_ratio == 0
    assert not result.requires_manual_review


def test_boundary_damage_ratio_9(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """damage_ratio = 9 (below 10% threshold) should be REJECT."""
    observation = ClaimVisionObservation(
        defect_type=DefectType.BRUISE,
        affected_items=1,
        damage_ratio_estimate=9,
        confidence=0.88,
        visible_evidence=["경미한 표면 눌림"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.REJECT
    assert result.reason_code == PolicyReasonCode.PARTIAL_DAMAGE
    assert result.refund_ratio == 0
    assert not result.requires_manual_review


def test_boundary_damage_ratio_10(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """damage_ratio = 10 (exact partial refund threshold) should be PARTIAL_REFUND."""
    observation = ClaimVisionObservation(
        defect_type=DefectType.BRUISE,
        affected_items=1,
        damage_ratio_estimate=10,
        confidence=0.88,
        visible_evidence=["과육 눌림"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.PARTIAL_REFUND
    assert result.reason_code == PolicyReasonCode.PARTIAL_DAMAGE
    assert result.refund_ratio == 10
    assert result.calculated_amount == 2000  # 10% of 20000
    assert not result.requires_manual_review


def test_boundary_damage_ratio_29(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """damage_ratio = 29 (just below full refund threshold) should be PARTIAL_REFUND."""
    observation = ClaimVisionObservation(
        defect_type=DefectType.ROT,
        affected_items=2,
        damage_ratio_estimate=29,
        confidence=0.90,
        visible_evidence=["과육 변색 및 무름"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.PARTIAL_REFUND
    assert result.reason_code == PolicyReasonCode.PARTIAL_DAMAGE
    assert result.refund_ratio == 29
    assert result.calculated_amount == 5800  # 29% of 20000
    assert not result.requires_manual_review


def test_boundary_damage_ratio_30(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """damage_ratio = 30 (exact full refund threshold) should be FULL_REFUND."""
    observation = ClaimVisionObservation(
        defect_type=DefectType.MOLD,
        affected_items=3,
        damage_ratio_estimate=30,
        confidence=0.92,
        visible_evidence=["흰색 곰팡이 포자 군집"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.FULL_REFUND
    assert result.reason_code == PolicyReasonCode.SEVERE_DAMAGE
    assert result.refund_ratio == 100
    assert result.calculated_amount == 20000  # 100% of 20000
    assert not result.requires_manual_review


def test_boundary_damage_ratio_31(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """damage_ratio = 31 (above full refund threshold) should be FULL_REFUND."""
    observation = ClaimVisionObservation(
        defect_type=DefectType.MOLD,
        affected_items=4,
        damage_ratio_estimate=31,
        confidence=0.94,
        visible_evidence=["광범위한 곰팡이 및 과즙 유출"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.FULL_REFUND
    assert result.reason_code == PolicyReasonCode.SEVERE_DAMAGE
    assert result.refund_ratio == 100
    assert result.calculated_amount == 20000
    assert not result.requires_manual_review


def test_image_quality_gate_blurry(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """Blurry image should trigger RETAKE_IMAGE."""
    observation = ClaimVisionObservation(
        defect_type=DefectType.MOLD,
        affected_items=2,
        damage_ratio_estimate=40,
        confidence=0.90,
        visible_evidence=["흐릿한 형상"],
        image_quality=ImageQuality.BLURRY,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.RETAKE_IMAGE
    assert result.reason_code == PolicyReasonCode.POOR_IMAGE_QUALITY
    assert "다시 촬영" in result.suggested_customer_message


def test_low_confidence_triggers_manual_review(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """Confidence below 0.70 must go to MANUAL_REVIEW."""
    observation = ClaimVisionObservation(
        defect_type=DefectType.ROT,
        affected_items=1,
        damage_ratio_estimate=35,
        confidence=0.62,
        visible_evidence=["불분명한 그림자"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.MANUAL_REVIEW
    assert result.reason_code == PolicyReasonCode.CONFIDENCE_TOO_LOW
    assert result.requires_manual_review


def test_unclear_defect_triggers_manual_review(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """DefectType.UNCLEAR must go to MANUAL_REVIEW."""
    observation = ClaimVisionObservation(
        defect_type=DefectType.UNCLEAR,
        affected_items=1,
        damage_ratio_estimate=20,
        confidence=0.85,
        visible_evidence=["알 수 없는 형태"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.MANUAL_REVIEW
    assert result.reason_code == PolicyReasonCode.UNCLEAR_DEFECT
    assert result.requires_manual_review


def test_expired_claim_window(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """Delivered > 2 days ago must be REJECT due to EXPIRED_WINDOW."""
    delivered_order.delivered_at = datetime.now(timezone.utc) - timedelta(days=3)
    observation = ClaimVisionObservation(
        defect_type=DefectType.MOLD,
        affected_items=2,
        damage_ratio_estimate=40,
        confidence=0.90,
        visible_evidence=["곰팡이"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.REJECT
    assert result.reason_code == PolicyReasonCode.EXPIRED_WINDOW


def test_duplicate_image_triggers_fraud_review(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """Duplicate image hash detected should go to MANUAL_REVIEW."""
    observation = ClaimVisionObservation(
        defect_type=DefectType.MOLD,
        affected_items=3,
        damage_ratio_estimate=50,
        confidence=0.95,
        visible_evidence=["곰팡이"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation, is_duplicate_image=True)
    assert result.decision == PolicyDecisionType.MANUAL_REVIEW
    assert result.reason_code == PolicyReasonCode.SUSPICIOUS_CLAIM
    assert result.requires_manual_review


def test_order_not_delivered_rejects(policy_engine: RefundPolicyEngine, delivered_order: Order):
    """Order in shipping state should be REJECT."""
    delivered_order.status = OrderStatus.SHIPPING
    delivered_order.delivered_at = None
    observation = ClaimVisionObservation(
        defect_type=DefectType.MOLD,
        affected_items=1,
        damage_ratio_estimate=30,
        confidence=0.90,
        visible_evidence=["곰팡이"],
        image_quality=ImageQuality.ACCEPTABLE,
    )
    result = policy_engine.evaluate(delivered_order, observation)
    assert result.decision == PolicyDecisionType.REJECT
    assert result.reason_code == PolicyReasonCode.ORDER_NOT_DELIVERED
