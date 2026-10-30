"""Product page price extraction — sale vs list, skip shipping/point amounts."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Tuple

# Just before the amount → not a product sale price.
_BEFORE_NOISE = (
    "배송비",
    "delivery_cost",
    "delivery_fee",
    "적립",
    "마일리지",
    "포인트",
    "리뷰",
    "상품후기",
)
# Just after the amount → free-shipping threshold / fee phrasing.
_AFTER_NOISE = (
    "이상 구매",
    "이상구매",
    "구매 시 무료",
    "구매시 무료",
    "원 이상",
)


@dataclass
class ProductPriceInfo:
    """price = selling (할인가 우선), original_price = 정상가/소비자가 when distinct."""

    price: Optional[int] = None
    original_price: Optional[int] = None

    @property
    def on_sale(self) -> bool:
        return (
            self.price is not None
            and self.original_price is not None
            and self.original_price > self.price
        )


def parse_price_val(v: Any) -> Optional[int]:
    try:
        p = int(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None
    return p if p > 0 else None


def reject_price_set(
    delivery_fee: Any = None,
    free_over_amount: Any = None,
) -> Set[int]:
    out: Set[int] = set()
    for v in (delivery_fee, free_over_amount):
        p = parse_price_val(v)
        if p:
            out.add(p)
    return out


def _ok(p: Optional[int], reject: Set[int]) -> Optional[int]:
    if p is None or p in reject:
        return None
    return p


def _js_assigned(raw_html: str, names: Tuple[str, ...]) -> Optional[int]:
    for name in names:
        m = re.search(
            rf"(?:{name})\s*[=:]\s*[\"']?([0-9,]+)",
            raw_html or "",
            re.IGNORECASE,
        )
        if m:
            return parse_price_val(m.group(1))
    return None


def _label_price(raw_html: str, labels: Tuple[str, ...]) -> Optional[int]:
    for lab in labels:
        m = re.search(
            rf"{re.escape(lab)}\s*[:：]?\s*([0-9]{{1,3}}(?:,[0-9]{{3}})+|[0-9]+)\s*원?",
            raw_html or "",
            re.IGNORECASE,
        )
        if m:
            return parse_price_val(m.group(1))
    return None


def _body_candidate_prices(raw_html: str, reject: Set[int]) -> list:
    """Non-shipping 원-tokens in document order."""
    text = raw_html or ""
    found = []
    for m in re.finditer(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*원", text):
        before = text[max(0, m.start() - 40) : m.start()]
        after = text[m.end() : m.end() + 40]
        if any(k in before for k in _BEFORE_NOISE):
            continue
        if any(k in after for k in _AFTER_NOISE):
            continue
        if re.match(r"\s*\(", after):
            continue
        cand = _ok(parse_price_val(m.group(1)), reject)
        if cand:
            found.append(cand)
    return found


def extract_product_prices(
    raw_html: str,
    jsonld_data: Optional[Dict[str, Any]] = None,
    *,
    reject_prices: Optional[Set[int]] = None,
) -> ProductPriceInfo:
    """Prefer Cafe24 sale/list pair; fall back to JSON-LD / meta / body."""
    reject = reject_prices or set()
    sale: Optional[int] = None
    original: Optional[int] = None

    # Cafe24 JS: sale vs consumer/list
    sale = _ok(
        _js_assigned(raw_html, ("sale_price", "salePrice", "prd_price_sale")),
        reject,
    )
    original = _ok(
        _js_assigned(
            raw_html,
            ("product_price", "productPrice", "prd_price", "consumer_price", "retail_price"),
        ),
        reject,
    )

    # Korean labels on page
    if sale is None:
        sale = _ok(_label_price(raw_html, ("할인가", "판매가", "할인판매가")), reject)
    if original is None:
        original = _ok(_label_price(raw_html, ("소비자가", "정상가", "정가", "기존가")), reject)

    # JSON-LD / meta often = current selling price
    jsonld_price = None
    if jsonld_data:
        offers = jsonld_data.get("offers")
        if isinstance(offers, dict):
            jsonld_price = _ok(parse_price_val(offers.get("price")), reject)
        if jsonld_price is None:
            for v in jsonld_data.get("hasVariant") or []:
                off = (v or {}).get("offers") or {}
                p = _ok(
                    parse_price_val(off.get("price") if isinstance(off, dict) else None),
                    reject,
                )
                if p:
                    jsonld_price = p
                    break

    if sale is None and jsonld_price is not None:
        sale = jsonld_price

    if sale is None:
        price_meta = re.search(
            r'property=["\'](?:product:price:amount|og:price:amount)["\']\s+content=["\']([0-9,]+)["\']',
            raw_html or "",
            re.IGNORECASE,
        )
        if price_meta:
            sale = _ok(parse_price_val(price_meta.group(1)), reject)

    if sale is None:
        body = _body_candidate_prices(raw_html, reject)
        if body:
            sale = body[0]

    # If only one side found via ambiguous product_price when sale empty
    if sale is None and original is not None:
        sale = original
        original = None

    if original is not None and sale is not None:
        if original <= sale:
            # Not a real discount pair
            original = None
        # else keep both → on_sale

    return ProductPriceInfo(price=sale, original_price=original)


def extract_product_price(
    raw_html: str,
    jsonld_data: Optional[Dict[str, Any]] = None,
    *,
    reject_prices: Optional[Set[int]] = None,
) -> Optional[int]:
    """Back-compat: selling price only."""
    return extract_product_prices(
        raw_html, jsonld_data, reject_prices=reject_prices
    ).price
