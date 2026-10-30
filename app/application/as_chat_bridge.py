"""Parse chat turns into AS scenario steps; hold short-lived per-session state."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.as_scenario_service import as_scenario_service
from app.domain.as_scenarios.models import AsIntent, AsScenarioState, AsScenarioStatus

_ORDER_ID_RE = re.compile(r"(\d{8}-\d{7}|ORD-[A-Za-z0-9-]+)")
_LINE_RE = re.compile(r"(?:(\d+)\s*번)|(?:line[_-]?(\w+))|(ITEM[-_]?\w+)", re.I)

# session_id -> AsScenarioState.to_dict()  (process memory; OK for MVP)
_ACTIVE: Dict[str, Dict[str, Any]] = {}

_POLICY_KW = ("반품정책", "교환정책", "반품기한", "교환기한", "환불정책")


def detect_as_intent(message_text: str) -> Optional[AsIntent]:
    clean = message_text.replace(" ", "").lower()
    if any(k in clean for k in _POLICY_KW):
        return None
    if any(k in clean for k in ("상담원", "직원연결", "사람연결", "상담사", "상담연결")):
        return AsIntent.HANDOFF
    if any(k in clean for k in ("주문취소", "취소해줘", "취소하고", "결제취소", "취소해주세요")):
        return AsIntent.CANCEL
    if "교환" in clean and any(
        k in clean for k in ("해줘", "하고", "신청", "원해요", "해주세요", "하고싶", "받을래")
    ):
        return AsIntent.EXCHANGE
    if any(k in clean for k in ("일부반품", "부분반품")):
        return AsIntent.PARTIAL_RETURN
    if "반품" in clean and any(
        k in clean for k in ("해줘", "하고", "신청", "접수", "원해요", "해주세요", "하고싶")
    ):
        return AsIntent.RETURN_FULL
    return None


def get_active(session_id: str) -> Optional[AsScenarioState]:
    raw = _ACTIVE.get(session_id)
    if not raw:
        return None
    return AsScenarioState.from_dict(raw)


def clear_active(session_id: str) -> None:
    _ACTIVE.pop(session_id, None)


def _save(session_id: str, state: AsScenarioState) -> None:
    # DONE / HANDOFF end the multi-turn loop (staff already notified on HANDOFF)
    if state.status in (AsScenarioStatus.DONE, AsScenarioStatus.HANDOFF):
        clear_active(session_id)
        return
    _ACTIVE[session_id] = state.to_dict()


def parse_step_kwargs(state: AsScenarioState, message_text: str) -> Dict[str, Any]:
    text = (message_text or "").strip()
    clean = text.replace(" ", "").lower()
    kwargs: Dict[str, Any] = {}

    if state.status == AsScenarioStatus.IDENTIFY_ORDER:
        m = _ORDER_ID_RE.search(text)
        if m:
            kwargs["order_id"] = m.group(1)
        return kwargs

    if state.status == AsScenarioStatus.SELECT_SCOPE:
        if "전체" in clean or "다반품" in clean:
            kwargs["line_ids"] = list(state.slots.line_ids) or ["ALL"]
            return kwargs
        lids = []
        for m in _LINE_RE.finditer(text):
            n = m.group(1) or m.group(2) or m.group(0)
            if n:
                lids.append(str(n))
        if lids:
            kwargs["line_ids"] = lids
            kwargs["quantities"] = {lid: 1 for lid in lids}
        return kwargs

    if state.status == AsScenarioStatus.COLLECT_REASON:
        kwargs["reason"] = text
        return kwargs

    if state.status == AsScenarioStatus.COLLECT_PHOTO:
        # Text chat has no image attach here — hand off to staff / claim UI
        kwargs["force_handoff"] = "photo_required_use_claim_ui"
        return kwargs

    if state.status == AsScenarioStatus.CONFIRM:
        if any(k in clean for k in ("예", "네", "응", "확인", "진행", "좋아요", "ok", "yes")):
            kwargs["confirm"] = True
        elif any(k in clean for k in ("아니", "취소", "그만", "no", "싫")):
            kwargs["confirm"] = False
        return kwargs

    if state.status == AsScenarioStatus.HANDOFF:
        kwargs["force_handoff"] = state.handoff_reason or "customer_note"
        return kwargs

    return kwargs


async def handle_as_turn(
    session_db: AsyncSession,
    session_id: str,
    mall_id: str,
    message_text: str,
) -> Optional[Tuple[str, str]]:
    """Continue or start AS scenario. Returns (intent, bot_text) or None."""
    state = get_active(session_id)
    if state is None:
        intent = detect_as_intent(message_text)
        if intent is None:
            return None
        state = as_scenario_service.begin(mall_id, intent)
        if intent == AsIntent.HANDOFF:
            state, _, prompt = await as_scenario_service.apply(
                session_db, state, force_handoff="customer_requested"
            )
            _save(session_id, state)
            return "as_handoff", prompt or state.bot_prompt
        # If first message already includes order id, advance once
        kwargs = parse_step_kwargs(state, message_text)
        if kwargs:
            state, _, prompt = await as_scenario_service.apply(session_db, state, **kwargs)
            _save(session_id, state)
            return f"as_{state.intent.value}", prompt or state.bot_prompt
        _save(session_id, state)
        return f"as_{state.intent.value}", state.bot_prompt

    # Active scenario: advance
    if state.mall_id != mall_id:
        state = AsScenarioState.from_dict({**state.to_dict(), "mall_id": mall_id})

    kwargs = parse_step_kwargs(state, message_text)
    if not kwargs and state.status == AsScenarioStatus.CONFIRM:
        # Re-prompt without advancing
        return f"as_{state.intent.value}", state.bot_prompt + " (예/아니오로 답해 주세요)"

    state, events, prompt = await as_scenario_service.apply(session_db, state, **kwargs)
    _save(session_id, state)
    intent_label = "as_handoff" if state.status == AsScenarioStatus.HANDOFF else f"as_{state.intent.value}"
    if state.status == AsScenarioStatus.DONE:
        intent_label = f"as_{state.intent.value}_done"
    return intent_label, prompt or state.bot_prompt
