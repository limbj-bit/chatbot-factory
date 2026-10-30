from app.domain.as_scenarios.machine import AsScenarioMachine, advance, start_scenario
from app.domain.as_scenarios.models import AsIntent, AsScenarioStatus


def test_cancel_happy_path_to_execute_event():
    m = AsScenarioMachine.start("demo_mall", AsIntent.CANCEL)
    assert m.state.status == AsScenarioStatus.IDENTIFY_ORDER

    m.step(order_id="ORD-NORMAL")
    assert m.state.status == AsScenarioStatus.COLLECT_REASON
    assert m.state.slots.order_id == "ORD-NORMAL"

    m.step(reason="단순 변심")
    assert m.state.status == AsScenarioStatus.CONFIRM
    assert m.state.slots.reason_code == "change_of_mind"

    events = m.step(confirm=True)
    assert m.state.status == AsScenarioStatus.EXECUTE
    assert any(e.type == "execute" for e in events)

    events = m.step(execute_ok=True)
    assert m.state.status == AsScenarioStatus.DONE
    assert any(e.type == "done" for e in events)


def test_partial_return_defect_requires_photo_then_handoff_on_api_fail():
    state = start_scenario("m1", AsIntent.PARTIAL_RETURN)
    state, _ = advance(state, order_id="ORD-NORMAL")
    assert state.status == AsScenarioStatus.LIST_LINES

    state, _ = advance(state)  # list -> select
    state, _ = advance(
        state,
        line_ids=["PROD-STRAWBERRY-01"],
        quantities={"PROD-STRAWBERRY-01": 1},
        available_line_ids=["PROD-STRAWBERRY-01"],
    )
    assert state.status == AsScenarioStatus.COLLECT_REASON

    state, _ = advance(state, reason="포장 파손 불량")
    assert state.status == AsScenarioStatus.COLLECT_PHOTO
    assert state.slots.needs_photo is True

    state, _ = advance(state, photo_claim_id="claim-1")
    assert state.status == AsScenarioStatus.CONFIRM

    state, events = advance(state, confirm=True)
    assert state.status == AsScenarioStatus.EXECUTE

    state, events = advance(state, execute_ok=False, execute_error="cafe24_timeout")
    assert state.status == AsScenarioStatus.HANDOFF
    assert state.handoff_reason == "cafe24_timeout"
    assert any(e.type == "handoff" for e in events)


def test_force_handoff_and_roundtrip_dict():
    state = start_scenario("m1", AsIntent.EXCHANGE)
    state, events = advance(state, force_handoff="low_confidence")
    assert state.status == AsScenarioStatus.HANDOFF
    assert events[0].type == "handoff"

    restored = type(state).from_dict(state.to_dict())
    assert restored.intent == AsIntent.EXCHANGE
    assert restored.status == AsScenarioStatus.HANDOFF
