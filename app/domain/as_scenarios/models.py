from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AsIntent(str, Enum):
    LOOKUP = "lookup"
    CANCEL = "cancel"
    EXCHANGE = "exchange"
    RETURN_FULL = "return_full"
    PARTIAL_RETURN = "partial_return"
    HANDOFF = "handoff"
    UNKNOWN = "unknown"


class AsScenarioStatus(str, Enum):
    """Conversation step inside an AS scenario."""

    IDENTIFY_ORDER = "identify_order"
    LIST_LINES = "list_lines"
    SELECT_SCOPE = "select_scope"
    COLLECT_REASON = "collect_reason"
    COLLECT_PHOTO = "collect_photo"
    CONFIRM = "confirm"
    EXECUTE = "execute"
    DONE = "done"
    HANDOFF = "handoff"


@dataclass
class AsSlots:
    order_id: Optional[str] = None
    line_ids: List[str] = field(default_factory=list)
    quantities: Dict[str, int] = field(default_factory=dict)
    reason: Optional[str] = None
    reason_code: Optional[str] = None  # change_of_mind | defect | wrong_item | other
    exchange_option: Optional[str] = None
    pickup_method: Optional[str] = None  # courier_pickup | customer_ship
    photo_claim_id: Optional[str] = None
    needs_photo: bool = False


@dataclass
class AsScenarioState:
    mall_id: str
    intent: AsIntent
    status: AsScenarioStatus = AsScenarioStatus.IDENTIFY_ORDER
    slots: AsSlots = field(default_factory=AsSlots)
    bot_prompt: str = ""
    last_error: Optional[str] = None
    handoff_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mall_id": self.mall_id,
            "intent": self.intent.value,
            "status": self.status.value,
            "slots": {
                "order_id": self.slots.order_id,
                "line_ids": list(self.slots.line_ids),
                "quantities": dict(self.slots.quantities),
                "reason": self.slots.reason,
                "reason_code": self.slots.reason_code,
                "exchange_option": self.slots.exchange_option,
                "pickup_method": self.slots.pickup_method,
                "photo_claim_id": self.slots.photo_claim_id,
                "needs_photo": self.slots.needs_photo,
            },
            "bot_prompt": self.bot_prompt,
            "last_error": self.last_error,
            "handoff_reason": self.handoff_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AsScenarioState":
        slots_raw = data.get("slots") or {}
        slots = AsSlots(
            order_id=slots_raw.get("order_id"),
            line_ids=list(slots_raw.get("line_ids") or []),
            quantities=dict(slots_raw.get("quantities") or {}),
            reason=slots_raw.get("reason"),
            reason_code=slots_raw.get("reason_code"),
            exchange_option=slots_raw.get("exchange_option"),
            pickup_method=slots_raw.get("pickup_method"),
            photo_claim_id=slots_raw.get("photo_claim_id"),
            needs_photo=bool(slots_raw.get("needs_photo")),
        )
        return cls(
            mall_id=str(data.get("mall_id") or ""),
            intent=AsIntent(data.get("intent") or AsIntent.UNKNOWN.value),
            status=AsScenarioStatus(data.get("status") or AsScenarioStatus.IDENTIFY_ORDER.value),
            slots=slots,
            bot_prompt=str(data.get("bot_prompt") or ""),
            last_error=data.get("last_error"),
            handoff_reason=data.get("handoff_reason"),
        )


@dataclass(frozen=True)
class AsScenarioEvent:
    """Side-effect hint for application layer (notify staff, call Cafe24, etc.)."""

    type: str  # prompt | execute | handoff | done
    payload: Dict[str, Any] = field(default_factory=dict)
