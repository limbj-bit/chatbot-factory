"""Drive AS scenario state machine and channel mutations; handoff notifies store staff."""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.as_channel_factory import resolve_as_ports
from app.application.notification_service import notification_service
from app.domain.as_scenarios.machine import AsScenarioMachine, start_scenario
from app.domain.as_scenarios.models import (
    AsIntent,
    AsScenarioEvent,
    AsScenarioState,
    AsScenarioStatus,
)
from app.domain.ports.channel_port import AsMutationPort, OrderChannelPort


class AsScenarioService:
    def __init__(
        self,
        order_port: Optional[OrderChannelPort] = None,
        mutation_port: Optional[AsMutationPort] = None,
    ):
        # Explicit ports = unit tests / forced mock. None = resolve per mall at apply().
        self._order_override = order_port
        self._mutation_override = mutation_port

    def begin(self, mall_id: str, intent: AsIntent) -> AsScenarioState:
        return start_scenario(mall_id, intent)

    async def _ports(
        self, session: AsyncSession, mall_id: str
    ) -> Tuple[OrderChannelPort, AsMutationPort]:
        if self._order_override is not None:
            mut = self._mutation_override or self._order_override
            return self._order_override, mut  # type: ignore[return-value]
        return await resolve_as_ports(session, mall_id)

    async def apply(
        self,
        session: AsyncSession,
        state: AsScenarioState,
        **step_kwargs: Any,
    ) -> Tuple[AsScenarioState, List[AsScenarioEvent], str]:
        """Advance machine; on EXECUTE call Mock/real Cafe24; on HANDOFF alert merchant."""
        orders, mutations = await self._ports(session, state.mall_id)
        machine = AsScenarioMachine(state)
        events = machine.step(**step_kwargs)
        state = machine.state

        # Enrich LIST_LINES with order items (live lookup when Cafe24 connected)
        if (
            state.status == AsScenarioStatus.LIST_LINES
            and state.slots.order_id
            and not step_kwargs.get("available_line_ids")
        ):
            order = await orders.get_order(state.slots.order_id)
            if order is None:
                events = machine.step(force_handoff="order_not_found")
                state = machine.state
            else:
                line_ids = [it.item_id for it in order.items]
                events = machine.step(available_line_ids=line_ids)
                state = machine.state
                names = ", ".join(
                    f"{it.product_name}({it.item_id}) x{it.quantity}" for it in order.items
                )
                state.bot_prompt = f"주문 상품: {names}. 반품/교환할 상품을 알려 주세요."

        if state.status == AsScenarioStatus.EXECUTE:
            ok, err = await self._run_mutation(mutations, state)
            events = machine.step(execute_ok=ok, execute_error=err)
            state = machine.state

        if state.status == AsScenarioStatus.HANDOFF:
            await self._notify_staff(session, state)
            if not any(e.type == "handoff" for e in events):
                events.append(
                    AsScenarioEvent(
                        type="handoff",
                        payload={"reason": state.handoff_reason, "state": state.to_dict()},
                    )
                )

        return state, events, state.bot_prompt

    async def _run_mutation(
        self, mutations: AsMutationPort, state: AsScenarioState
    ) -> Tuple[bool, Optional[str]]:
        key = f"as-{state.intent.value}-{state.slots.order_id}-{uuid.uuid4().hex[:8]}"
        reason = state.slots.reason or state.slots.reason_code or "customer_request"
        try:
            if state.intent == AsIntent.CANCEL:
                ok = await mutations.cancel_order(
                    state.slots.order_id or "", reason, key
                )
            elif state.intent == AsIntent.EXCHANGE:
                ok = await mutations.request_exchange(
                    state.slots.order_id or "",
                    list(state.slots.line_ids),
                    state.slots.exchange_option or "미지정",
                    reason,
                    key,
                )
            else:
                ok = await mutations.request_partial_return(
                    state.slots.order_id or "",
                    list(state.slots.line_ids),
                    dict(state.slots.quantities),
                    reason,
                    key,
                )
            return bool(ok), None if ok else "mutation_rejected"
        except Exception as e:
            return False, f"{type(e).__name__}:{e}"

    async def _notify_staff(self, session: AsyncSession, state: AsScenarioState) -> None:
        from app.api.staff_inbox import staff_inbox_token
        from app.core.config import settings

        summary = (
            f"의도={state.intent.value} 주문={state.slots.order_id} "
            f"사유={state.handoff_reason or state.slots.reason}"
        )
        key = staff_inbox_token(state.mall_id)
        path = f"/staff/{state.mall_id}/inbox?key={key}"
        base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
        ticket_url = f"{base}{path}" if base else path
        await notification_service.notify_merchant_alert(
            session,
            mall_id=state.mall_id,
            alert_type="as_handoff",
            title="고객 AS 상담 인수 요청",
            message=summary,
            claim_id=state.slots.photo_claim_id,
            extra_data={"scenario": state.to_dict()},
            ticket_url=ticket_url,
        )


as_scenario_service = AsScenarioService()
