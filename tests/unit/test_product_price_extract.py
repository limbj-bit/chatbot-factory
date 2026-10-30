from app.application.product_price_extract import (
    extract_product_price,
    extract_product_prices,
    reject_price_set,
)


def test_skips_shipping_fee_body_text():
    html = """
    <div>배송비 3,000원 (60,000원 이상 구매 시 무료)</div>
    <div class="price">판매가 28,000원</div>
    """
    assert extract_product_price(html, None, reject_prices={3000, 60000}) == 28000


def test_rejects_delivery_fee_even_from_jsonld():
    jsonld = {"@type": "Product", "offers": {"price": "3000"}}
    assert extract_product_price("", jsonld, reject_prices={3000}) is None


def test_cafe24_js_sale_price_wins():
    html = 'var sale_price = "18500"; product_price = "28000"; 배송비 3,000원'
    assert extract_product_price(html, None, reject_prices={3000, 60000}) == 18500


def test_list_price_alone_does_not_become_sale():
    """소비자가/정가만 있으면 카드에는 가격 생략 (잘못된 본문 추정 방지)."""
    html = 'var product_price = "18500"; 배송비 3,000원'
    info = extract_product_prices(html, None, reject_prices={3000, 60000})
    assert info.price is None
    assert info.original_price == 18500


def test_sale_vs_original():
    html = 'product_price = "28000"; sale_price = "18500";'
    info = extract_product_prices(html, None, reject_prices=set())
    assert info.price == 18500
    assert info.original_price == 28000
    assert info.on_sale is True


def test_cafe24_sale_beats_related_rail_amount():
    html = """
    <strong id="span_product_price_text">20,000원</strong>
    <span id="span_product_price_sale">10,000원</span>
    <div class="relate">추천상품 45,000원</div>
    """
    info = extract_product_prices(html, None, reject_prices={3000})
    assert info.price == 10000
    assert info.original_price == 20000


def test_body_rail_not_used_as_sale_by_default():
    html = "연관상품 45,000원 다른상품 32,000원 배송비 3,000원"
    assert extract_product_prices(html, None, reject_prices={3000}).price is None


def test_cafe24_dom_ids():
    html = """
    <strong id="span_product_price_text" style="text-decoration: line-through;">69,900원</strong>
    <span id="span_product_price_sale">62,910원 <span>(6,990원 할인)</span></span>
    배송비 3,000원 (60,000원 이상 구매 시 무료)
    """
    info = extract_product_prices(html, None, reject_prices={3000, 60000})
    assert info.price == 62910
    assert info.original_price == 69900
    assert info.on_sale is True
    assert info.discount_percent == 10


def test_label_sale_and_list():
    html = "소비자가 32,000원 할인가 24,000원"
    info = extract_product_prices(html, None)
    assert info.price == 24000
    assert info.original_price == 32000
    assert info.on_sale is True


def test_reject_price_set():
    assert reject_price_set(3000, 60000) == {3000, 60000}


def test_cafe24_image_big():
    from app.application.product_price_extract import extract_product_image_url

    html = '<div id="bigImage"><img src="https://cdn.example.com/p/pearl.jpg" /></div>'
    assert extract_product_image_url(html) == "https://cdn.example.com/p/pearl.jpg"
