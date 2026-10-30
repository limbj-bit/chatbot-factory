import pytest

from app.application.product_price_enrich import (
    needs_price_enrichment,
    product_no_from_url,
    enrich_product_prices,
)
from app.application.product_price_extract import ProductPriceInfo


def test_product_no_from_cafe24_path():
    assert (
        product_no_from_url("https://rooicellmall.co.kr/product/somtong/12345/")
        == "12345"
    )
    assert product_no_from_url("https://x.com/?product_no=99") == "99"
    assert product_no_from_url("https://x.com/about") is None


def test_needs_enrichment_when_missing_or_rejected():
    assert needs_price_enrichment(ProductPriceInfo(price=None)) is True
    assert needs_price_enrichment(ProductPriceInfo(price=3000), {3000}) is True
    # 3000 looks like Cafe24 shipping even when not in store reject set
    assert needs_price_enrichment(ProductPriceInfo(price=3000), set()) is True
    assert needs_price_enrichment(ProductPriceInfo(price=18500), {3000}) is False


@pytest.mark.asyncio
async def test_enrich_keeps_static_when_good(monkeypatch):
    html = '<span id="span_product_price_text">18,500원</span> 배송비 3,000원'
    # Ensure API/playwright not called when static is enough
    async def boom(*a, **k):
        raise AssertionError("should not enrich")

    monkeypatch.setattr(
        "app.application.product_price_enrich.fetch_cafe24_front_price", boom
    )
    monkeypatch.setattr(
        "app.application.product_price_enrich.fetch_js_rendered_html", boom
    )
    info, used, src = await enrich_product_prices(
        "https://x.com/product/a/1", html, None, reject_prices={3000}
    )
    assert src == "static"
    assert info.price == 18500
    assert used == html


@pytest.mark.asyncio
async def test_enrich_uses_api_when_static_only_shipping(monkeypatch):
    html = "배송비 3,000원 (60,000원 이상 구매 시 무료)"

    async def fake_api(product_no, **kwargs):
        assert product_no == "42"
        return ProductPriceInfo(price=12000, original_price=15000)

    async def no_pw(*a, **k):
        raise AssertionError("playwright should not run when API works")

    monkeypatch.setattr(
        "app.application.product_price_enrich.fetch_cafe24_front_price", fake_api
    )
    monkeypatch.setattr(
        "app.application.product_price_enrich.fetch_js_rendered_html", no_pw
    )
    info, _, src = await enrich_product_prices(
        "https://shop.com/product/foo/42",
        html,
        None,
        reject_prices={3000, 60000},
    )
    assert src == "cafe24_api"
    assert info.price == 12000
    assert info.original_price == 15000


@pytest.mark.asyncio
async def test_enrich_falls_back_to_playwright(monkeypatch):
    html = "배송비 3,000원"

    async def no_api(*a, **k):
        return None

    async def fake_pw(url, **kwargs):
        return '<span id="span_product_price_sale">9,900원</span>'

    monkeypatch.setattr(
        "app.application.product_price_enrich.fetch_cafe24_front_price", no_api
    )
    monkeypatch.setattr(
        "app.application.product_price_enrich.fetch_js_rendered_html", fake_pw
    )
    info, used, src = await enrich_product_prices(
        "https://shop.com/product/foo/7",
        html,
        None,
        reject_prices={3000},
    )
    assert src == "playwright"
    assert info.price == 9900
    assert "span_product_price_sale" in used
