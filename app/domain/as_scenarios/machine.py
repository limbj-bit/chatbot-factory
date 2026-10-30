from __future__ import annotations

from dataclasses import replace
from typing import List, Optional, Tuple

from app.domain.as_scenarios.models import (
    AsIntent,
    AsScenarioEvent,
    AsScenarioState,
    AsScenarioStatus,
    AsSlots,
)

# Reason codes that require a damage photo before confirm.
_DEFECT_CODES = frozenset({"defect", "wrong_item", "damaged"})


def start_scenario(mall_id: str, intent: AsIntent) -> AsScenarioState:
    prompts = {
        AsIntent.CANCEL: "취소하실 주문번호를 알려 주세요. (예: ORD-NORMAL 또는 20261028-0000012)",
        AsIntent.EXCHANGE: "교환하실 주문번호를 알려 주세요.",
        AsIntent.PARTIAL_RETURN: "일부만 반품하실 주문번호를 알려 주세요.",
        AsIntent.RETURN_FULL: "반품하실 주문번호를 알려 주세요.",
        AsIntent.LOOKUP: "조회하실 주문번호를 알려 주세요.",
        AsIntent.HANDOFF: "상점 직원에게 연결해 드릴게요. 문의 내용을 짧게 남겨 주세요.",
    }
    if intent == AsIntent.HANDOFF:
        return AsScenarioState(
            mall_id=mall_id,
            intent=intent,
            status=AsScenarioStatus.HANDOFF,
            bot_prompt=prompts[intent],
            handoff_reason="customer_requested",
        )
    return AsScenarioState(
        mall_id=mall_id,
        intent=intent,
        status=AsScenarioStatus.IDENTIFY_ORDER,
        bot_prompt=prompts.get(intent, "주문번호를 알려 주세요."),
    )


