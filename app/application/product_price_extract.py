"""Product page price/image extraction — Cafe24 DOM first, then schema/meta/body."""
from __future__ import annotations

import html as html_lib
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

# Cafe24 smart-design price nodes (often present even before JS hydrate).
_CAFE24_SALE_IDS = (
    "span_product_price_sale",
    "span_product_price_mobile_text",
    "span_product_price_custom",
)
_CAFE24_LIST_IDS = (
    "span_product_price_text",
    "span_product_price_custom_text",
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

    @property
    def discount_percent(self) -> Optional[int]:
        if not self.on_sale or not self.price or not self.original_price:
            return None
        return max(1, min(99, int(round((1 - self.price / self.original_price) * 100))))


def parse_price_val(v: Any) -> Optional[int]:
    """Normalize price text; uses price-parser when installed."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        p = int(v)
        return p if p > 0 else None
    text = str(v).strip()
    if not text:
        return None
    try:
        from price_parser import Price  # type: ignore

        parsed = Price.fromstring(text)
        if parsed.amount is not None:
            # KRW pages are usually whole won; Decimal may be 62910.00
            p = int(parsed.amount)
            if p > 0:
                return p
    except Exception:
        pass
    # Digits only (strip 원, commas, discount parenthetical)
    m = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)", text.replace(" ", ""))
    if not m:
        return None
    try:
        p = int(m.group(1).replace(",", ""))
    except ValueError:
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


def _element_inner_text(raw_html: str, element_id: str) -> Optional[str]:
    """Pull text content of id=\"…\" (Cafe24 price spans)."""
    pat = re.compile(
        rf'id=["\']{re.escape(element_id)}["\'][^>]*>([\s\S]*?)</(?:span|strong|div|p|em)>',
        re.IGNORECASE,
    )
    m = pat.search(raw_html or "")
    if not m:
        return None
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    text = html_lib.unescape(re.sub(r"\s+", " ", text)).strip()
    return text or None


def _cafe24_dom_prices(raw_html: str, reject: Set[int]) -> Tuple[Optional[int], Optional[int]]:
    sale = None
    original = None
    for eid in _CAFE24_SALE_IDS:
        t = _element_inner_text(raw_html, eid)
        if t:
            # "62,910원 (6,990원 할인)" → first amount
            sale = _ok(parse_price_val(t.split("(")[0]), reject)
            if sale:
                break
    for eid in _CAFE24_LIST_IDS:
        t = _element_inner_text(raw_html, eid)
        if t:
            original = _ok(parse_price_val(t.split("(")[0]), reject)
            if original:
                break
    return sale, original


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


def _extruct_offer_price(raw_html: str, reject: Set[int]) -> Optional[int]:
    """Optional scrapinghub/extruct JSON-LD + OpenGraph price."""
    try:
        import extruct  # type: ignore
    except Exception:
        return None
    try:
        data = extruct.extract(
            raw_html or "",
            syntaxes=["json-ld", "opengraph", "microdata"],
            errors="ignore",
        )
    except Exception:
        return None
    for block in data.get("json-ld") or []:
        if not isinstance(block, dict):
            continue
        types = block.get("@type")
        type_l = (
            [types]
            if isinstance(types, str)
            else list(types or [])
            if isinstance(types, list)
            else []
        )
        type_s = " ".join(str(t) for t in type_l).lower()
        if "product" not in type_s and "offer" not in type_s:
            # still try offers
            pass
        offers = block.get("offers")
        if isinstance(offers, dict):
            p = _ok(parse_price_val(offers.get("price")), reject)
            if p:
                return p
        if isinstance(offers, list):
            for off in offers:
                if isinstance(off, dict):
                    p = _ok(parse_price_val(off.get("price")), reject)
                    if p:
                        return p
    for og in data.get("opengraph") or []:
        props = og.get("properties") if isinstance(og, dict) else None
        if not isinstance(props, dict):
            continue
        for key in ("product:price:amount", "og:price:amount"):
            if key in props:
                p = _ok(parse_price_val(props[key]), reject)
                if p:
                    return p
    return None


def extract_product_prices(
    raw_html: str,
    jsonld_data: Optional[Dict[str, Any]] = None,
    *,
    reject_prices: Optional[Set[int]] = None,
    allow_body_fallback: bool = False,
) -> ProductPriceInfo:
    """Cafe24 sale/list spans first. Never guess from random body amounts by default.

    Body/related-product digits (e.g. 45,000원 in a rail) caused false sale prices.
    If sale cannot be resolved, price stays None — card shows features; Front API can fill later.
    """
    reject = reject_prices or set()
    sale: Optional[int] = None
    original: Optional[int] = None

    # 1) Cafe24 theme nodes — sale span is source of truth for discount malls
    c24_sale, c24_list = _cafe24_dom_prices(raw_html, reject)
    sale = c24_sale
    original = c24_list

    # 2) Explicit sale JS / 할인가 labels only (not generic product_price → sale)
    if sale is None:
        sale = _ok(
            _js_assigned(raw_html, ("sale_price", "salePrice", "prd_price_sale")),
            reject,
        )
    if original is None:
        original = _ok(
            _js_assigned(
                raw_html,
                (
                    "product_price",
                    "productPrice",
                    "prd_price",
                    "consumer_price",
                    "retail_price",
                ),
            ),
            reject,
        )

    # 3) Korean sale/list labels
    if sale is None:
        sale = _ok(_label_price(raw_html, ("할인가", "할인판매가", "판매가")), reject)
    if original is None:
        original = _ok(_label_price(raw_html, ("소비자가", "정상가", "정가", "기존가")), reject)

    # 4) JSON-LD / meta only when Cafe24 sale still empty (structured, not body scrape)
    if sale is None and jsonld_data:
        offers = jsonld_data.get("offers")
        if isinstance(offers, dict):
            sale = _ok(parse_price_val(offers.get("price")), reject)
        if sale is None:
            for v in jsonld_data.get("hasVariant") or []:
                off = (v or {}).get("offers") or {}
                p = _ok(
                    parse_price_val(off.get("price") if isinstance(off, dict) else None),
                    reject,
                )
                if p:
                    sale = p
                    break
    if sale is None:
        sale = _extruct_offer_price(raw_html, reject)

    if sale is None:
        price_meta = re.search(
            r'property=["\'](?:product:price:amount|og:price:amount)["\']\s+content=["\']([0-9,]+)["\']',
            raw_html or "",
            re.IGNORECASE,
        )
        if price_meta:
            sale = _ok(parse_price_val(price_meta.group(1)), reject)

    # 5) Body scrape OFF by default — related rails inject wrong amounts (45,000 등)
    if sale is None and allow_body_fallback:
        body = _body_candidate_prices(raw_html, reject)
        if body:
            sale = body[0]

    # Do NOT promote list/소비자가 alone to sale — omit price rather than lie
    if original is not None and sale is not None and original <= sale:
        original = None

    return ProductPriceInfo(price=sale, original_price=original)


def extract_product_price(
    raw_html: str,
    jsonld_data: Optional[Dict[str, Any]] = None,
    *,
    reject_prices: Optional[Set[int]] = None,
) -> Optional[int]:
    return extract_product_prices(
        raw_html, jsonld_data, reject_prices=reject_prices
    ).price


def extract_product_image_url(raw_html: str) -> Optional[str]:
    """Prefer Cafe24 big image / JSON-LD / og:image (skip logos/SVG)."""
    text = raw_html or ""

    # Cafe24 zoom / big image
    for pat in (
        r'id=["\']bigImage["\'][^>]*>\s*<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+id=["\']bigImage["\'][^>]+src=["\']([^"\']+)["\']',
        r'class=["\'][^"\']*BigImage[^"\']*["\'][^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+class=["\'][^"\']*ThumbImage[^"\']*["\'][^>]+src=["\']([^"\']+)["\']',
    ):
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            url = html_lib.unescape(m.group(1).strip())
            low = url.lower()
            if url and not low.endswith(".svg") and "logo" not in low:
                return url

    try:
        import extruct  # type: ignore

        data = extruct.extract(
            text, syntaxes=["json-ld", "opengraph"], errors="ignore"
        )
        for block in data.get("json-ld") or []:
            if not isinstance(block, dict):
                continue
            imgs = block.get("image")
            if isinstance(imgs, list) and imgs and isinstance(imgs[0], str):
                return imgs[0].strip()
            if isinstance(imgs, str) and imgs.strip():
                return imgs.strip()
        for og in data.get("opengraph") or []:
            props = og.get("properties") if isinstance(og, dict) else None
            if isinstance(props, dict) and props.get("og:image"):
                cand = str(props["og:image"]).strip()
                low = cand.lower()
                if cand and not low.endswith(".svg") and "logo" not in low:
                    return cand
    except Exception:
        pass

    img_match = re.search(
        r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']',
        text,
        re.IGNORECASE,
    )
    if img_match:
        cand = html_lib.unescape(img_match.group(1).strip())
        low = cand.lower()
        if cand and not low.endswith(".svg") and "logo" not in low:
            return cand
    return None
