from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.industry import normalize_industry_key
from app.infrastructure.database.models import StoreKnowledgeModel


@dataclass
class RAGDocument:
    document_id: str
    source: str  # product, policy, faq, crawled_url
    product_id: Optional[str]
    title: str
    content: str
    metadata: Dict[str, Any]


@dataclass
class RAGSearchResult:
    document: RAGDocument
    score: float


# Beauty concern → ingredient/category vocabulary. Naive token overlap cannot
# connect "지성·모공" to "퓨리파잉 세럼"; this expansion makes the catalog
# searchable the way a human consultant thinks.
BEAUTY_CONCERN_EXPANSIONS = {
    "모공": ["모공", "피지", "세럼", "퓨리파잉", "클렌징", "BHA", "살리실"],
    "지성": ["지성", "피지", "모공", "세럼", "클렌징", "BHA"],
    "건성": ["건성", "보습", "수분", "히알루론", "세라마이드", "크림", "앰플"],
    "건조": ["건조", "보습", "수분", "히알루론", "세라마이드", "크림"],
    "민감": ["민감", "진정", "시카", "아줄렌", "판테놀", "순한"],
    "홍조": ["홍조", "진정", "시카", "아줄렌", "판테놀"],
    "미백": ["미백", "나이아신", "비타민C", "화이트닝", "톤업", "색소"],
    "기미": ["기미", "미백", "나이아신", "화이트닝", "색소"],
    "주름": ["주름", "탄력", "콜라겐", "펩타이드", "레티놀", "EGF"],
    "탄력": ["탄력", "주름", "콜라겐", "펩타이드", "EGF"],
    "여드름": ["여드름", "트러블", "진정", "시카", "BHA", "살리실"],
    "트러블": ["트러블", "진정", "시카", "BHA"],
    "각질": ["각질", "필링", "AHA", "BHA", "PHA"],
}


def expand_query_tokens(query: str, industry: Optional[str] = None) -> set:
    """Query tokens + concern synonyms (beauty only)."""
    tokens = set((query or "").lower().split())
    if normalize_industry_key(industry or "") != "beauty":
        return tokens
    q = (query or "").lower()
    for concern, extras in BEAUTY_CONCERN_EXPANSIONS.items():
        if concern in q:
            tokens.update(t.lower() for t in extras)
    return tokens


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
    "피부트러블": "사용 중 피부 이상 반응/트러블 발생 시 안내:\n1. 즉시 사용을 중단해 주세요.\n2. 증상이 심하거나 지속되면 피부과 전문의 상담을 받으시길 권장합니다.\n3. 트러블 접수는 고객센터를 통해 상담 후 사례별로 안내해 드립니다. (반품·환불 가능 여부는 상품 상태와 접수 사유에 따라 달라질 수 있습니다.)",
    "개봉반품": "화장품 개봉 후 반품 규정:\n전자상거래법상 보호 씰(Virgin Seal)을 훼손하거나 개봉한 상품은 단순 변심 반품이 불가합니다. (단, 상품 하자·배송 누유 등 접수 사유는 개봉 여부와 무관하게 상담 후 안내 가능합니다.)",
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
        metadata={
            "industry": "fresh_food",
            "category": "fruit",
            "variety": "설향",
            "price": 24000,
            "purchase_url": "/products/strawberry",
        },
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
        metadata={
            "industry": "fresh_food",
            "category": "fruit",
            "variety": "대저",
            "price": 28000,
            "purchase_url": "/products/tomato",
        },
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
        metadata={"industry": "fresh_food", "scope": "claims"},
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
    RAGDocument(
        document_id="DOC-BEAUTY-001",
        source="product",
        product_id="PROD-CICA-AMPOULE-01",
        title="시카 수딩 리페어 앰플 전성분 및 민감성 피부 사용 가이드",
        content=(
            "핵심 성분: 병풀추출물(시카) 85%, 판테놀 5%, 히알루론산, 마데카소사이드.\n"
            "안전성: 20가지 주의 성분 무첨가, 전성분 EWG 그린 등급, 저자극 테스트 완료.\n"
            "민감성 피부/임산부: 인공 향료 및 색소가 배제되어 임산부 및 극민감성 피부도 안심하고 사용 가능합니다.\n"
            "사용 순서: 토너 정리 후 스포이드로 2~3방울 떨어뜨려 부드럽게 흡수시켜 주세요."
        ),
        metadata={
            "industry": "beauty",
            "category": "skincare",
            "ewg": "green",
            "price": 32000,
            "purchase_url": "/products/cica-ampoule",
            "tags": "민감성,진정,시카,임산부,수분,트러블,건성",
        },
    ),
]


