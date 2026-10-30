from app.application.chat_service import (
    ChatService,
    catalog_match_plan,
    catalog_match_preamble,
    dialogue_query_from_history,
    filter_results_for_cards,
    should_attach_product_cards,
    wants_product_cards,
)
from app.infrastructure.rag.engine import RAGDocument, RAGSearchResult


def _hit(title: str, content: str = "", doc_id: str = "D1") -> RAGSearchResult:
    return RAGSearchResult(
        document=RAGDocument(
            document_id=doc_id,
            source="crawled_url",
            product_id=doc_id,
            title=title,
            content=content or title,
            metadata={"purchase_url": f"https://x/{doc_id}", "price": 10000},
        ),
        score=1.0,
    )


def test_lookup_and_recommend_want_cards():
    assert wants_product_cards("솜통 찾아줘", "솜통 찾아줘", "beauty") is True
    assert wants_product_cards("추천해줘", "추천해줘", "beauty") is True
    assert wants_product_cards("건성 피부예요", "건성 피부예요", "beauty") is True
    assert wants_product_cards("유니폼 있니", "유니폼 있니", "beauty") is True


def test_pearl_followup_attaches_matching_card_only():
    results = [
        _hit("파스텔 1 유니폼", doc_id="1"),
        _hit("파스텔 2 유니폼", doc_id="2"),
        _hit("진주 유니폼", doc_id="3"),
    ]
    assert should_attach_product_cards("진주", "진주", "beauty", results) is True
    cards = filter_results_for_cards("진주", results, max_cards=5)
    assert len(cards) == 1
    assert "진주" in cards[0].document.title


def test_uniform_lists_all_three_cards():
    results = [
        _hit("파스텔 1 유니폼", doc_id="1"),
        _hit("파스텔 2 유니폼", doc_id="2"),
        _hit("진주 유니폼", doc_id="3"),
    ]
    assert should_attach_product_cards("유니폼 있니", "유니폼 있니", "beauty", results)
    cards = filter_results_for_cards("유니폼 있니", results, max_cards=5)
    assert len(cards) == 3


def test_catalog_match_plan_named_keyword_n_and_top_k():
    results = [
        _hit("콜라겐 앰플", doc_id="1"),
        _hit("콜라겐 크림", doc_id="2"),
        _hit("콜라겐 마스크", doc_id="3"),
        _hit("콜라겐 세럼", doc_id="4"),
        _hit("알로에 젤", doc_id="5"),
    ]
    plan = catalog_match_plan("콜라겐 추천해줘", results, recommend_k=3)
    assert plan is not None
    total_n, top = plan
    assert total_n == 4
    assert len(top) == 3
    assert all("콜라겐" in h.document.title for h in top)
    soft = catalog_match_plan("건성 피부 추천", results, recommend_k=3)
    assert soft is None


def test_catalog_match_preamble_includes_n_and_titles():
    top = [_hit("콜라겐 앰플", doc_id="1"), _hit("콜라겐 크림", doc_id="2")]
    text = catalog_match_preamble(7, top)
    assert "총 7개" in text
    assert "상위 2개" in text
    assert "콜라겐 앰플" in text
    assert "N=7" in text


def test_dialogue_query_keeps_prior_collagen_for_similar_ask():
    history = [
        {"role": "user", "content": "콜라겐 있어?"},
        {"role": "assistant", "content": "콜라겐 라인 안내드릴게요."},
        {"role": "user", "content": "비슷한 상품 추천"},
    ]
    # Current turn alone loses 콜라겐; dialogue query must keep it.
    q = dialogue_query_from_history("비슷한 상품 추천", history[:-1])
    assert "콜라겐" in q
    assert "비슷한 상품 추천" in q
    results = [
        _hit("콜라겐 앰플", doc_id="1"),
        _hit("스네일 비비크림", doc_id="2"),
        _hit("매직 비비밤", doc_id="3"),
    ]
    plan = catalog_match_plan(q, results, recommend_k=3)
    assert plan is not None
    assert plan[0] == 1
    assert "콜라겐" in plan[1][0].document.title


def test_competitive_prompt_requires_full_dialogue_reasoning():
    lines = "\n".join(ChatService._competitive_cs_reply_lines())
    assert "대화 전체" in lines
    assert "history" in lines or "이전 턴" in lines
    assert "비비크림" in lines


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
        metadata={
            "price": 3000,
            "purchase_url": "https://x/p",
            "image_url": None,
            "tags": "psrc=cafe24",
        },
    )
    cards = ChatService._build_product_cards(
        [RAGSearchResult(document=doc, score=1.0)],
        reject_prices={3000, 60000},
    )
    assert len(cards) == 1
    assert cards[0].price is None
    assert cards[0].purchase_url == "https://x/p"


def test_card_hides_legacy_price_without_psrc():
    doc = RAGDocument(
        document_id="D450",
        source="crawled_url",
        product_id="D450",
        title="히알루론산 앰플 시트 마스크",
        content="설명",
        metadata={"price": 45000, "purchase_url": "https://x/m", "tags": None},
    )
    cards = ChatService._build_product_cards(
        [RAGSearchResult(document=doc, score=1.0)],
        reject_prices={3000},
    )
    assert cards[0].price is None


def test_card_shows_trusted_cafe24_price():
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
            "tags": "psrc=cafe24",
        },
    )
    cards = ChatService._build_product_cards(
        [RAGSearchResult(document=doc, score=1.0)],
        reject_prices={3000},
    )
    assert cards[0].price == 18500
    assert cards[0].on_sale is True


def test_card_on_sale_fields():
    doc = RAGDocument(
        document_id="D2b",
        source="crawled_url",
        product_id="D2b",
        title="세럼",
        content="세럼",
        metadata={
            "price": 18500,
            "original_price": 28000,
            "purchase_url": "https://x/s",
            "tags": "psrc=cafe24_api",
        },
    )
    cards = ChatService._build_product_cards(
        [RAGSearchResult(document=doc, score=1.0)],
        reject_prices={3000},
    )
    assert cards[0].on_sale is True
    assert cards[0].price == 18500
    assert cards[0].original_price == 28000
