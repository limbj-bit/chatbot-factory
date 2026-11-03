from app.infrastructure.rag.engine import RAGDocument, RAGEngine, RAGSearchResult


def test_deterministic_faq_lookup():
    rag = RAGEngine()

    # Exact keyword match (0 tokens cost)
    faq1 = rag.lookup_deterministic_faq("배송비 얼마예요?")
    assert faq1 is not None
    assert "3,000원" in faq1
    assert "무료배송" in faq1

    faq2 = rag.lookup_deterministic_faq("고객센터 운영시간 알려주세요")
    assert faq2 is not None
    assert "오전 9시부터 오후 6시" in faq2

    # Irrelevant query returns None
    assert rag.lookup_deterministic_faq("사과 맛이 왜 이런가요?") is None

    # Excluded keywords (store already owns the topic) are skipped
    assert rag.lookup_deterministic_faq("배송비 얼마예요?", exclude_keywords={"배송비"}) is None



def test_rag_search_and_context_assembly():
    rag = RAGEngine()

    # Search for strawberry storage (fresh_food default corpus)
    results = rag.search("딸기 보관 방법", industry="fresh_food")
    assert len(results) > 0
    top_doc = results[0].document
    assert "설향 딸기" in top_doc.title
    assert "냉장(0~4℃)" in top_doc.content
    assert top_doc.metadata["variety"] == "설향"

    context = rag.assemble_context(results)
    assert "[문서 ID: DOC-PROD-001" in context
    assert "참고 공식 지식 베이스" in context


def test_context_caps_long_pages_to_keep_first_token_fast():
    rag = RAGEngine()
    long_doc = RAGDocument(
        document_id="long",
        source="crawled_url",
        product_id="long",
        title="루이셀 테스트 세럼",
        content=(
            "상품요약정보 "
            + ("가" * 700)
            + "전성분: 나이아신아마이드, 판테놀 "
            + ("나" * 1000)
            + "TAIL_MARKER"
        ),
        metadata={"industry": "beauty", "price": 12000},
    )
    results = [RAGSearchResult(document=long_doc, score=1.0)]
    context = rag.assemble_context(results)
    assert "루이셀 테스트 세럼" in context
    assert "12,000원" in context
    # Key ingredient block after the head is preserved for answer quality.
    assert "나이아신아마이드" in context
    assert "TAIL_MARKER" not in context
    assert len(context) < 1600


def test_groq_qwen_disables_thinking_for_fast_first_token():
    from app.infrastructure.ai.groq import GroqProvider

    assert GroqProvider._reasoning_params("qwen/qwen3.8-27b") == {
        "reasoning_effort": "none"
    }
    # Unsupported models must not receive the parameter (Groq returns 400).
    assert GroqProvider._reasoning_params("llama-3.3-70b-versatile") == {}


def test_default_docs_isolated_by_industry():
    rag = RAGEngine()
    # Beauty must not surface fresh-food strawberry docs
    beauty_hits = rag.search("딸기 보관 방법", industry="beauty")
    assert all(r.document.metadata.get("industry") == "beauty" for r in beauty_hits)
    # Fresh food can hit strawberry
    fresh_hits = rag.search("딸기 보관", industry="fresh_food")
    assert any("딸기" in r.document.title for r in fresh_hits)


def test_beauty_concern_expansion_and_product_ranking():
    from app.infrastructure.rag.engine import BEAUTY_CONCERN_EXPANSIONS, expand_query_tokens

    assert BEAUTY_CONCERN_EXPANSIONS["모공"]
    tokens = expand_query_tokens("지성 피부인데 모공이 넓어요", "beauty")
    assert "피지" in tokens and "퓨리파잉" in tokens
    # Expansion is beauty-only (no cross-industry vocabulary leak)
    assert expand_query_tokens("지성 모공", "fresh_food") == {"지성", "모공"}

    rag = RAGEngine()
    rag.documents = [
        RAGDocument(
            document_id="good",
            source="crawled_url",
            product_id="good",
            title="루이셀 퓨리파잉 세럼",
            content="피지와 모공을 케어하는 세럼",
            metadata={"industry": "beauty"},
        ),
        RAGDocument(
            document_id="junk",
            source="crawled_url",
            product_id="junk",
            title="루이셀",
            content="피부 제품 안내 피부 고민 상담",
            metadata={"industry": "beauty"},
        ),
    ]
    results = rag.search("지성 피부인데 모공이 넓어요", top_k=2, industry="beauty")
    assert results[0].document.document_id == "good"


def test_store_search_dedupes_same_product_title():
    rag = RAGEngine()
    rag.documents = [
        RAGDocument(
            document_id="a",
            source="crawled_url",
            product_id="a",
            title="루이셀 퓨리파잉 세럼",
            content="모공 케어 세럼",
            metadata={"industry": "beauty"},
        ),
        RAGDocument(
            document_id="b",
            source="crawled_url",
            product_id="b",
            title="루이셀  퓨리파잉  세럼",
            content="모공 케어 세럼 상세",
            metadata={"industry": "beauty"},
        ),
    ]
    results = rag.search("모공 세럼", top_k=5, industry="beauty")
    assert len(results) == 1
