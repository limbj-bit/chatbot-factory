import pytest

from app.application.as_chat_bridge import (
    clear_active,
    detect_as_intent,
    handle_as_turn,
    parse_step_kwargs,
)
from app.domain.as_scenarios.models import AsIntent, AsScenarioStatus
from app.application.as_scenario_service import as_scenario_service


def test_detect_as_intent_actions_not_policy():
    assert detect_as_intent("주문 취소해줘") == AsIntent.CANCEL
    assert detect_as_intent("반품 정책이 뭐예요?") is None
    assert detect_as_intent("상담원 연결해주세요") == AsIntent.HANDOFF
    assert detect_as_intent("일부 반품하고 싶어요") == AsIntent.PARTIAL_RETURN


@pytest.mark.asyncio
async def test_chat_bridge_cancel_flow(monkeypatch):
    clear_active("sess-as-1")
    session = object()

    async def fake_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.application.as_scenario_service.notification_service.notify_merchant_alert",
        fake_notify,
    )

    r1 = await handle_as_turn(session, "sess-as-1", "shop_x", "주문 취소해줘")
    assert r1 is not None
    assert r1[0].startswith("as_cancel")
    assert "주문번호" in r1[1]

    r2 = await handle_as_turn(session, "sess-as-1", "shop_x", "ORD-NORMAL")
    assert r2 is not None
    assert "사유" in r2[1]

    r3 = await handle_as_turn(session, "sess-as-1", "shop_x", "변심이에요")
    assert r3 is not None
    assert "진행할까요" in r3[1] or "취소" in r3[1]

    r4 = await handle_as_turn(session, "sess-as-1", "shop_x", "네")
    assert r4 is not None
    assert "done" in r4[0] or "접수" in r4[1]


def test_parse_confirm():
    state = as_scenario_service.begin("m", AsIntent.CANCEL)
    state.status = AsScenarioStatus.CONFIRM
    assert parse_step_kwargs(state, "네 진행해주세요")["confirm"] is True
    assert parse_step_kwargs(state, "아니요")["confirm"] is False
