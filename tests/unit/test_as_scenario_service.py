from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.as_scenario_service import AsScenarioService
from app.domain.as_scenarios.models import AsIntent, AsScenarioStatus
from app.infrastructure.channels.mock_cafe24 import MockCafe24Adapter


@pytest.mark.asyncio
async def test_service_cancel_to_done_and_handoff_notifies(monkeypatch):
    mock = MockCafe24Adapter()
    svc = AsScenarioService(order_port=mock, mutation_port=mock)
    session = MagicMock()

    notified = {}

    async def fake_notify(session, mall_id, alert_type, title, message, claim_id=None, extra_data=None, ticket_url=None):
        notified["alert_type"] = alert_type
        notified["mall_id"] = mall_id
        notified["message"] = message
        notified["ticket_url"] = ticket_url
        return None

    monkeypatch.setattr(
        "app.application.as_scenario_service.notification_service.notify_merchant_alert",
        fake_notify,
    )

    state = svc.begin("shop_1", AsIntent.CANCEL)
    state, _, prompt = await svc.apply(session, state, order_id="ORD-NORMAL")
    assert state.status == AsScenarioStatus.COLLECT_REASON

    state, _, _ = await svc.apply(session, state, reason="변심")
    assert state.status == AsScenarioStatus.CONFIRM

    state, events, _ = await svc.apply(session, state, confirm=True)
    assert state.status == AsScenarioStatus.DONE
    assert "취소" in state.bot_prompt
    assert any(e.type == "done" for e in events)

    # Force handoff path
    state2 = svc.begin("shop_1", AsIntent.PARTIAL_RETURN)
    state2, _, _ = await svc.apply(session, state2, force_handoff="customer_requested")
    assert state2.status == AsScenarioStatus.HANDOFF
    assert notified.get("alert_type") == "as_handoff"
    assert notified.get("mall_id") == "shop_1"
    assert notified.get("ticket_url") and "/staff/shop_1/inbox?key=" in notified["ticket_url"]
