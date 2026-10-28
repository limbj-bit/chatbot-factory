from app.infrastructure.rag.engine import RAGEngine


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


def test_rag_search_and_context_assembly():
    rag = RAGEngine()

    # Search for strawberry storage
    results = rag.search("딸기 보관 방법")
    assert len(results) > 0
    top_doc = results[0].document
    assert "설향 딸기" in top_doc.title
    assert "냉장(0~4℃)" in top_doc.content
    assert top_doc.metadata["variety"] == "설향"

    context = rag.assemble_context(results)
    assert "[문서 ID: DOC-PROD-001" in context
    assert "참고 공식 지식 베이스" in context
