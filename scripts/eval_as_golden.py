#!/usr/bin/env python3
"""Skeleton evaluator for evals/as_golden/cases.jsonl — no network."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.application.as_chat_bridge import (  # noqa: E402
    clear_active,
    detect_as_intent,
    get_active,
    handle_as_turn,
)


async def _run_case(case: dict) -> list[str]:
    errors: list[str] = []
    cid = case["id"]
    sid = f"golden-{cid}"
    clear_active(sid)

    if "expect_detect" in case and case.get("intent") is None:
        for turn in case.get("turns") or []:
            got = detect_as_intent(turn)
            if got is not None:
                errors.append(f"{cid}: expected detect=None got={got}")
        return errors

    last_text = ""
    out = None
    session = object()

    async def _noop_notify(*a, **k):
        return None

    import app.application.as_scenario_service as svc_mod

    orig = svc_mod.notification_service.notify_merchant_alert
    svc_mod.notification_service.notify_merchant_alert = _noop_notify  # type: ignore
    try:
        for turn in case.get("turns") or []:
            out = await handle_as_turn(session, sid, "golden_mall", turn)
            if out is None:
                errors.append(f"{cid}: no AS reply for turn={turn!r}")
                continue
            last_text = out[1]
        state = get_active(sid)
        expect = case.get("expect_final_status")
        if expect == "done":
            label = out[0] if out else ""
            if "done" not in label and "접수" not in last_text:
                errors.append(f"{cid}: expected done-ish reply, got {last_text!r}")
        elif expect == "handoff":
            if "직원" not in last_text and "상담" not in last_text:
                errors.append(f"{cid}: expected handoff wording, got {last_text!r}")
        elif expect == "identify_order":
            if state is None or state.status.value != "identify_order":
                if "주문번호" not in last_text:
                    errors.append(f"{cid}: expected identify_order prompt")
        for sub in case.get("expect_substrings") or []:
            if sub not in last_text:
                errors.append(f"{cid}: missing substring {sub!r} in {last_text!r}")
    finally:
        svc_mod.notification_service.notify_merchant_alert = orig  # type: ignore
        clear_active(sid)
    return errors


async def _main_async() -> int:
    path = ROOT / "evals" / "as_golden" / "cases.jsonl"
    cases = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    all_err: list[str] = []
    for case in cases:
        all_err.extend(await _run_case(case))
    if all_err:
        print("FAIL")
        for e in all_err:
            print(" -", e)
        return 1
    print(f"PASS {len(cases)} cases")
    return 0


def main() -> int:
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
