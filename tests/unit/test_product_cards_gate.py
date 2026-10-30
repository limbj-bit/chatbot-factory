from app.application.chat_service import ChatService, wants_product_cards
from app.infrastructure.rag.engine import RAGDocument, RAGSearchResult


def test_lookup_and_recommend_want_cards():
    assert wants_product_cards("솜통 찾아줘", "솜통 찾아줘", "beauty") is True
    assert wants_product_cards("추천해줘", "추천해줘", "beauty") is True
    assert wants_product_cards("건성 피부예요", "건성 피부예요", "beauty") is True


def test_greeting_not_in_system_prompt():
    class _S:
        store_name = "테스트몰"
        industry = "beauty"
        bot_name = "루이"
        business_hours = "24시간"
        contact_email = "a@b.c"
        welcome_message = (
            "안녕하세요, 상담사 루이입니다. "
            "피부타입별 맞춤 전성분 상담까지 도와드립니다. 궁금한 점을 편하게 말씀해 주세요."
        )
        policy_config_json = "{}"

    prompt = ChatService._build_store_system_prompt(_S())
    assert "피부타입별 맞춤 전성분 상담까지" not in prompt
    assert "매 답변 앞에" in prompt
    assert "루이" in prompt


def test_card_price_stripped_when_matches_shipping():
    doc = RAGDocument(
        document_id="D1",
        source="crawled_url",
        product_id="D1",
        title="솜통",
        content="솜통 설명",
        metadata={"price": 3000, "purchase_url": "https://x/p", "image_url": None},
    )
    cards = ChatService._build_product_cards(
        [RAGSearchResult(document=doc, score=1.0)],
        reject_prices={3000, 60000},
    )
    assert len(cards) == 1
    assert cards[0].price is None
    assert cards[0].purchase_url == "https://x/p"


def test_card_on_sale_fields():
    doc = RAGDocument(
        document_id="D2",
        source="crawled_url",
        product_id="D2",
        title="세럼",
        content="세럼",
        metadata={
            "price": 18500,
            "original_price": 28000,
            "purchase_url": "https://x/s",
        },
    )
    cards = ChatService._build_product_cards(
        [RAGSearchResult(document=doc, score=1.0)],
        reject_prices={3000},
    )
    assert cards[0].on_sale is True
    assert cards[0].price == 18500
    assert cards[0].original_price == 28000