def advance(
    state: AsScenarioState,
    *,
    order_id: Optional[str] = None,
    line_ids: Optional[List[str]] = None,
    quantities: Optional[dict] = None,
    reason_code: Optional[str] = None,
    reason: Optional[str] = None,
    exchange_option: Optional[str] = None,
    pickup_method: Optional[str] = None,
    photo_claim_id: Optional[str] = None,
    confirm: Optional[bool] = None,
    execute_ok: Optional[bool] = None,
    execute_error: Optional[str] = None,
    force_handoff: Optional[str] = None,
    available_line_ids: Optional[List[str]] = None,
) -> Tuple[AsScenarioState, List[AsScenarioEvent]]:
    """Pure transition. Application layer supplies order lines / API results."""
    events: List[AsScenarioEvent] = []

    if force_handoff:
        s = replace(
            state,
            status=AsScenarioStatus.HANDOFF,
            handoff_reason=force_handoff,
            bot_prompt="처리가 어려워 상점 직원에게 전달했습니다. 직원이 확인 후 연락드릴게요.",
        )
        events.append(
            AsScenarioEvent(
                type="handoff",
                payload={"reason": force_handoff, "state": s.to_dict()},
            )
        )
        return s, events

    status = state.status
    slots = state.slots

    if status == AsScenarioStatus.DONE:
        return state, events

    if status == AsScenarioStatus.HANDOFF:
        events.append(
            AsScenarioEvent(type="handoff", payload={"reason": state.handoff_reason or "handoff"})
        )
        return state, events

    if status == AsScenarioStatus.IDENTIFY_ORDER:
        oid = (order_id or slots.order_id or "").strip()
        if not oid:
            s = replace(state, bot_prompt="주문번호가 필요해요. 다시 입력해 주세요.")
            events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
            return s, events
        new_slots = replace(slots, order_id=oid)
        # Cancel can skip line pick if whole order; others list lines.
        if state.intent == AsIntent.CANCEL:
            s = replace(
                state,
                slots=new_slots,
                status=AsScenarioStatus.COLLECT_REASON,
                bot_prompt="취소 사유를 알려 주세요. (변심 / 주문실수 / 기타)",
            )
        else:
            s = replace(
                state,
                slots=new_slots,
                status=AsScenarioStatus.LIST_LINES,
                bot_prompt="주문 상품 목록을 확인했습니다. 대상 상품을 선택해 주세요.",
            )
        events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
        return s, events

    if status == AsScenarioStatus.LIST_LINES:
        s = replace(
            state,
            status=AsScenarioStatus.SELECT_SCOPE,
            bot_prompt="반품/교환할 상품 번호와 수량을 알려 주세요. (예: 1번 1개)",
        )
        events.append(
            AsScenarioEvent(
                type="prompt",
                payload={"text": s.bot_prompt, "lines": available_line_ids or []},
            )
        )
        return s, events

    if status == AsScenarioStatus.SELECT_SCOPE:
        lids = line_ids if line_ids is not None else slots.line_ids
        qtys = quantities if quantities is not None else slots.quantities
        if state.intent in (AsIntent.PARTIAL_RETURN, AsIntent.EXCHANGE) and not lids:
            s = replace(state, bot_prompt="대상 상품을 선택해 주세요.")
            events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
            return s, events
        if available_line_ids is not None and lids:
            bad = [x for x in lids if x not in available_line_ids]
            if bad:
                s = replace(state, bot_prompt="주문에 없는 상품이 포함되어 있어요. 다시 선택해 주세요.")
                events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
                return s, events
        new_slots = replace(slots, line_ids=list(lids or []), quantities=dict(qtys or {}))
        if state.intent == AsIntent.EXCHANGE:
            s = replace(
                state,
                slots=new_slots,
                status=AsScenarioStatus.COLLECT_REASON,
                bot_prompt="원하시는 교환 옵션(사이즈/색상 등)과 사유를 알려 주세요.",
            )
        else:
            s = replace(
                state,
                slots=new_slots,
                status=AsScenarioStatus.COLLECT_REASON,
                bot_prompt="사유를 알려 주세요. (변심 / 불량·파손 / 오배송 / 기타)",
            )
        events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
        return s, events

    if status == AsScenarioStatus.COLLECT_REASON:
        code = (reason_code or slots.reason_code or "").strip().lower()
        text = (reason or slots.reason or "").strip()
        # Normalize Korean shortcuts
        if not code and text:
            if "불량" in text or "파손" in text:
                code = "defect"
            elif "오배송" in text or "잘못" in text:
                code = "wrong_item"
            elif "변심" in text or "취소" in text:
                code = "change_of_mind"
            else:
                code = "other"
        if not code and not text:
            s = replace(state, bot_prompt="사유를 한 줄로 알려 주세요.")
            events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
            return s, events
        needs_photo = code in _DEFECT_CODES
        new_slots = replace(
            slots,
            reason_code=code or "other",
            reason=text or code,
            needs_photo=needs_photo,
            exchange_option=exchange_option or slots.exchange_option,
            pickup_method=pickup_method or slots.pickup_method,
        )
        if state.intent == AsIntent.EXCHANGE and not (exchange_option or slots.exchange_option):
            # keep collecting if exchange option missing but reason given — still ok to proceed with prompt
            if not exchange_option and not slots.exchange_option:
                new_slots = replace(new_slots, exchange_option=text or "미지정")
        if needs_photo and not (photo_claim_id or slots.photo_claim_id):
            s = replace(
                state,
                slots=new_slots,
                status=AsScenarioStatus.COLLECT_PHOTO,
                bot_prompt="불량·파손 확인을 위해 상품 사진을 올려 주세요.",
            )
            events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
            return s, events
        s = replace(
            state,
            slots=new_slots,
            status=AsScenarioStatus.CONFIRM,
            bot_prompt=_confirm_prompt(state.intent, new_slots),
        )
        events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
        return s, events

    if status == AsScenarioStatus.COLLECT_PHOTO:
        pid = photo_claim_id or slots.photo_claim_id
        if not pid:
            s = replace(state, bot_prompt="사진이 필요해요. 이미지를 첨부해 주세요.")
            events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
            return s, events
        new_slots = replace(slots, photo_claim_id=pid, needs_photo=True)
        s = replace(
            state,
            slots=new_slots,
            status=AsScenarioStatus.CONFIRM,
            bot_prompt=_confirm_prompt(state.intent, new_slots),
        )
        events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
        return s, events

    if status == AsScenarioStatus.CONFIRM:
        if confirm is True:
            s = replace(
                state,
                status=AsScenarioStatus.EXECUTE,
                bot_prompt="접수 중입니다. 잠시만 기다려 주세요.",
            )
            events.append(
                AsScenarioEvent(
                    type="execute",
                    payload={"intent": state.intent.value, "slots": s.slots.__dict__},
                )
            )
            return s, events
        if confirm is False:
            s = replace(
                state,
                status=AsScenarioStatus.HANDOFF,
                handoff_reason="customer_declined_confirm",
                bot_prompt="접수를 취소했습니다. 필요하시면 상점 직원에게 연결해 드릴게요.",
            )
            events.append(
                AsScenarioEvent(
                    type="handoff",
                    payload={"reason": "customer_declined_confirm", "state": s.to_dict()},
                )
            )
            return s, events
        s = replace(state, bot_prompt=_confirm_prompt(state.intent, slots) + " (예/아니오로 답해 주세요)")
        events.append(AsScenarioEvent(type="prompt", payload={"text": s.bot_prompt}))
        return s, events

    if status == AsScenarioStatus.EXECUTE:
        if execute_ok is True:
            s = replace(
                state,
                status=AsScenarioStatus.DONE,
                bot_prompt=_done_prompt(state.intent, slots),
                last_error=None,
            )
            events.append(AsScenarioEvent(type="done", payload={"state": s.to_dict()}))
            return s, events
        if execute_ok is False:
            reason = execute_error or "execute_failed"
            s = replace(
                state,
                status=AsScenarioStatus.HANDOFF,
                handoff_reason=reason,
                last_error=reason,
                bot_prompt="자동 접수에 실패해 상점 직원에게 전달했습니다.",
            )
            events.append(
                AsScenarioEvent(
                    type="handoff",
                    payload={"reason": reason, "state": s.to_dict()},
                )
            )
            return s, events
        # Waiting for application layer to call channel API
        events.append(
            AsScenarioEvent(
                type="execute",
                payload={"intent": state.intent.value, "slots": slots.__dict__},
            )
        )
        return state, events

    return state, events


