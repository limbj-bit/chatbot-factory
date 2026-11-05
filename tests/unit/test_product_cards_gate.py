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


def test_skin_concern_sentence_attaches_relevant_cards():
    """'지성 피부인데 모공이...' is a concern, not a product name.

    Regression: particles made every word look like a product token, the card
    filter returned [], the LLM got no catalog context and invented products.
    """
    results = [
        _hit("루이셀 퓨리파잉 세럼", content="모공과 피지를 케어하는 세럼", doc_id="p1"),
        _hit("루이셀 화이트닝 세럼", content="미백과 색소 케어", doc_id="p2"),
        _hit("루이셀 콜라겐 크림", content="탄력 케어", doc_id="p3"),
    ]
    msg = "지성 피부인데 모공이 넓어서 고민이에요. 어떤 제품이 좋을까요?"
    assert should_attach_product_cards(msg, msg, "beauty", results) is True
    cards = filter_results_for_cards(msg, results, max_cards=5)
    assert len(cards) >= 1
    assert "모공" in cards[0].document.content


def test_concern_sentence_with_boilerplate_content_still_attaches_top_cards():
    """Real crawled products rarely mention '모공' in the first 200 chars.

    Regression: the query had soft tokens (지성/모공/피지) plus conversational
    tokens (넓고/써야/할까). The filter treated the sentence as a named-product
    query, returned [], and the live answer had zero cards.
    """
    results = [
        _hit(
            "루이셀 퓨리파잉 세럼",
            content=(
                "루이셀 퓨리파잉 세럼. 배송비: 3,000원 (60,000원 이상 구매 시 무료) | "
                "용량: 100ml | 상품명: 루이셀 퓨리파잉 세럼. 고객님을 위한 추천상품 "
                "루이셀 화이트닝 세럼 루이셀 비타C 세럼"
            ),
            doc_id="p1",
        ),
        _hit(
            "퓨리파잉 앰플",
            content="퓨리파잉 앰플. 배송비: 3,000원 | 용량: 2ml x 20ea",
            doc_id="p2",
        ),
        _hit(
            "루이셀 콜라겐 크림",
            content="루이셀 콜라겐 크림. 배송비: 3,000원 | 용량: 50g",
            doc_id="p3",
        ),
    ]
    msg = "지성 피부인데 모공이 넓고 피지가 많아요. 어떤 제품을 써야 할까요?"
    assert should_attach_product_cards(msg, msg, "beauty", results) is True
    cards = filter_results_for_cards(msg, results, max_cards=5)
    assert len(cards) >= 2
    assert cards[0].document.title == "루이셀 퓨리파잉 세럼"


def test_named_product_without_match_does_not_dump_unrelated_cards():
    results = [_hit("루이셀 알로에 젤", content="수분 진정", doc_id="p1")]
    cards = filter_results_for_cards("콜라겐 에센스 추천해줘", results, max_cards=5)
    assert cards == []


def test_named_query_with_generic_predicate_still_does_not_fallback():
    """A named query with a conversational ending must not fall back to top hits."""
    results = [
        _hit("루이셀 알로에 젤", content="수분 진정", doc_id="p1"),
        _hit("루이셀 퓨리파잉 앰플", content="트러블 진정", doc_id="p2"),
    ]
    msg = "콜라겐 에센스 없어요?"
    assert filter_results_for_cards(msg, results, max_cards=5) == []


def test_named_product_exact_title_returns_only_that_product():
    """'루이셀 퓨리파잉 세럼' must not widen to every serum in the catalog."""
    results = [
        _hit("루이셀 퓨리파잉 세럼", content="트러블 진정 세럼", doc_id="p1"),
        _hit("루이셀 EGF 세럼", content="추천상품: 루이셀 퓨리파잉 세럼", doc_id="p2"),
        _hit("루이셀 콜라겐 세럼", content="탄력 세럼", doc_id="p3"),
    ]
    msg = "루이셀 퓨리파잉 세럼 있어요?"
    cards = filter_results_for_cards(msg, results, max_cards=5)
    assert [c.document.title for c in cards] == ["루이셀 퓨리파잉 세럼"]


def test_concern_sentence_with_particles_is_treated_as_soft_query():
    """'건성 피부라 속건조가 심해요' must not be mistaken for a product name.

    Regression: '피부라'/'심해'/'추천해주세' survived token cleanup, so the
    soft-only fallback never fired and an unrelated catalog hit list stayed empty.
    """
    results = [
        _hit("루이셀 아이리뉴얼 크림", content="배송비 3,000원", doc_id="p1"),
        _hit("루이셀 EGF 앰플", content="배송비 3,000원", doc_id="p2"),
    ]
    msg = "건성 피부라 속건조가 심해요. 수분 세럼 추천해주세요."
    cards = filter_results_for_cards(msg, results, max_cards=5)
    assert len(cards) == 2


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
