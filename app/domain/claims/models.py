from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional
import uuid


class ClaimStatus(str, Enum):
    RECEIVED = "RECEIVED"
    ORDER_VERIFIED = "ORDER_VERIFIED"
    IMAGE_ANALYZING = "IMAGE_ANALYZING"
    IMAGE_RETAKE_REQUIRED = "IMAGE_RETAKE_REQUIRED"
    POLICY_EVALUATING = "POLICY_EVALUATING"
    AUTO_APPROVED = "AUTO_APPROVED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    UNKNOWN_EXTERNAL_STATE = "UNKNOWN_EXTERNAL_STATE"


class ClaimType(str, Enum):
    FRESH_DEFECT = "fresh_defect"
    WRONG_DELIVERY = "wrong_delivery"
    MISSING_ITEM = "missing_item"
    OTHER = "other"


class DefectType(str, Enum):
    MOLD = "mold"
    ROT = "rot"
    BRUISE = "bruise"
    CRUSH_DAMAGE = "crush_damage"
    COSMETIC_DEFECT = "cosmetic_defect"
    NORMAL = "normal"
    UNCLEAR = "unclear"


class ImageQuality(str, Enum):
    ACCEPTABLE = "acceptable"
    TOO_DARK = "too_dark"
    BLURRY = "blurry"
    OCCLUDED = "occluded"
    INVALID = "invalid"


@dataclass(frozen=True)
class ClaimVisionObservation:
    defect_type: DefectType
    affected_items: int
    damage_ratio_estimate: int  # 0 to 100 percentage
    confidence: float          # 0.0 to 1.0
    visible_evidence: List[str]
    image_quality: ImageQuality

    def is_acceptable_quality(self) -> bool:
        return self.image_quality == ImageQuality.ACCEPTABLE

    def is_reliable(self, min_confidence: float = 0.70) -> bool:
        return self.is_acceptable_quality() and self.confidence >= min_confidence and self.defect_type != DefectType.UNCLEAR


@dataclass
class ClaimImage:
    id: str
    claim_id: str
    file_path: str
    file_hash: str
    is_primary: bool = True
    observation: Optional[ClaimVisionObservation] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ClaimEvent:
    id: str
    claim_id: str
    event_type: str
    from_status: Optional[ClaimStatus]
    to_status: ClaimStatus
    actor: str  # e.g., "SYSTEM", "RULE_ENGINE", "ADMIN"
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Claim:
    id: str
    order_id: str
    customer_id: str
    claim_type: ClaimType
    description: str
    status: ClaimStatus = ClaimStatus.RECEIVED
    idempotency_key: Optional[str] = None
    images: List[ClaimImage] = field(default_factory=list)
    events: List[ClaimEvent] = field(default_factory=list)
    refund_amount: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def transition_to(self, new_status: ClaimStatus, actor: str, reason: str, payload: Optional[dict[str, Any]] = None) -> ClaimEvent:
        event = ClaimEvent(
            id=str(uuid.uuid4()),
            claim_id=self.id,
            event_type=f"TRANSITION_TO_{new_status.value}",
            from_status=self.status,
            to_status=new_status,
            actor=actor,
            reason=reason,
            payload=payload or {},
            created_at=datetime.now(timezone.utc),
        )
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        self.events.append(event)
        return event