def _confirm_prompt(intent: AsIntent, slots: AsSlots) -> str:
    oid = slots.order_id or "?"
    if intent == AsIntent.CANCEL:
        return f"주문 {oid} 취소를 진행할까요?"
    if intent == AsIntent.EXCHANGE:
        opt = slots.exchange_option or "요청 옵션"
        return f"주문 {oid}을(를) '{opt}'(으)로 교환 접수할까요?"
    lines = ", ".join(slots.line_ids) if slots.line_ids else "전체"
    return f"주문 {oid} / 상품 {lines} 반품 접수할까요? 사유: {slots.reason or slots.reason_code}"


def _done_prompt(intent: AsIntent, slots: AsSlots) -> str:
    oid = slots.order_id or "?"
    if intent == AsIntent.CANCEL:
        return f"주문 {oid} 취소가 접수되었습니다."
    if intent == AsIntent.EXCHANGE:
        return f"주문 {oid} 교환이 접수되었습니다. 상점 확인 후 진행됩니다."
    return f"주문 {oid} 반품이 접수되었습니다. 검수 후 안내드릴 수 있습니다."


class AsScenarioMachine:
    """Thin OOP wrapper around advance() for callers that prefer an object."""

    def __init__(self, state: AsScenarioState):
        self.state = state

    @classmethod
    def start(cls, mall_id: str, intent: AsIntent) -> "AsScenarioMachine":
        return cls(start_scenario(mall_id, intent))

    def step(self, **kwargs) -> List[AsScenarioEvent]:
        self.state, events = advance(self.state, **kwargs)
        return events