class RAGEngine:
    """RAG & FAQ retrieval engine ensuring zero hallucinations and source metadata attribution."""

    def __init__(self, documents: Optional[List[RAGDocument]] = None):
        self.documents = documents or DEFAULT_KNOWLEDGE_DOCS

    def lookup_deterministic_faq(
        self, query: str, exclude_keywords: Optional[set] = None
    ) -> Optional[str]:
        """Check deterministic FAQs. Costs 0 tokens.

        `exclude_keywords`: global FAQ keys superseded by the store's own
        policy (e.g. skip '배송비' when shipping_policy is configured).
        """
        blocked = exclude_keywords or set()
        clean_q = query.replace(" ", "").lower()
        for keyword, answer in DETERMINISTIC_FAQS.items():
            if keyword in clean_q:
                if keyword in blocked:
                    continue
                return answer
        return None

    def _score_doc(self, query: str, query_tokens: set, doc: RAGDocument) -> float:
        tags_str = str(doc.metadata.get("tags") or "")
        doc_text = (doc.title + " " + doc.content + " " + tags_str).lower()
        matches = sum(1 for token in query_tokens if len(token) >= 2 and token in doc_text)
        # Also check 2-char Korean keyword substrings from query
        clean_q = query.replace("?", "").replace("!", "").lower()
        for word in clean_q.split():
            if len(word) >= 2 and word[:2] in doc_text:
                matches += 1
        # A token in the product NAME is a much stronger signal than a passing
        # mention in a long description (junk pages otherwise outrank products).
        title_text = (doc.title or "").lower()
        title_hits = sum(1 for token in query_tokens if len(token) >= 2 and token in title_text)
        matches += title_hits * 2
        if matches > 0:
            return round(matches / (len(query_tokens) + 1), 2)
        return 0.0

    @staticmethod
    def _digest_doc_content(text: str, head: int = 600, extra: int = 400) -> str:
        """Keep the useful head of a long crawled page plus its ingredient block.

        Crawled Cafe24 pages carry nav/footer/options noise that bloats the
        prompt and delays the first token. The head holds title, price, volume
        and the product summary; if the ingredient/summary section appears
        later, keep a window around it so answer quality does not drop.
        """
        body = (text or "").strip()
        if len(body) <= 1200:
            return body
        parts = [body[:head].rstrip()]
        for marker in ("전성분", "상품요약정보", "사용법", "성분", "효능"):
            idx = body.find(marker)
            if idx >= head:
                parts.append(body[idx : idx + extra].strip())
                break
        return (" … ".join(parts))[: head + extra + 5].rstrip()

    @staticmethod
    def _dedupe_results(results: List[RAGSearchResult], top_k: int) -> List[RAGSearchResult]:
        """Same product crawled under several URLs must not eat multiple slots."""
        out: List[RAGSearchResult] = []
        seen: set = set()
        for r in results:
            title = re.sub(r"\s+", "", (r.document.title or "").lower())
            key = title or r.document.document_id
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
            if len(out) >= top_k:
                break
        return out

    @staticmethod
    def _doc_matches_industry(doc: RAGDocument, industry: Optional[str]) -> bool:
        """True when default doc is allowed for this store industry (no cross-leak)."""
        if not (industry or "").strip():
            return False
        key = normalize_industry_key(industry)
        meta_raw = (doc.metadata.get("industry") or "").strip()
        if not meta_raw:
            return False
        return normalize_industry_key(meta_raw) == key

    def search(
        self, query: str, top_k: int = 2, industry: Optional[str] = None
    ) -> List[RAGSearchResult]:
        """Search default in-memory documents using token overlap & keyword relevance scoring."""
        query_tokens = expand_query_tokens(query, industry)
        results: List[RAGSearchResult] = []

        for doc in self.documents:
            if industry is not None and not self._doc_matches_industry(doc, industry):
                continue
            score = self._score_doc(query, query_tokens, doc)
            if score > 0:
                results.append(RAGSearchResult(document=doc, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return self._dedupe_results(results, top_k)

    async def search_with_store_knowledge(
        self,
        session: AsyncSession,
        mall_id: str,
        query: str,
        top_k: int = 2,
        industry: Optional[str] = None,
    ) -> List[RAGSearchResult]:
        """Store DB knowledge first. Default demo docs only if store has zero rows,
        and only docs tagged for the same industry (prevents strawberry leaking into beauty)."""
        query_tokens = expand_query_tokens(query, industry)
        results: List[RAGSearchResult] = []

        q = select(StoreKnowledgeModel).where(StoreKnowledgeModel.mall_id == mall_id)
        db_res = await session.execute(q)
        store_docs = db_res.scalars().all()

        for sdoc in store_docs:
            if not (sdoc.title or "").strip():
                continue
            rag_doc = RAGDocument(
                document_id=sdoc.id,
                source=sdoc.doc_type,
                product_id=sdoc.id,
                title=sdoc.title,
                content=sdoc.content,
                metadata={
                    "mall_id": sdoc.mall_id,
                    "price": sdoc.price,
                    "original_price": getattr(sdoc, "original_price", None),
                    "purchase_url": sdoc.purchase_url or sdoc.source_url,
                    "image_url": sdoc.image_url,
                    "tags": sdoc.tags,
                },
            )
            score = self._score_doc(query, query_tokens, rag_doc)
            if score > 0:
                results.append(RAGSearchResult(document=rag_doc, score=round(score + 0.5, 2)))

        # Defaults only when this mall has no learned knowledge yet.
        if not store_docs:
            for doc in self.documents:
                if not self._doc_matches_industry(doc, industry):
                    continue
                score = self._score_doc(query, query_tokens, doc)
                if score > 0:
                    results.append(RAGSearchResult(document=doc, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return self._dedupe_results(results, top_k)

    def assemble_context(
        self,
        search_results: List[RAGSearchResult],
        reject_prices: Optional[set] = None,
    ) -> str:
        """Assemble retrieved documents into context with strict citation format."""
        if not search_results:
            return ""

        reject = reject_prices or set()
        context_lines = ["--- [참고 공식 지식 베이스] ---"]
        # Long crawled pages (nav/footer/options) bloat the prompt and slow the
        # first token. Keep the head of each doc — title, price, summary and
        # ingredients appear there — and cap how many docs reach the model.
        for res in search_results[:12]:
            doc = res.document
            raw_price = doc.metadata.get("price")
            raw_orig = doc.metadata.get("original_price")
            try:
                price_i = int(raw_price) if raw_price is not None else None
            except (TypeError, ValueError):
                price_i = None
            try:
                orig_i = int(raw_orig) if raw_orig is not None else None
            except (TypeError, ValueError):
                orig_i = None
            if price_i is not None and price_i in reject:
                price_i = None
            if orig_i is not None and orig_i in reject:
                orig_i = None
            if price_i and orig_i and orig_i > price_i:
                price_info = f" | 판매가: {price_i:,}원 (정상가 {orig_i:,}원, 할인 중)"
            elif price_i:
                price_info = f" | 판매가: {price_i:,}원"
            else:
                price_info = ""
            body = self._digest_doc_content(doc.content)
            context_lines.append(
                f"[문서 ID: {doc.document_id} | 제목: {doc.title}{price_info} | 출처: {doc.source} | 일치도: {res.score}]\n{body}\n"
            )
        context_lines.append(
            "--- [지침: 위 참고 지식 베이스에 명시된 사실만 답변하십시오. "
            "여기에 없는 상품명은 절대 새로 만들어내지 마십시오.] ---"
        )
        return "\n".join(context_lines)


rag_engine = RAGEngine()
