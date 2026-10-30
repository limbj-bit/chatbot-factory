#!/usr/bin/env python3
"""Offline CS golden checks: cards + cross-industry prompt bench (no network)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.application.chat_service import (  # noqa: E402
    ChatService,
    filter_results_for_cards,
    should_attach_product_cards,
)
from app.infrastructure.rag.engine import RAGDocument, RAGSearchResult  # noqa: E402


def _hits(titles: list[str]) -> list[RAGSearchResult]:
    out = []
    for i, title in enumerate(titles):
        out.append(
            RAGSearchResult(
                document=RAGDocument(
                    document_id=f"D{i}",
                    source="crawled_url",
                    product_id=f"D{i}",
                    title=title,
                    content=title,
                    metadata={"purchase_url": f"https://x/{i}", "price": 10000 + i},
                ),
                score=1.0,
            )
        )
    return out


def _run_case(case: dict) -> list[str]:
    errors: list[str] = []
    cid = case["id"]
    industry = case.get("industry") or "general"
    msg = case["message"]
    results = _hits(case.get("titles") or [])
    attach = should_attach_product_cards(msg, msg, industry, results)
    if case.get("expect_attach") is False and attach:
        errors.append(f"{cid}: expected no attach")
    if case.get("expect_attach") is not False and not attach:
        errors.append(f"{cid}: expected attach")
    cards = filter_results_for_cards(msg, results, max_cards=5) if attach else []
    got_titles = [c.document.title for c in cards]
    if "expect_card_titles" in case:
        if got_titles != case["expect_card_titles"]:
            errors.append(f"{cid}: cards {got_titles!r} != {case['expect_card_titles']!r}")
    if "expect_card_titles_contains" in case:
        for needle in case["expect_card_titles_contains"]:
            if not any(needle in t for t in got_titles):
                errors.append(f"{cid}: no card title contains {needle!r} in {got_titles!r}")
    if "min_cards" in case and len(cards) < int(case["min_cards"]):
        errors.append(f"{cid}: cards={len(cards)} < min {case['min_cards']}")
    return errors


def main() -> int:
    path = ROOT / "evals" / "cs_golden" / "cases.jsonl"
    errors: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        errors.extend(_run_case(json.loads(line)))

    # Prompt: competitive bench applies to every industry key we care about.
    class _S:
        store_name = "테스트몰"
        industry = "fashion"
        bot_name = "루이"
        business_hours = "24시간"
        contact_email = "a@b.c"
        welcome_message = "안녕하세요, 상담사 루이입니다. 긴환영멘트"
        policy_config_json = "{}"

    for ind in ("beauty", "fashion", "fresh_food", "general", "electronics"):
        _S.industry = ind
        prompt = ChatService._build_store_system_prompt(_S())
        if "상품 상담 답변 벤치 (전 업종 공통" not in prompt:
            errors.append(f"prompt:{ind}: missing competitive CS bench block")
        if "긴환영멘트" in prompt:
            errors.append(f"prompt:{ind}: welcome spam still injected")
        if "**볼드**" not in prompt and "볼드" not in prompt:
            errors.append(f"prompt:{ind}: missing typography emphasis guidance")
        if "배송비" not in prompt or "판매가" not in prompt:
            # shipping-as-price rule lives in rules section
            if "배송비 금액을 상품" not in prompt and "배송비·무료배송 기준" not in prompt:
                errors.append(f"prompt:{ind}: missing shipping≠sale content rule")

    # Shipping fee must not be quoted as product sale price.
    class _Ship:
        policy_config_json = json.dumps(
            {"shipping_policy": {"delivery_fee": 3000, "free_over_amount": 60000}}
        )

    bad = "진주 유니폼을 3,000원에 판매하고 있습니다."
    fixed = ChatService._guardrail_shipping_not_product_price(bad, _Ship())  # type: ignore
    if "3,000원에 판매" in fixed and "상세 페이지" not in fixed:
        errors.append(f"guardrail failed: {fixed!r}")

    if errors:
        print("FAIL")
        for e in errors:
            print(" -", e)
        return 1
    print("OK", path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
