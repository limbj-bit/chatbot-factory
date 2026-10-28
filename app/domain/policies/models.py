from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PolicyDecisionType(str, Enum):
    FULL_REFUND = "FULL_REFUND"
    PARTIAL_REFUND = "PARTIAL_REFUND"
    REPLACEMENT = "REPLACEMENT"
    RETAKE_IMAGE = "RETAKE_IMAGE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECT = "REJECT"


class PolicyReasonCode(str, Enum):
    SEVERE_DAMAGE = "SEVERE_DAMAGE"
    PARTIAL_DAMAGE = "PARTIAL_DAMAGE"
    EXPIRED_WINDOW = "EXPIRED_WINDOW"
    POOR_IMAGE_QUALITY = "POOR_IMAGE_QUALITY"
    UNCLEAR_DEFECT = "UNCLEAR_DEFECT"
    SUSPICIOUS_CLAIM = "SUSPICIOUS_CLAIM"
    NORMAL_PRODUCT = "NORMAL_PRODUCT"
    COSMETIC_DEFECT = "COSMETIC_DEFECT"
    ORDER_NOT_DELIVERED = "ORDER_NOT_DELIVERED"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    CONFIDENCE_TOO_LOW = "CONFIDENCE_TOO_LOW"


@dataclass(frozen=True)
class PolicyConfig:
    full_refund_damage_ratio: int = 30
    partial_refund_damage_ratio: int = 10
    max_claim_days: int = 2
    min_vision_confidence: float = 0.70


@dataclass(frozen=True)
class PolicyDecisionResult:
    decision: PolicyDecisionType
    reason_code: PolicyReasonCode
    requires_manual_review: bool
    refund_ratio: int  # 0 to 100 percentage
    explanation: str
    suggested_customer_message: str
    calculated_amount: Optional[int] = None
