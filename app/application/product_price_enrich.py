"""Enrich product prices when static HTML only has shipping fees / empty Cafe24 spans.

Priority:
1) Cafe24 Front API (when CAFE24_FRONT_CLIENT_ID + mall id configured)
2) Playwright JS render → reuse extract_product_prices
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

import httpx

from app.application.product_price_extract import (
    ProductPriceInfo,
    extract_product_prices,
    parse_price_val,
)

logger = logging.getLogger(__name__)

# Cafe24 themes almost always print these as 배송비; treat as untrusted until
# Front API / Playwright fills a real sale node.
_SHIPPING_LOOKALIKE_PRICES = frozenset({2500, 3000})

_CAFE24_PRICE_WAIT_JS = """
() => {
  const ids = [
    "span_product_price_text",
    "span_product_price_sale",
    "span_product_price_mobile_text",
    "span_product_price_custom",
  ];
  return ids.some((id) => {
    const el = document.getElementById(id);
    return !!(el && el.textContent && /\\d/.test(el.textContent));
  });
}
"""


def product_no_from_url(url: str) -> Optional[str]:
    raw = (url or "").strip()
    if not raw:
        return None
    try:
        p = urlparse(raw)
    except Exception:
        return None
    path = p.path or ""
    m = re.search(r"/product/[^/]+/(\d+)/?$", path, re.IGNORECASE)
    if m:
        return m.group(1)
    qs = parse_qs(p.query)
    for key in ("product_no", "productno", "goods_no", "goodsno"):
        vals = qs.get(key)
        if vals and str(vals[0]).isdigit():
            return str(vals[0])
    return None


def needs_price_enrichment(
    info: ProductPriceInfo,
    reject_prices: Optional[Set[int]] = None,
) -> bool:
    """True when sale price missing, rejected, or looks like Cafe24 shipping fee."""
    if info.price is None:
        return True
    reject = reject_prices or set()
    if info.price in reject:
        return True
    # Static HTML often scrapes 배송비 3,000 as the only digit — force JS/API.
    return info.price in _SHIPPING_LOOKALIKE_PRICES


def _cafe24_api_mall_id() -> Optional[str]:
    try:
        from app.core.config import settings

        v = (settings.CAFE24_API_MALL_ID or "").strip()
        if v:
            return v
    except Exception:
        pass
    return (os.getenv("CAFE24_API_MALL_ID") or "").strip() or None


def _cafe24_front_client_id() -> Optional[str]:
    try:
        from app.core.config import settings

        v = (settings.CAFE24_FRONT_CLIENT_ID or settings.CAFE24_CLIENT_ID or "").strip()
        if v:
            return v
    except Exception:
        pass
    return (
        os.getenv("CAFE24_FRONT_CLIENT_ID") or os.getenv("CAFE24_CLIENT_ID") or ""
    ).strip() or None


def _playwright_enabled() -> bool:
    try:
        from app.core.config import settings

        return bool(settings.PRICE_ENRICH_PLAYWRIGHT)
    except Exception:
        return True


async def fetch_cafe24_front_price(
    product_no: str,
    *,
    api_mall_id: Optional[str] = None,
    client_id: Optional[str] = None,
    timeout: float = 12.0,
) -> Optional[ProductPriceInfo]:
    """Cafe24 Front API product price (works after client_id is issued)."""
    mall = (api_mall_id or _cafe24_api_mall_id() or "").strip()
    cid = (client_id or _cafe24_front_client_id() or "").strip()
    pn = str(product_no or "").strip()
    if not mall or not cid or not pn.isdigit():
        return None
    url = f"https://{mall}.cafe24api.com/api/v2/products/{pn}"
    headers = {
        "Content-Type": "application/json",
        "X-Cafe24-Client-Id": cid,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code >= 400:
                logger.info(
                    "[price_enrich] Cafe24 Front API %s → %s",
                    resp.status_code,
                    (resp.text or "")[:160],
                )
                return None
            data = resp.json()
    except Exception as e:
        logger.info("[price_enrich] Cafe24 Front API error: %s", e)
        return None

    product: Dict[str, Any] = {}
    if isinstance(data, dict):
        if isinstance(data.get("product"), dict):
            product = data["product"]
        elif "price" in data:
            product = data
    sale = parse_price_val(product.get("price"))
    original = parse_price_val(product.get("retail_price"))
    if sale is None and original is None:
        return None
    if original is not None and sale is not None and original <= sale:
        original = None
    if sale is None and original is not None:
        sale = original
        original = None
    return ProductPriceInfo(price=sale, original_price=original)


async def fetch_js_rendered_html(
    url: str,
    *,
    timeout_ms: int = 20000,
    wait_ms: int = 10000,
) -> Optional[str]:
    """Load product page in Chromium and return HTML after Cafe24 price nodes fill."""
    if not _playwright_enabled():
        return None
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.debug("[price_enrich] playwright not installed — skip JS render")
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                try:
                    await page.wait_for_function(_CAFE24_PRICE_WAIT_JS, timeout=wait_ms)
                except Exception:
                    # Still return HTML — extract may find JS vars / labels
                    pass
                return await page.content()
            finally:
                await browser.close()
    except Exception as e:
        logger.info("[price_enrich] Playwright render failed: %s", e)
        return None


async def enrich_product_prices(
    page_url: str,
    raw_html: str,
    jsonld_data: Optional[Dict[str, Any]] = None,
    *,
    reject_prices: Optional[Set[int]] = None,
) -> Tuple[ProductPriceInfo, str, str]:
    """Return (price_info, html_used, source) where source is static|cafe24_api|playwright."""
    reject = reject_prices or set()
    info = extract_product_prices(raw_html, jsonld_data, reject_prices=reject)
    if not needs_price_enrichment(info, reject):
        return info, raw_html, "static"

    product_no = product_no_from_url(page_url)
    if product_no:
        api_info = await fetch_cafe24_front_price(product_no)
        if api_info and api_info.price is not None and api_info.price not in reject:
            return api_info, raw_html, "cafe24_api"

    rendered = await fetch_js_rendered_html(page_url)
    if rendered:
        js_info = extract_product_prices(rendered, None, reject_prices=reject)
        if (
            js_info.price is not None
            and js_info.price not in reject
            and js_info.price not in _SHIPPING_LOOKALIKE_PRICES
        ):
            return js_info, rendered, "playwright"
        # Playwright ran but still only shipping-like digits — hide price vs lie
        if js_info.price is None or js_info.price in _SHIPPING_LOOKALIKE_PRICES | reject:
            return ProductPriceInfo(price=None, original_price=None), rendered, "playwright"
        return js_info, rendered, "playwright"

    # Static-only 3,000원 lookalike: never persist as sale price
    if info.price is not None and info.price in _SHIPPING_LOOKALIKE_PRICES | reject:
        return ProductPriceInfo(price=None, original_price=None), raw_html, "static_cleared"
    return info, raw_html, "static"
