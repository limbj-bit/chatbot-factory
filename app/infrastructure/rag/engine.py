from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class RAGDocument:
    document_id: str
    source: str  # product, policy, faq
    product_id: Optional[str]
    title: str
    content: str
    metadata: Dict[str, Any]


@dataclass
class RAGSearchResult:
    document: RAGDocument
    score: float


# Deterministic FAQ dictionary for 0-token answers
DETERMINISTIC_FAQS = {
    "운영시간": "고객센터 운영시간은 평일 오전 9시부터 오후 6시까지(점심시간 12:00~13:00)이며, 주말 및 공휴일은 휴무입니다.",
    "고객센터": "고객센터 운영시간은 평일 오전 9시부터 오후 6시까지입니다.",
    "배송비": "기본 배송비는 3,000원이며, 40,000원 이상 구매 시 무료배송 혜택이 적용됩니다. (제주/도서산간 지역은 3,000원 추가)",
    "입금계좌": "무통장 입금 계좌는 [신한은행 110-123-456789 / 예금주: (주)신선식품공장] 입니다.",
    "반품정책": "신선식품의 특성상 단순 변심에 의한 반품은 불가하며, 상품 하자 또는 파손 시 수령 후 48시간 이내에 사진과 함께 접수해 주시면 전액 또는 부분 환불 처리됩니다.",
    "교환정책": "신선식품은 맞교환 시 상품 부패 위험이 있어, 상품 불량 확인 시 재배송 또는 환불로 처리해 드립니다.",
    "전원불량": "디지털/가전 전원이 켜지지 않는 경우 자가진단:\n1. 정품 충전 케이블 연결 후 15분 이상 충전해 보세요.\n2. 전원 버튼을 10초간 길게 눌러 강제 리셋을 시도하세요.\n3. 자가 해결이 안 되면 'A/S 사진 접수'를 통해 무상 수리를 신청하실 수 있습니다.",
    "사이즈교환": "의류 사이즈 교환 안내:\n상품 수령 후 7일 이내 상품 텍(Tag) 미제거 시 동일 상품에 한해 1회 무료 사이즈 맞교환이 가능합니다.",
}


DEFAULT_KNOWLEDGE_DOCS = [
    RAGDocument(
        document_id="DOC-PROD-001",
        source="product",
        product_id="PROD-STRAWBERRY-01",
        title="설향 딸기 1kg 보관 및 섭취 안내",
        content=(
            "설향 딸기는 과육이 부드럽고 당도가 높은 국산 품종입니다.\n"
            "보관 방법: 수령 즉시 꼭지를 떼지 않은 상태로 키친타월을 깐 밀폐용기에 담아 냉장(0~4℃) 보관하십시오.\n"
            "섭취 방법: 물에 30초 이상 담그지 말고 흐르는 물에 가볍게 씻어 즉시 드세요. 수령 후 2일 이내 섭취 권장."
        ),
        metadata={"category": "fruit", "variety": "설향"},
    ),
    RAGDocument(
        document_id="DOC-PROD-002",
        source="product",
        product_id="PROD-TOMATO-01",
        title="대저 짭짤이 토마토 보관 및 후숙 안내",
        content=(
            "대저 토마토는 초록빛이 감돌 때 특유의 짭짤하고 아삭한 맛이 가장 좋습니다.\n"
            "보관 방법: 냉장고에 바로 넣지 마시고 통풍이 잘되는 서늘한 상온(15~20℃)에서 2~3일 후숙하여 붉은빛이 돌 때 드세요.\n"
            "주의: 냉장 보관 시 고유의 산미와 식감이 저하될 수 있습니다."
        ),
        metadata={"category": "fruit", "variety": "대저"},
    ),
    RAGDocument(
        document_id="DOC-POLICY-001",
        source="policy",
        product_id=None,
        title="신선식품 품질 보상 제도 기준",
        content=(
            "신선식품 파손 및 변질 보상 규정:\n"
            "1. 배송 완료 시점으로부터 48시간 이내 접수 건에 한하여 보상 심사가 진행됩니다.\n"
            "2. 손상 면적 및 과육 무름 비율이 30% 이상인 경우 전액 환불 또는 새 상품 무료 재배송을 지원합니다.\n"
            "3. 손상 비율이 10% 이상 30% 미만인 경우 해당 비율만큼 부분 환불 또는 적립금을 지급합니다.\n"
            "4. 사진이 흐리거나 손상 부위가 식별되지 않는 경우 재촬영을 요청드릴 수 있습니다."
        ),
        metadata={"scope": "claims"},
    ),
    RAGDocument(
        document_id="DOC-AS-ELEC-001",
        source="as_troubleshooting",
        product_id=None,
        title="디지털/가전 스마트 A/S 보증 규정 및 자가진단",
        content=(
            "디지털/가전 무상 A/S 규정:\n"
            "1. 보증 기간: 구매일로부터 1년 무상 보증 (소모품 배터리는 6개월).\n"
            "2. 초기 불량(수령 후 14일 이내): 자가진단(리셋, 충전 확인) 후에도 전원 미작동 시 100% 새 제품 맞교환.\n"
            "3. 파손/침수 등 고객 과실은 유상 수리로 전환되며, 사진 제출 시 수리 견적이 사전 안내됩니다."
        ),
        metadata={"industry": "electronics", "scope": "warranty"},
    ),
]


class RAGEngine:
    """RAG & FAQ retrieval engine ensuring zero hallucinations and source metadata attribution."""

    def __init__(self, documents: Optional[List[RAGDocument]] = None):
        self.documents = documents or DEFAULT_KNOWLEDGE_DOCS

    def lookup_deterministic_faq(self, query: str) -> Optional[str]:
        """Check deterministic FAQs first. Costs 0 tokens."""
        clean_q = query.replace(" ", "").lower()
        for keyword, answer in DETERMINISTIC_FAQS.items():
            if keyword in clean_q:
                return answer
        return None

    def search(self, query: str, top_k: int = 2) -> List[RAGSearchResult]:
        """Search documents using token overlap & keyword relevance scoring."""
        query_tokens = set(query.lower().split())
        results: List[RAGSearchResult] = []

        for doc in self.documents:
            doc_text = (doc.title + " " + doc.content).lower()
            # Calculate simple TF match score
            matches = sum(1 for token in query_tokens if token in doc_text)
            if matches > 0:
                score = round(matches / (len(query_tokens) + 1), 2)
                results.append(RAGSearchResult(document=doc, score=score))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def assemble_context(self, search_results: List[RAGSearchResult]) -> str:
        """Assemble retrieved documents into context with strict citation format."""
        if not search_results:
            return ""

        context_lines = ["--- [참고 공식 지식 베이스] ---"]
        for res in search_results:
            doc = res.document
            context_lines.append(
                f"[문서 ID: {doc.document_id} | 제목: {doc.title} | 출처: {doc.source} | 일치도: {res.score}]\n{doc.content}\n"
            )
        context_lines.append("--- [지침: 위 참고 지식 베이스에 명시된 사실만 답변하십시오] ---")
        return "\n".join(context_lines)


rag_engine = RAGEngine()
