import json
import re
import time
import uuid
from typing import AsyncIterator, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.commerce_service import commerce_service
from app.application.order_service import OrderService
from app.application.store_service import store_service
from app.core.industry import INDUSTRY_KR as _INDUSTRY_KR, normalize_industry_key
from app.core.language import detect_language, LANGUAGE_NAMES
from app.core.logging import logger
from app.domain.orders.models import Order, OrderStatus
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.router import AIProviderRouter
from app.infrastructure.database.models import MessageModel, SessionModel, StoreModel
from app.infrastructure.rag.engine import RAGEngine, RAGSearchResult, rag_engine
from app.schemas.chat import ProductRecommendationCard

# Real Cafe24 order no (e.g. 20261028-0000012) OR our test order id (ORD-...)
_ORDER_ID_RE = re.compile(r"(\d{8}-\d{7}|ORD-[A-Za-z0-9-]+)")

# How many recent turns to feed the LLM for multi-turn memory.
_HISTORY_LIMIT = 10

# Matches a claim/refund window like "7일 이내" / "3일 이하" in an LLM reply.
_CLAIM_DAY_RE = re.compile(r"(\d+)\s*일\s*(이내|이하|안에)")

# Order/shipping *tracking* (not policy). Policy questions must not hit Cafe24 lookup.
_ORDER_TRACKING_KW = (
    "주문조회",
    "배송조회",
    "운송장",
    "송장번호",
    "택배조회",
    "내주문",
    "주문상태",
    "배송상태",
    "어디쯤",
    "출고됐",
    "출고되었",
)
_SHIPPING_POLICY_KW = (
    "배송비",
    "무료배송",
    "택배비",
    "배송기간",
    "배송일",
    "소요일",
    "제주",
    "도서산간",
)

_STATUS_KOR = {
    OrderStatus.PAID: "결제 완료",
    OrderStatus.PREPARING: "상품 준비 중",
    OrderStatus.SHIPPING: "배송 중",
    OrderStatus.DELIVERED: "배송 완료",
    OrderStatus.CANCELLED: "주문 취소",
    OrderStatus.REFUNDED: "반품/환불",
}


# Backward-compatible aliases (beauty defaults). Prefer _counsel_keywords(industry).
RECOMMENDATION_KEYWORDS = [
    "추천", "건조", "건성", "민감", "진정", "트러블", "홍조", "임산부",
    "보습", "수분", "시카", "앰플", "크림", "토너", "선물", "성분",
    "전성분", "나이아신", "바르면", "뭐가",
]

SKIN_DETAIL_KEYWORDS = [
    "건성", "지성", "복합성", "민감성", "중성", "피부타입",
    "주름", "미백", "트러블", "보습", "모공", "기미", "진정", "탄력",
    "건조", "여드름", "각질", "홍조", "색소", "칙칙", "리프팅",
    "안티에이징", "노화", "수분", "유분", "T존", "U존",
    "성분", "전성분", "레티놀", "히알루론산", "비타민", "나이아신아마이드",
    "세라마이드", "콜라겐", "펩타이드", "AHA", "BHA", "PHA", "CICA", "시카",
    "사용법", "어떻게", "언제", "루틴", "순서", "아침", "저녁",
    "가격", "얼마", "용량", "ml", "g", "mg",
]

_FRESH_RECOMMEND = [
    "추천", "선물", "뭐가", "보관", "먹는법", "섭취", "레시피", "제철",
    "맛", "당도", "신선", "고르", "어떤", "세트", "과일", "채소",
]
_FRESH_DETAIL = [
    "보관", "냉장", "냉동", "상온", "후숙", "씻", "섭취", "레시피", "요리",
    "당도", "품종", "산지", "제철", "유통기한", "소비기한", "해동", "손질",
    "가격", "얼마", "kg", "인분", "몇개", "몇 개", "선물", "알레르기", "알러지",
    "상했", "무름", "변질", "파손", "택배지연", "아이간식", "임산부",
]
_FASHION_RECOMMEND = [
    "추천", "선물", "뭐가", "사이즈", "코디", "어울", "핏", "스타일", "고르", "어떤",
]
_FASHION_DETAIL = [
    "사이즈", "치수", "가슴", "허리", "기장", "소재", "원단", "세탁", "코디",
    "색상", "컬러", "핏", "오버핏", "슬림", "정장", "캐주얼", "가격", "얼마",
    "교환", "착용", "착용감", "키", "몸무게", "총장",
]
_ELECTRONICS_RECOMMEND = [
    "추천", "뭐가", "고르", "어떤", "스펙", "호환", "AS", "고장", "비교",
]
_ELECTRONICS_DETAIL = [
    "스펙", "호환", "모델", "배터리", "충전", "보증", "AS", "용량", "인치",
    "와이파이", "블루투스", "가격", "얼마", "사용법", "설정", "전원", "리셋",
]
_PET_RECOMMEND = [
    "추천", "뭐가", "고르", "사료", "간식", "장난감", "선물",
]
_PET_DETAIL = [
    "사료", "간식", "나이", "개월", "견종", "묘종", "알러지", "알레르기",
    "체중", "급여", "가격", "얼마", "성분", "급여량", "강아지", "고양이",
]
_RAW_RECOMMEND = ["추천", "규격", "COA", "MSDS", "공급", "샘플", "뭐가", "고르"]
_RAW_DETAIL = [
    "규격", "COA", "MSDS", "함량", "순도", "원료", "성분", "레티놀", "나이아신",
    "가격", "얼마", "MOQ", "샘플", "납기", "제조사",
]
_BABY_RECOMMEND = ["추천", "뭐가", "고르", "용품", "개월", "월령", "선물"]
_BABY_DETAIL = [
    "개월", "월령", "신생아", "유아", "KC", "안전", "소재", "사이즈", "가격", "얼마",
    "이유식", "젖병", "카시트", "유모차",
]
_SPORTS_RECOMMEND = ["추천", "뭐가", "고르", "스펙", "호환", "캠핑", "장비"]
_SPORTS_DETAIL = [
    "스펙", "호환", "사이즈", "모델", "텐트", "캠핑", "등반", "가격", "얼마", "AS", "무게",
]
_CLINIC_RECOMMEND = ["예약", "진료", "시술", "상담", "과목", "안내"]
_CLINIC_DETAIL = [
    "예약", "초진", "재진", "진료시간", "야간", "주말", "주차", "비용", "비급여",
    "증명서", "위치", "과목", "시술",
]
_EDU_RECOMMEND = ["추천", "수강", "레벨", "반", "커리큘럼", "체험"]
_EDU_DETAIL = [
    "레벨", "수강료", "시간표", "개강", "환불", "체험", "테스트", "과목", "가격", "얼마",
]
_LEGAL_RECOMMEND = ["상담", "예약", "자문", "수임", "문의"]
_LEGAL_DETAIL = [
    "예약", "수임료", "자문", "서류", "계약", "세무", "노무", "법률", "비밀", "절차",
]
_INTERIOR_RECOMMEND = ["견적", "상담", "시공", "추천", "문의"]
_INTERIOR_DETAIL = [
    "평수", "견적", "실측", "시공", "자재", "포트폴리오", "AS", "하자", "예산", "일정",
]
_HOTEL_RECOMMEND = ["예약", "객실", "문의", "요금"]
_HOTEL_DETAIL = [
    "예약", "체크인", "체크아웃", "인원", "조식", "수영장", "취소", "환불", "요금", "주차",
]
_IT_RECOMMEND = ["도입", "데모", "요금제", "문의", "제휴"]
_IT_DETAIL = [
    "요금제", "데모", "도입", "제휴", "장애", "지원", "API", "엔터프라이즈", "가격", "얼마",
]
_FNB_RECOMMEND = ["예약", "메뉴", "추천", "가맹", "문의"]
_FNB_DETAIL = [
    "예약", "인원", "메뉴", "알레르기", "알러지", "영업시간", "주차", "포장", "배달", "가맹",
]
_GENERAL_RECOMMEND = ["추천", "선물", "뭐가", "고르", "어떤"]
_GENERAL_DETAIL = ["가격", "얼마", "사용법", "어떻게", "스펙", "구성", "옵션"]

# Explicit product lookup / buy intent — always attach cards when RAG hits products.
_PRODUCT_LOOKUP_KW = (
    "찾아",
    "검색",
    "있냐",
    "있나요",
    "있어요",
    "있어?",
    "보여",
    "보여줘",
    "사진",
    "이미지",
    "골라",
    "상품",
    "제품",
    "구매",
    "링크",
    "상세",
    "사는곳",
    "어디서",
    "품번",
    "재고",
    "유니폼",
)

_INDUSTRY_COUNSEL: Dict[str, Tuple[List[str], List[str]]] = {
    "beauty": (RECOMMENDATION_KEYWORDS, SKIN_DETAIL_KEYWORDS),
    "fresh_food": (_FRESH_RECOMMEND, _FRESH_DETAIL),
    "fashion": (_FASHION_RECOMMEND, _FASHION_DETAIL),
    "electronics": (_ELECTRONICS_RECOMMEND, _ELECTRONICS_DETAIL),
    "pet_supplies": (_PET_RECOMMEND, _PET_DETAIL),
    "raw_materials": (_RAW_RECOMMEND, _RAW_DETAIL),
    "baby_kids": (_BABY_RECOMMEND, _BABY_DETAIL),
    "sports_leisure": (_SPORTS_RECOMMEND, _SPORTS_DETAIL),
    "medical_clinic": (_CLINIC_RECOMMEND, _CLINIC_DETAIL),
    "education_academy": (_EDU_RECOMMEND, _EDU_DETAIL),
    "professional_legal": (_LEGAL_RECOMMEND, _LEGAL_DETAIL),
    "interior_realestate": (_INTERIOR_RECOMMEND, _INTERIOR_DETAIL),
    "hotel_travel": (_HOTEL_RECOMMEND, _HOTEL_DETAIL),
    "it_corporate": (_IT_RECOMMEND, _IT_DETAIL),
    "restaurant_cafe": (_FNB_RECOMMEND, _FNB_DETAIL),
    "general": (_GENERAL_RECOMMEND, _GENERAL_DETAIL),
}


def _counsel_keywords(industry: Optional[str]) -> Tuple[List[str], List[str]]:
    """Return (recommendation_keywords, detail_keywords) for the store industry."""
    key = normalize_industry_key(industry)
    return _INDUSTRY_COUNSEL.get(key, _INDUSTRY_COUNSEL["general"])


def wants_product_cards(
    message_text: str,
    convo_text: str,
    industry: Optional[str],
) -> bool:
    """True when lookup/recommend/detail intent should attach product cards."""
    msg = message_text or ""
    convo = convo_text or msg
    rec_kw, detail_kw = _counsel_keywords(industry)
    if any(k in msg for k in _PRODUCT_LOOKUP_KW):
        return True
    if any(k in msg for k in rec_kw):
        return True
    if any(k in convo for k in detail_kw):
        return True
    return False


def _normalize_product_query(message_text: str) -> str:
    """Strip verbs/particles so '진주를 보여줘'→'진주', '유니폼이 있니'→'유니폼'."""
    raw = (message_text or "").strip()
    cleaned = re.sub(
        r"[을를이가은는좀]?\s*"
        r"(보여\s*줘|보여줘|찾아\s*줘|찾아줘|검색|알려\s*줘|골라\s*줘|추천해\s*줘|"
        r"있니|있나요|있어요|있어\??|있냐|뭐야|뭐\s*있어).*$",
        "",
        raw,
    )
    cleaned = re.sub(
        r"(보여|찾아|검색|알려|골라|추천|있니|있나요|있어요|있어|있냐)\s*$",
        "",
        cleaned,
    )
    cleaned = re.sub(r"[을를이가은는]\s*$", "", cleaned)
    return re.sub(r"\s+", "", cleaned).strip()


def _product_hits(results: Optional[List[RAGSearchResult]]) -> List[RAGSearchResult]:
    if not results:
        return []
    return [r for r in results if r.document.source in ("product", "crawled_url")]


def filter_results_for_cards(
    message_text: str,
    results: Optional[List[RAGSearchResult]],
    *,
    max_cards: int = 5,
) -> List[RAGSearchResult]:
    """Prefer title/content matches for the query token; else all product hits (cap)."""
    hits = _product_hits(results)
    if not hits:
        return []
    token = _normalize_product_query(message_text)
    if len(token) >= 2:
        matched = []
        for r in hits:
            title = re.sub(r"\s+", "", r.document.title or "")
            snippet = re.sub(r"\s+", "", (r.document.content or "")[:200])
            if token in title or token in snippet or title in token:
                matched.append(r)
        if matched:
            return matched[:max_cards]
    return hits[:max_cards]


def message_matches_product_hit(
    message_text: str, results: Optional[List[RAGSearchResult]]
) -> bool:
    """True when the user message names a retrieved product (follow-up like '진주')."""
    return bool(filter_results_for_cards(message_text, results, max_cards=1))


def should_attach_product_cards(
    message_text: str,
    convo_text: str,
    industry: Optional[str],
    results: Optional[List[RAGSearchResult]] = None,
) -> bool:
    if wants_product_cards(message_text, convo_text, industry):
        return bool(_product_hits(results)) if results is not None else True
    return message_matches_product_hit(message_text, results)


class ChatService:
    """Application Service for chat orchestration, multi-tenant RAG, AI beauty/shopping counselor, quota gating, and SSE streaming."""

    def __init__(
        self,
        ai_router: Optional[AIProviderPort] = None,
        rag: Optional[RAGEngine] = None,
        order_service: Optional[OrderService] = None,
    ):
        self.ai_router = ai_router or AIProviderRouter()
        self.rag = rag or rag_engine
        self.order_service = order_service or OrderService()

    async def get_or_create_session(
        self,
        session_db: AsyncSession,
        session_id: Optional[str],
        customer_id: str = "guest",
        mall_id: str = "demo_mall",
    ) -> SessionModel:
        if session_id:
            res = await session_db.execute(
                select(SessionModel).where(
                    SessionModel.id == session_id,
                    SessionModel.mall_id == mall_id,
                )
            )
            chat_session = res.scalar_one_or_none()
            if chat_session:
                return chat_session
            # Same id under another mall (or legacy row): never hijack — mint a new id.
            clash = await session_db.execute(
                select(SessionModel.id).where(SessionModel.id == session_id)
            )
            if clash.scalar_one_or_none() is not None:
                session_id = None

        new_id = session_id or str(uuid.uuid4())
        chat_session = SessionModel(
            id=new_id,
            customer_id=customer_id,
            mall_id=mall_id,
            channel="web_widget",
        )
        session_db.add(chat_session)
        await session_db.commit()
        await session_db.refresh(chat_session)
        return chat_session

    @staticmethod
    def _shipping_reject_prices(store_obj: Optional[StoreModel]) -> set:
        from app.application.product_price_extract import reject_price_set

        policy = ChatService._parse_policy_dict(store_obj)
        ship = policy.get("shipping_policy")
        ship = ship if isinstance(ship, dict) else {}
        return reject_price_set(ship.get("delivery_fee"), ship.get("free_over_amount"))

    @staticmethod
    def _build_product_cards(
        search_results: List[RAGSearchResult],
        *,
        reject_prices: Optional[set] = None,
    ) -> List[ProductRecommendationCard]:
        cards: List[ProductRecommendationCard] = []
        reject = reject_prices or set()
        for r in search_results:
            doc = r.document
            if doc.source in ("product", "crawled_url"):
                price = doc.metadata.get("price")
                orig = doc.metadata.get("original_price")
                try:
                    price_i = int(price) if price is not None else None
                except (TypeError, ValueError):
                    price_i = None
                try:
                    orig_i = int(orig) if orig is not None else None
                except (TypeError, ValueError):
                    orig_i = None
                if price_i is not None and price_i in reject:
                    price_i = None
                if orig_i is not None and orig_i in reject:
                    orig_i = None
                on_sale = bool(price_i and orig_i and orig_i > price_i)
                discount_pct = None
                if not on_sale:
                    orig_i = None
                elif price_i and orig_i:
                    discount_pct = max(
                        1, min(99, int(round((1 - price_i / orig_i) * 100)))
                    )
                cards.append(
                    ProductRecommendationCard(
                        product_id=doc.product_id or doc.document_id,
                        title=doc.title,
                        price=price_i,
                        original_price=orig_i,
                        on_sale=on_sale,
                        discount_percent=discount_pct,
                        summary=doc.content[:140] + ("..." if len(doc.content) > 140 else ""),
                        purchase_url=doc.metadata.get("purchase_url"),
                        image_url=doc.metadata.get("image_url"),
                        tags=doc.metadata.get("tags"),
                    )
                )
        return cards

    @staticmethod
    def _parse_policy_dict(store_obj: Optional[StoreModel]) -> Dict:
        if store_obj is None:
            return {}
        try:
            policy = json.loads(store_obj.policy_config_json or "{}")
        except Exception:
            return {}
        return policy if isinstance(policy, dict) else {}

    @staticmethod
    def _is_order_tracking_intent(message_text: str) -> bool:
        """True only for tracking/status lookups — never for shipping/claim policy Qs."""
        if _ORDER_ID_RE.search(message_text):
            return True
        clean = message_text.replace(" ", "").lower()
        if any(k in clean for k in _SHIPPING_POLICY_KW):
            return False
        if any(k in clean for k in ("반품", "교환", "환불", "클레임")):
            return False
        if any(k in clean for k in _ORDER_TRACKING_KW):
            return True
        if "주문" in clean and any(k in clean for k in ("어디", "상태", "조회", "확인")):
            return True
        if "배송" in clean:
            if any(k in clean for k in ("며칠", "기간", "소요", "얼마나걸려", "얼마나 걸려")):
                return False
            if any(k in clean for k in ("어디", "상태", "조회", "추적", "도착했", "언제와")):
                return True
        return False

    @classmethod
    def _global_faq_keywords_covered_by_store(cls, store_obj: Optional[StoreModel]) -> set:
        """Global FAQ keys the store already owns — must not override store facts."""
        covered: set = set()
        if store_obj is None:
            return covered
        if (store_obj.business_hours or "").strip():
            covered.update({"운영시간", "고객센터"})
        policy = cls._parse_policy_dict(store_obj)
        ship = policy.get("shipping_policy")
        ship = ship if isinstance(ship, dict) else {}
        if isinstance(ship.get("delivery_fee"), (int, float)) or (ship.get("delivery_days") or "").strip():
            covered.add("배송비")
        claim = policy.get("claim_policy")
        claim = claim if isinstance(claim, dict) else {}
        max_days = claim.get("max_claim_days", policy.get("max_claim_days"))
        if isinstance(max_days, (int, float)):
            covered.update({"반품정책", "교환정책"})
        return covered

    @classmethod
    def _lookup_store_policy_faq(
        cls, message_text: str, store_obj: Optional[StoreModel]
    ) -> Optional[str]:
        """0-token answers grounded in the store's own hours / shipping / claim policy."""
        if store_obj is None:
            return None
        clean = message_text.replace(" ", "").lower()
        policy = cls._parse_policy_dict(store_obj)
        ship = policy.get("shipping_policy")
        ship = ship if isinstance(ship, dict) else {}
        claim = policy.get("claim_policy")
        claim = claim if isinstance(claim, dict) else {}
        store_name = (store_obj.store_name or "스토어").strip() or "스토어"

        if (
            "운영시간" in clean
            or "영업시간" in clean
            or ("고객센터" in clean and "시간" in clean)
        ):
            hours = (store_obj.business_hours or "").strip()
            if hours:
                return f"'{store_name}' 고객센터 운영시간은 {hours}입니다."

        if any(k in clean for k in ("배송비", "무료배송", "택배비")):
            parts: List[str] = []
            fee = ship.get("delivery_fee")
            if isinstance(fee, (int, float)):
                parts.append(f"기본 배송비는 {int(fee):,}원입니다.")
            free_over = ship.get("free_over_amount")
            if isinstance(free_over, (int, float)):
                parts.append(f"{int(free_over):,}원 이상 구매 시 무료배송입니다.")
            note = (ship.get("note") or "").strip()
            if note:
                parts.append(note)
            if parts:
                return " ".join(parts)

        if (
            any(k in clean for k in ("배송기간", "배송일", "소요일"))
            or ("배송" in clean and any(k in clean for k in ("며칠", "언제와", "얼마나")))
        ):
            days = (ship.get("delivery_days") or "").strip()
            if days:
                return f"배송 소요일 안내: {days}"

        if any(k in clean for k in ("반품정책", "교환정책", "반품기한", "교환기한")) or (
            any(k in clean for k in ("반품", "교환", "환불"))
            and any(k in clean for k in ("며칠", "기한", "기간", "정책"))
        ):
            max_days = claim.get("max_claim_days", policy.get("max_claim_days"))
            if isinstance(max_days, (int, float)):
                return (
                    f"'{store_name}' 반품/교환은 수령 후 {int(max_days)}일 이내 접수 가능합니다. "
                    "상품 하자·파손은 채팅창의 [사진으로 반품 접수]로 사진을 올려 주시면 빠르게 도와드립니다."
                )

        return None

    async def _resolve_zero_token_reply(
        self,
        session_db: AsyncSession,
        mall_id: str,
        rate_key: str,
        message_text: str,
        store_obj: Optional[StoreModel],
    ) -> Optional[Tuple[str, str]]:
        """Store policy → AS scenario → order tracking → global FAQ."""
        from app.application.as_chat_bridge import handle_as_turn

        store_faq = self._lookup_store_policy_faq(message_text, store_obj)
        if store_faq:
            return "store_policy_faq", store_faq

        # Cancel / exchange / return / staff handoff (multi-turn machine)
        as_reply = await handle_as_turn(session_db, rate_key, mall_id, message_text)
        if as_reply:
            return as_reply

        if self._is_order_tracking_intent(message_text):
            reply = await self._lookup_order_reply(
                session_db, mall_id, rate_key, message_text
            )
            return "shipping_inquiry", reply

        covered = self._global_faq_keywords_covered_by_store(store_obj)
        global_faq = self.rag.lookup_deterministic_faq(
            message_text, exclude_keywords=covered
        )
        if global_faq:
            return "faq_deterministic", global_faq

        return None

    async def _lookup_order_reply(
        self,
        session_db: AsyncSession,
        mall_id: str,
        rate_key: str,
        message_text: str,
    ) -> str:
        """Resolve an order/shipping inquiry to a customer-facing reply.

        - Real Cafe24 order no (YYYYMMDD-0000000): live lookup via the mall's own
          token (auto-refresh). Only connected malls can see real data.
        - Test order id (ORD-...): served only when the mall has NO live connection
          (i.e. showroom preview). Connected malls never receive mock orders.
        - PII (name/address/phone) is never included.
        """
        m = _ORDER_ID_RE.search(message_text)
        if not m:
            return "주문 및 배송 조회를 원하시면 주문번호(예: 20261028-0000012 또는 ORD-NORMAL)를 함께 입력해 주세요."

        order_no = m.group(1)
        is_real_format = bool(re.fullmatch(r"\d{8}-\d{7}", order_no))

        # Per-conversation rate limit (brute-force protection)
        if not commerce_service._rate_allow(rate_key):
            return "조회 요청이 너무 잦습니다. 잠시 후(1분 뒤) 다시 시도해 주세요."

        conn = await commerce_service.get_connection(session_db, mall_id)
        has_live_conn = conn is not None and conn.status in ("connected", "refresh_expired")

        if is_real_format:
            order, err = await commerce_service.lookup_order(session_db, mall_id, order_no)
            if order:
                return self._format_order_reply(order)
            return err or "주문 조회가 일시 점검 중입니다. 잠시 후 다시 시도해 주세요."

        # Test order id (ORD-...): block for any mall with a live connection
        if has_live_conn:
            return "주문번호를 다시 확인해 주세요."

        order = await self.order_service.get_order_details(order_no)
        if order:
            return self._format_order_reply(order)
        return "주문번호를 다시 확인해 주세요."

    @staticmethod
    def _format_order_reply(order: Order) -> str:
        status_kor = _STATUS_KOR.get(order.status, "배송 진행 중")
        product = order.items[0].product_name if order.items else "상품"
        lines = [f"📦 주문 {order.order_id} · [{status_kor}] · 상품: {product}"]
        if order.carrier_name or order.shipping_code:
            carrier = order.carrier_name or "택배사"
            tracking = order.shipping_code or "-"
            lines.append(f"🚚 {carrier} {tracking}")
        return "\n".join(lines)

    @staticmethod
    def _deterministic_intake_reply(
        industry: Optional[str], message_text: str, convo_text: str
    ) -> Optional[str]:
        """Fixed first-turn questions when customer asks for recommendations vaguely."""
        rec_kw, detail_kw = _counsel_keywords(industry)
        msg = message_text or ""
        convo = convo_text or ""
        wants_counsel = any(k in msg for k in rec_kw)
        # Quick-button labels often contain meta words like "피부타입별 추천" —
        # those are CTAs, not answered intake. Strip CTA noise before detail check.
        detail_probe = convo
        for noise in (
            "피부타입별",
            "맞춤 상품",
            "상품 추천",
            "맞춤 추천",
            "전성분 &",
            "다른 질문",
        ):
            detail_probe = detail_probe.replace(noise, " ")
        # "피부타입" alone inside a menu label should not count as answered
        meaningful_detail = [k for k in detail_kw if k not in ("피부타입", "추천")]
        has_detail = any(k in detail_probe for k in meaningful_detail)
        if not wants_counsel or has_detail:
            return None
        key = normalize_industry_key(industry)
        if key == "beauty":
            return (
                "맞춤 추천을 위해 먼저 여쭤볼게요.\n"
                "1) 피부타입은 건성 / 지성 / 복합성 / 민감성 중 어디에 가까우신가요?\n"
                "2) 지금 가장 신경 쓰이는 부위나 고민(건조·트러블·미백·진정 등)을 알려주세요."
            )
        if key == "fresh_food":
            return (
                "맛있게 골라 드리려면 조금만 여쭤볼게요.\n"
                "1) 선물용인가요, 바로 드실 건가요?\n"
                "2) 선호하시는 맛(당도/산미)이나 인원을 알려주세요."
            )
        if key == "fashion":
            return (
                "핏에 맞는 추천을 위해 확인할게요.\n"
                "1) 대략 사이즈(또는 키·몸무게 감안 여부)는 어떠신가요?\n"
                "2) 선호 핏(슬림/오버)과 착용 상황을 알려주세요."
            )
        return (
            "맞춤 안내를 위해 먼저 여쭤볼게요.\n"
            "1) 사용 목적이나 상황을 알려주세요.\n"
            "2) 예산·선호 조건이 있으면 함께 말씀해 주세요."
        )

    @staticmethod
    def _industry_persona_lines(
        industry_key: str, bot_display_name: str, industry_kr: str
    ) -> List[str]:
        """Industry-matched counselor persona lines for the system prompt."""
        key = normalize_industry_key(industry_key)
        lines: List[str] = []
        if key == "beauty":
            lines += [
                "",
                "## 뷰티 전문 상담사 페르소나",
                (
                    f"당신은 {bot_display_name}. 뷰티&코스메틱 전문 상담사로서 "
                    "피부 고민에 공감하며 근거 있는 추천을 합니다. 부드러운 존댓말을 씁니다."
                ),
                "",
                "### 추천 요청 시",
                "- '추천해줘'에도 학습된 상품으로 전문가 상담·추천 이유·사용 팁을 답하세요(카드는 시스템이 표시).",
                "- 피부타입·고민이 없으면 답변 끝에 1~2개만 짧게 물어 다음 추천을 정교화하세요.",
                "",
                "### 추천 시 답변 구조",
                "1) 고객 상황 한 줄 요약 2) 상품 1~3개(이유·핵심 성분·사용법·가격) "
                "3) 아침/저녁 루틴(가능 시) 4) 추가 질문 유도",
                "- 학습 지식에 없는 성분·효능은 지어내지 마세요. 피부 무관 상품은 추천 금지.",
            ]
        elif key == "fresh_food":
            lines += [
                "",
                "## 신선식품 전문 상담사 페르소나",
                (
                    f"당신은 {bot_display_name}. 신선식품·농수산물 전문가로서 "
                    "보관·후숙·섭취·제철 추천과 품질 클레임 안내를 정확히 합니다."
                ),
                "",
                "### 추천 요청 시",
                "- 추천 요청에는 학습된 상품으로 이유와 함께 안내하세요(카드는 시스템이 표시).",
                "- 용도·인원이 불명확하면 답변 끝에만 짧게 확인하세요.",
                "",
                "### 추천·안내 답변 구조",
                "1) 상황 요약 2) 상품 1~3개(이유) 3) 보관·후숙·손질 4) 섭취 기한 "
                "5) 파손·변질 시 사진 접수 안내(고객이 문제를 말한 뒤에만)",
                "",
                "### 안전·금지",
                "- 없는 원산지·당도·유통기한을 추측하지 마세요.",
                "- 알레르기·임산부·유아식은 단정하지 말고, 표시 성분은 지식에 있을 때만 안내하세요.",
                "- 배송 지연으로 상온 방치·변질이 의심되면 사진 접수와 고객센터 확인을 안내하세요.",
            ]
        elif key == "fashion":
            lines += [
                "",
                "## 패션 전문 상담사 페르소나",
                (
                    f"당신은 {bot_display_name}. 패션/의류 전문 상담사로서 "
                    "사이즈·핏·코디·소재를 근거 있게 안내합니다."
                ),
                "",
                "### 추천 요청 시",
                "- 추천 요청에는 학습된 상품으로 이유와 함께 안내하세요(카드는 시스템이 표시).",
                "- 사이즈·핏이 없으면 답변 끝에만 짧게 확인하세요.",
                "",
                "### 답변 구조",
                "1) 요구 요약 2) 상품 1~3개(핏·소재·상황 적합성) 3) 사이즈/세탁 팁 4) 교환은 스토어 정책만 인용",
                "- 임의로 무료교환·재고를 약속하지 마세요.",
            ]
        elif key == "electronics":
            lines += [
                "",
                "## 전자/가전 전문 상담사 페르소나",
                f"당신은 {bot_display_name}. 전자·가전 상담사로서 스펙·호환·자가진단·AS를 정확히 안내합니다.",
                "",
                "### 인테이크",
                "- 추천 전 사용 목적·호환 기기·예산을 확인하세요.",
                "",
                "### 답변 구조",
                "1) 요구 요약 2) 적합 상품/스펙 근거 3) 설정·사용 팁 4) 고장 시 자가진단 후 사진 AS 안내",
                "- 보증·스펙은 학습 지식만 인용하세요.",
            ]
        elif key == "pet_supplies":
            lines += [
                "",
                "## 반려동물 용품 상담사 페르소나",
                f"당신은 {bot_display_name}. 반려동물 용품 상담사로서 급여·연령 적합성을 신중히 안내합니다.",
                "",
                "### 인테이크",
                "- 추천 전 종(강아지/고양이)·나이·체중·알러지 여부를 확인하세요.",
                "",
                "### 답변 구조",
                "1) 반려동물 정보 요약 2) 적합 상품·급여 포인트 3) 주의사항",
                "- 의료 진단처럼 단정하지 말고, 이상 증상은 수의사 상담을 권하세요.",
            ]
        elif key == "raw_materials":
            lines += [
                "",
                "## 원료/B2B 전문 상담사 페르소나",
                f"당신은 {bot_display_name}. 화장품·식품 원료 B2B 상담사로서 규격·공급·서류를 정확히 안내합니다.",
                "",
                "### 인테이크",
                "- 용도(화장품/식품 등), 필요 규격, 예상 수량(MOQ)을 먼저 확인하세요.",
                "",
                "### 답변 구조",
                "1) 요구 요약 2) 적합 원료/규격 3) COA·MSDS·샘플·납기(지식에 있을 때만) 4) 다음 단계(견적/등록)",
                "- 없는 성적서·함량을 지어내지 마세요.",
            ]
        elif key == "baby_kids":
            lines += [
                "",
                "## 유아동 전문 상담사 페르소나",
                f"당신은 {bot_display_name}. 유아동 용품 상담사로서 월령·안전 기준으로 신중히 안내합니다.",
                "",
                "### 인테이크",
                "- 추천 전 아이 개월수/체중·사용 목적(수유/외출/수면 등)을 확인하세요.",
                "- 정보 부족 시 카드·단정 추천을 하지 마세요.",
                "",
                "### 답변 구조",
                "1) 월령·목적 요약 2) 적합 상품 1~3개(이유·안전 포인트) 3) 사용/교환 안내",
                "- KC·안전 인증은 학습 지식에 있을 때만 언급하세요. 의료 조언은 하지 마세요.",
            ]
        elif key == "sports_leisure":
            lines += [
                "",
                "## 스포츠/레저 전문 상담사 페르소나",
                f"당신은 {bot_display_name}. 스포츠·캠핑 장비 상담사로서 스펙·호환·AS를 정확히 안내합니다.",
                "",
                "### 인테이크",
                "- 사용 환경(캠핑/등산 등), 인원, 예산, 호환이 필요한 기존 장비를 확인하세요.",
                "",
                "### 답변 구조",
                "1) 용도 요약 2) 장비 추천/스펙 근거 3) 사용·관리 팁 4) 파손 시 사진 AS 안내",
            ]
        elif key == "medical_clinic":
            lines += [
                "",
                "## 병원/클리닉 상담사 페르소나",
                f"당신은 {bot_display_name}. 병원·클리닉 안내 상담사로서 예약·진료과·운영 안내를 돕습니다.",
                "",
                "### 인테이크",
                "- 희망 과목/시술, 초진·재진, 희망 일시를 확인하세요.",
                "",
                "### 답변 구조",
                "1) 문의 요약 2) 예약·시간·주차·비용(지식/정책에 있는 범위) 3) 원무과 연결 안내",
                "- 진단·처방·치료 효과를 단정하지 마세요. 응급은 즉시 병원/응급실을 안내하세요.",
            ]
        elif key == "education_academy":
            lines += [
                "",
                "## 교육/학원 상담사 페르소나",
                f"당신은 {bot_display_name}. 학원·교육 상담사로서 과정·레벨·수강 안내를 합니다.",
                "",
                "### 인테이크",
                "- 관심 과목, 현재 수준, 희망 일정·목표를 확인하세요.",
                "",
                "### 답변 구조",
                "1) 목표 요약 2) 적합 반/커리큘럼 3) 수강료·환불·체험(정책/지식 범위) 4) 상담 신청 안내",
                "- 합격·성적 보장을 약속하지 마세요.",
            ]
        elif key == "professional_legal":
            lines += [
                "",
                "## 전문직(법률/세무/노무) 상담사 페르소나",
                f"당신은 {bot_display_name}. 전문 상담 예약·서류·절차 안내를 담당합니다.",
                "",
                "### 인테이크",
                "- 상담 분야, 긴급도, 보유 서류를 확인하세요.",
                "",
                "### 답변 구조",
                "1) 문의 요약 2) 예약/절차/필요 서류 3) 수임·자문 안내는 공개된 기준만",
                "- 개별 사건 법률 결론을 단정하지 말고, 전문가 상담으로 연결하세요.",
            ]
        elif key == "interior_realestate":
            lines += [
                "",
                "## 인테리어/건축 상담사 페르소나",
                f"당신은 {bot_display_name}. 견적·실측·시공 안내 상담사입니다.",
                "",
                "### 인테이크",
                "- 평수/공간, 예산, 희망 일정, 신규·리모델링 여부를 확인하세요.",
                "",
                "### 답변 구조",
                "1) 요구 요약 2) 견적·포트폴리오·실측 예약 안내 3) 하자/AS는 사진 접수 가능",
                "- 확정 견적을 임의로 약속하지 마세요.",
            ]
        elif key == "hotel_travel":
            lines += [
                "",
                "## 호텔/숙박 컨시어지 페르소나",
                f"당신은 {bot_display_name}. 예약·요금·시설 안내 컨시어지입니다.",
                "",
                "### 인테이크",
                "- 날짜, 인원, 객실 타입, 특별 요청을 확인하세요.",
                "",
                "### 답변 구조",
                "1) 요청 요약 2) 예약/요금/체크인 규정 3) 부대시설·취소 규정(지식 범위)",
                "- 잔여 객실을 추측해 확정하지 마세요.",
            ]
        elif key == "it_corporate":
            lines += [
                "",
                "## IT/SaaS 도입 상담사 페르소나",
                f"당신은 {bot_display_name}. 도입·요금·기술지원 상담사입니다.",
                "",
                "### 인테이크",
                "- 회사 규모, 필요 기능, 도입 시기, 기존 툴을 확인하세요.",
                "",
                "### 답변 구조",
                "1) 요구 요약 2) 요금제/데모/지원 범위 3) 장애는 증상 확인 후 지원 안내",
                "- 없는 SLA·기능을 약속하지 마세요.",
            ]
        elif key == "restaurant_cafe":
            lines += [
                "",
                "## 레스토랑/카페 상담사 페르소나",
                f"당신은 {bot_display_name}. 예약·메뉴·운영 안내 상담사입니다.",
                "",
                "### 인테이크",
                "- 날짜·인원·좌석(룸/단체), 알레르기 여부를 확인하세요.",
                "",
                "### 답변 구조",
                "1) 요청 요약 2) 예약/메뉴/영업시간 안내 3) 가맹 문의는 별도 절차 안내",
                "- 알레르기·원재료는 지식에 있을 때만 안내하고 단정하지 마세요.",
            ]
        else:
            lines += [
                "",
                "## 전문 상담 페르소나",
                (
                    f"당신은 {bot_display_name}. '{industry_kr}' 분야 전문 상담사로서 "
                    "고객에게 정확하고 친절한 상담을 제공합니다."
                ),
                "",
                "### 핵심 상담 원칙",
                "- 요구사항·예산·사용 목적을 먼저 파악하세요.",
                "- 정보가 부족하면 추천 전 1~2개 질문으로 보완하세요.",
                "- 상품 추천 시 적합성 근거를 설명하세요.",
                "- 학습 지식에 없는 사실은 지어내지 마세요.",
                "- 부드러운 존댓말을 사용하세요.",
            ]
        return lines

    @staticmethod
    def _build_store_system_prompt(
        store_obj: Optional[StoreModel],
        rag_context: Optional[str] = None,
    ) -> str:
        """Build a store-grounded system prompt for general-CS answers.

        This is the anti-hallucination core: instead of a bare LLM call, the bot
        now knows WHO it represents (store name/industry), WHEN staff are online,
        HOW customers can reach a human, and WHAT the actual refund/claim policy
        says. When RAG hits, the learned knowledge is appended so product facts
        stay authoritative.
        """
        if store_obj is None:
            lines = [
                "당신은 쇼핑몰 고객센터 AI 상담원입니다.",
                "친절하고 정확하게 한국어로 답변하세요.",
            ]
            if rag_context:
                lines.append(
                    "아래는 학습된 스토어 공식 지식입니다. 이 내용에 근거해 답변하고, "
                    "지식에 없는 내용은 추측하지 말고 고객센터 확인을 안내하세요."
                )
                lines.append(rag_context)
            return "\n".join(lines)

        industry_key = normalize_industry_key(store_obj.industry)
        industry_kr = _INDUSTRY_KR.get(industry_key, store_obj.industry or "쇼핑몰")
        bot_display_name = (store_obj.bot_name or "").strip() or f"{store_obj.store_name}봇"
        lines = [
            f"당신은 '{store_obj.store_name}'({industry_kr}) 고객센터 AI 상담원 '{bot_display_name}'입니다.",
            "원칙: 학습된 지식과 스토어 정책에만 근거해 답변합니다. 없는 정보는 지어내지 않고 "
            "'고객센터로 확인 후 안내드리겠습니다'라고 솔직히 답합니다.",
            "",
            "## 스토어 정보",
            f"- 스토어명: {store_obj.store_name}",
            f"- 업종: {industry_kr}",
            f"- 상담사 이름: {bot_display_name} (대화에서 자연스럽게 '저는 {bot_display_name}예요'처럼 소개 가능)",
        ]
        if store_obj.business_hours:
            lines.append(f"- 운영시간: {store_obj.business_hours}")
        if store_obj.contact_email:
            lines.append(f"- 고객문의: {store_obj.contact_email}")
        # Do NOT inject full welcome_message — models then paste it on every turn.

        # Per-mall claim policy. The showroom writes the owner's overrides under
        # policy_config.claim_policy; the top level holds industry defaults. The
        # owner's explicit setting must win, else we'd quote a stale default.
        try:
            policy = json.loads(store_obj.policy_config_json or "{}")
        except Exception:
            policy = {}
        if not isinstance(policy, dict):
            policy = {}
        claim = policy.get("claim_policy")
        claim = claim if isinstance(claim, dict) else {}
        max_days = claim.get("max_claim_days", policy.get("max_claim_days"))
        full_ratio = claim.get("full_refund_damage_ratio", policy.get("full_refund_damage_ratio"))
        partial_ratio = claim.get(
            "partial_refund_damage_ratio", policy.get("partial_refund_damage_ratio")
        )
        if any(isinstance(v, (int, float)) for v in (max_days, full_ratio, partial_ratio)):
            lines.append("")
            lines.append("## 반품/교환 정책 (고객 질문 시 그대로 안내)")
            if isinstance(max_days, (int, float)):
                lines.append(
                    f"- 접수 기한: 수령 후 {int(max_days)}일 이내 (기한 경과 시 접수 불가)"
                )
            if isinstance(full_ratio, (int, float)):
                lines.append(f"- 파손 {int(full_ratio)}% 이상 → 전액 환불")
            if isinstance(partial_ratio, (int, float)):
                bound = f"{int(partial_ratio)}% 이상"
                if isinstance(full_ratio, (int, float)):
                    bound += f" {int(full_ratio)}% 미만"
                lines.append(f"- 파손 {bound} → 부분 환불 (손상 비율에 비례)")

        # Shipping policy (entered by the owner; injected verbatim so the bot
        # quotes real delivery terms instead of guessing).
        ship = policy.get("shipping_policy")
        ship = ship if isinstance(ship, dict) else {}
        if ship:
            lines.append("")
            lines.append("## 배송 정책 (배송비/소요일 질문 시 그대로 안내)")
            fee = ship.get("delivery_fee")
            if isinstance(fee, (int, float)):
                lines.append(f"- 기본 배송비: {int(fee):,}원")
            free_over = ship.get("free_over_amount")
            if isinstance(free_over, (int, float)):
                lines.append(f"- 무료배송: {int(free_over):,}원 이상 구매 시")
            days_txt = (ship.get("delivery_days") or "").strip()
            if days_txt:
                lines.append(f"- 배송 소요일: {days_txt}")
            note_txt = (ship.get("note") or "").strip()
            if note_txt:
                lines.append(f"- 배송 유의사항: {note_txt}")

        if rag_context:
            lines.append("")
            lines.append(
                "## 학습된 상품/스토어 지식 (상품 질문 시 근거로 사용, 지식에 없는 내용은 지어내지 말 것)"
            )
            lines.append(rag_context)

        # Industry-specific consultation guide — persona must match 업종.
        lines.extend(
            ChatService._industry_persona_lines(industry_key, bot_display_name, industry_kr)
        )

        lines.append("")
        lines.append("## 답변 규칙 (필수)")
        lines.append(
            "1. 위 '정책'과 '학습된 지식'에 적힌 숫자·금액·기간만 그대로 인용합니다. "
            "절대로 임의로 배송비·기간·환불 비율을 만들거나 바꾸지 않습니다."
        )
        lines.append(
            "2. 정책/지식에 없는 내용은 '잠시만요, 정확한 내용으로 확인 후 안내드리겠습니다'라고 "
            "인정하고 고객센터 연결을 안내합니다. 아는 척하지 않습니다."
        )
        lines.append(
            "3. 고객이 '반품', '교환', '파손', '불량', '환불' 등을 언급하면 사진 접수를 안내합니다: "
            "'사진을 올려주시면 AI가 손상 상태를 판독해 빠르게 처리해 드립니다. "
            "채팅창의 [📸 사진으로 반품 접수] 버튼을 눌러 사진을 올려주세요.' 라고 안내합니다. "
            "고객이 반품 의사를 밝히지 않았는데 사진 업로드를 먼저 권하지 마세요."
        )
        lines.append(
            "4. 고객이 사용한 언어(일본어·영어·중국어 등)로 자연스럽게 답변합니다. "
            "한국어로만 고정하지 않습니다."
        )
        lines.append(
            "5. 답변은 두세 문장 이내의 간결한 존댓말로 하고, 필요 시 다음 단계"
            "(주문번호 안내 등)를 제시합니다."
        )
        lines.append(
            f"6. 매 답변 앞에 '안녕하세요, 상담사 {bot_display_name}입니다' 또는 "
            "긴 환영/소개 멘트를 반복하지 마세요. 이름은 필요할 때만 한 번 짧게 언급합니다."
        )
        lines.append(
            "7. 고객이 상품을 찾거나 추천을 요청하면, 학습된 상품을 근거로 추천 이유를 "
            "말하고(카드는 시스템이 별도 표시), 없는 가격·스펙은 지어내지 마세요."
        )
        lines.append(
            "8. 지식에 '할인 중'·정상가·판매가가 있으면 구분해 안내하세요. "
            "배송비·무료배송 기준 금액을 상품 판매가처럼 말하지 마세요. "
            "지식에 판매가가 없거나 불확실하면 가격을 숫자로 단정하지 말고 "
            "'상품 카드/상세 페이지에서 확인해 주세요'라고 안내하세요."
        )
        return "\n".join(lines)

    @classmethod
    def _guardrail_shipping_not_product_price(
        cls, reply: str, store_obj: Optional[StoreModel]
    ) -> str:
        """Stop the model from quoting delivery_fee as if it were the product price."""
        if not reply or store_obj is None:
            return reply
        reject = cls._shipping_reject_prices(store_obj)
        if not reject:
            return reply
        out = reply
        for fee in sorted(reject):
            for amount in {f"{fee:,}", str(fee)}:
                pat = re.compile(
                    rf"([^\n。\.!]{{0,40}}?){re.escape(amount)}원"
                    rf"(?:\s*에\s*판매|\s*에\s*팔|\s*판매\s*중|"
                    rf"\s*(?:에|으로)\s*(?:구매|구입)|"
                    rf"(?=\s*(?:입니다|이에요|예요|입니다\.)))"
                )

                def _sub(m: re.Match, _fee: int = fee) -> str:
                    head = m.group(1) or ""
                    if any(k in head for k in ("배송", "택배", "무료배송", "이상")):
                        return m.group(0)
                    return (
                        f"{head}판매가는 상품 카드·상세 페이지에서 확인해 주세요"
                    )

                out = pat.sub(_sub, out)
        return out

    @staticmethod
    def _guardrail_fix_claim_window(reply: str, store_obj: Optional[StoreModel]) -> str:
        """Post-hoc hallucination guard for the claim/refund window.

        The prompt instructs the model to quote the policy verbatim, but an LLM
        can still invent a plausible number. If the reply states a claim window
        that contradicts the store's own policy, we re-anchor the whole sentence
        to the authoritative window so the bot never misstates a refund deadline
        (the single most dispute-prone fact in CS).
        """
        if store_obj is None or not reply:
            return reply
        try:
            policy = json.loads(store_obj.policy_config_json or "{}")
        except Exception:
            return reply
        if not isinstance(policy, dict):
            return reply
        claim = policy.get("claim_policy")
        claim = claim if isinstance(claim, dict) else {}
        max_days = claim.get("max_claim_days", policy.get("max_claim_days"))
        if not isinstance(max_days, (int, float)):
            return reply
        correct = int(max_days)

        m = _CLAIM_DAY_RE.search(reply)
        if not m:
            return reply
        stated = int(m.group(1))
        if stated == correct:
            return reply  # already correct — leave the reply untouched

        logger.warning(
            f"[Chat][Guardrail] Claim-window mismatch for mall={store_obj.mall_id}: "
            f"reply said {stated}d, policy says {correct}d. Re-anchoring."
        )
        # Replace every mismatched "N일 이내/이하" with the true policy window.
        def _repl(mm: re.Match) -> str:
            return f"{correct}일 {mm.group(2)}" if int(mm.group(1)) != correct else mm.group(0)

        fixed = _CLAIM_DAY_RE.sub(_repl, reply)
        return (
            f"{fixed}\n"
            f"※ 정확한 기준은 수령 후 {correct}일 이내 접수입니다. (스토어 정책 기준)"
        )

    async def _load_history(
        self, session_db: AsyncSession, session_id: str, exclude_id: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Load recent conversation turns for multi-turn memory.

        Returns oldest->newest [{"role": "user"|"assistant", "content": str}, ...].
        `exclude_id` drops the current user message row (its text is the live prompt).
        """
        try:
            res = await session_db.execute(
                select(MessageModel)
                .where(MessageModel.session_id == session_id)
                .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
                .limit(_HISTORY_LIMIT)
            )
            rows = list(res.scalars().all())
        except Exception as e:
            logger.warning(f"[Chat] Failed to load history for session {session_id}: {e}")
            return []

        history: List[Dict[str, str]] = []
        for row in reversed(rows):  # oldest first
            if exclude_id is not None and row.id == exclude_id:
                continue
            if row.role not in ("user", "assistant") or not (row.content or "").strip():
                continue
            history.append({"role": row.role, "content": row.content})
        return history

    async def handle_message(
        self,
        session_db: AsyncSession,
        session_id: Optional[str],
        customer_id: str,
        message_text: str,
        mall_id: str = "demo_mall",
    ) -> Tuple[str, str, str, List[ProductRecommendationCard]]:
        """Handle synchronous chat message with Quota Gate -> FAQ -> Store RAG Counselor -> LLM routing.
        
        Returns (session_id, response_text, intent, recommended_products).
        """
        chat_session = await self.get_or_create_session(
            session_db, session_id, customer_id, mall_id=mall_id
        )
        start_time = time.time()
        recommended_products: List[ProductRecommendationCard] = []

        # 1. Record User Message (with language detection for owner-side translation)
        detected_lang = detect_language(message_text)
        user_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="user",
            content=message_text,
            detected_language=detected_lang,
        )
        session_db.add(user_msg)
        await session_db.flush()

        # Translate foreign customer messages to Korean for the owner dashboard
        if detected_lang != "ko":
            try:
                ko_translation = await self.ai_router.translate_text(message_text, "ko", detected_lang)
                user_msg.translation_ko = ko_translation
                await session_db.flush()
            except Exception as e:
                logger.warning(f"[Chat] Translation to Korean failed: {e}")

        # 1.2 Load recent conversation turns for multi-turn memory (current msg excluded)
        history = await self._load_history(
            session_db, chat_session.id, exclude_id=user_msg.id
        )

        # 1.5 Check if store subscription is expired
        store_obj = await store_service.get_store_by_mall_id(session_db, mall_id)
        if store_obj:
            _, is_exp, _, exp_msg = store_service.evaluate_subscription_status(store_obj)
            if is_exp:
                return chat_session.id, f"⛔ {exp_msg}", "subscription_expired", []

        # 2. Zero-token path: store policy → order tracking → global FAQ fallback
        zero = await self._resolve_zero_token_reply(
            session_db, mall_id, chat_session.id, message_text, store_obj
        )
        if zero:
            intent, response_text = zero
        else:
            # 3. Check store daily AI quota before invoking RAG/LLM
            allowed, used, limit = await store_service.check_and_consume_daily_quota(
                session_db, mall_id
            )
            if not allowed:
                intent = "quota_exceeded"
                response_text = (
                    f"⚠️ 금일 스토어 AI 상담 제공 한도({limit}건)가 모두 소진되었습니다. "
                    "급하신 문의는 고객센터 게시판을 이용해 주시거나 내일 다시 이용해 주세요."
                )
            else:
                # 4. Build a combined view of the conversation: the current message
                # plus recent user turns. Customers often answer the bot's intake
                # question ("지성 피부예요, 트러블 고민이에요") in separate turns, so
                # keyword detection must look at the whole dialogue, not just the
                # latest message.
                convo_text = message_text + " " + " ".join(
                    h.get("content", "") for h in history if h.get("role") == "user"
                )
                industry = (store_obj.industry if store_obj else None)
                rec_kw, _detail_kw = _counsel_keywords(industry)

                # 4b. ALWAYS search store knowledge — advice/usage questions must
                # be answered with real product data.
                results = await self.rag.search_with_store_knowledge(
                    session_db,
                    mall_id,
                    message_text,
                    top_k=5,
                    industry=industry,
                )
                attach_cards = should_attach_product_cards(
                    message_text, convo_text, industry, results
                )
                is_counselor_query = any(k in message_text for k in rec_kw) or attach_cards

                if results:
                    intent = "ai_counselor_recommendation" if is_counselor_query else "rag_product_inquiry"
                    reject_prices = self._shipping_reject_prices(store_obj)
                    if attach_cards:
                        card_hits = filter_results_for_cards(
                            message_text, results, max_cards=5
                        )
                        recommended_products = self._build_product_cards(
                            card_hits,
                            reject_prices=reject_prices,
                        )
                    context = self.rag.assemble_context(
                        results,
                        reject_prices=reject_prices,
                    )
                    system_prompt = self._build_store_system_prompt(store_obj, rag_context=context)
                    response_text = await self.ai_router.generate_text(
                        message_text, system_prompt=system_prompt, history=history
                    )
                else:
                    # Nothing learned matches: plain conversational CS (no cards).
                    intent = "general_cs"
                    system_prompt = self._build_store_system_prompt(store_obj)
                    response_text = await self.ai_router.generate_text(
                        message_text, system_prompt=system_prompt, history=history
                    )

        # 4.5 Hallucination guardrail: re-anchor any AI-stated claim window that
        # contradicts the store's own refund policy (AI branches only).
        if intent in (
            "general_cs",
            "rag_product_inquiry",
            "ai_counselor_recommendation",
            "stream_response",
        ):
            response_text = self._guardrail_fix_claim_window(response_text, store_obj)
            response_text = self._guardrail_shipping_not_product_price(
                response_text, store_obj
            )

        latency_ms = int((time.time() - start_time) * 1000)

        # 5. Record Assistant Message
        assistant_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="assistant",
            content=response_text,
            intent=intent,
            latency_ms=latency_ms,
            detected_language=detected_lang,
        )
        session_db.add(assistant_msg)
        await session_db.commit()

        return chat_session.id, response_text, intent, recommended_products

    async def stream_chat_response(
        self,
        session_db: AsyncSession,
        session_id: Optional[str],
        customer_id: str,
        message_text: str,
        mall_id: str = "demo_mall",
        cards_out: Optional[List[ProductRecommendationCard]] = None,
    ) -> AsyncIterator[str]:
        """Stream SSE tokens while saving messages and enforcing store daily quota.

        `cards_out` (optional) receives the product recommendation cards that
        the SAME intake-gating logic as handle_message decided to attach. The
        caller must NOT run its own RAG search for cards — that would bypass
        the "collect info before recommending" rule.
        """
        chat_session = await self.get_or_create_session(
            session_db, session_id, customer_id, mall_id=mall_id
        )

        detected_lang = detect_language(message_text)
        user_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="user",
            content=message_text,
            detected_language=detected_lang,
        )
        session_db.add(user_msg)
        await session_db.commit()

        # Translate foreign customer messages to Korean for the owner dashboard
        if detected_lang != "ko":
            try:
                ko_translation = await self.ai_router.translate_text(message_text, "ko", detected_lang)
                user_msg.translation_ko = ko_translation
                await session_db.commit()
            except Exception as e:
                logger.warning(f"[Chat] Translation to Korean failed: {e}")

        # Load recent turns for multi-turn memory (current msg excluded)
        history = await self._load_history(
            session_db, chat_session.id, exclude_id=user_msg.id
        )

        # 0. Check if store subscription is expired
        store_obj = await store_service.get_store_by_mall_id(session_db, mall_id)
        if store_obj:
            _, is_exp, _, exp_msg = store_service.evaluate_subscription_status(store_obj)
            if is_exp:
                yield f"⛔ {exp_msg}"
                return

        # Zero-token path (same order as handle_message)
        zero = await self._resolve_zero_token_reply(
            session_db, mall_id, chat_session.id, message_text, store_obj
        )
        if zero:
            intent, reply = zero
            if intent in ("store_policy_faq", "faq_deterministic"):
                words = reply.split(" ")
                for i, w in enumerate(words):
                    yield w + (" " if i < len(words) - 1 else "")
            else:
                yield reply
            assistant_msg = MessageModel(
                id=str(uuid.uuid4()),
                session_id=chat_session.id,
                role="assistant",
                content=reply,
                intent=intent,
            )
            session_db.add(assistant_msg)
            await session_db.commit()
            return

        # Check daily quota
        allowed, used, limit = await store_service.check_and_consume_daily_quota(
            session_db, mall_id
        )
        if not allowed:
            quota_msg = f"⚠️ 금일 스토어 AI 상담 한도({limit}건)가 초과되었습니다."
            yield quota_msg
            return

        convo_text = message_text + " " + " ".join(
            h.get("content", "") for h in history if h.get("role") == "user"
        )
        industry = (store_obj.industry if store_obj else None)
        rec_kw, _detail_kw = _counsel_keywords(industry)
        reject_prices = self._shipping_reject_prices(store_obj)

        # Always search RAG so expert answers are grounded in real product data.
        results = await self.rag.search_with_store_knowledge(
            session_db,
            mall_id,
            message_text,
            top_k=5,
            industry=industry,
        )
        attach_cards = should_attach_product_cards(
            message_text, convo_text, industry, results
        )
        is_counselor_query = any(k in message_text for k in rec_kw) or attach_cards

        # 상품명/유니폼·찾아·추천 매칭 시 카드 최대 5장 (링크·이미지·가격)
        if results and cards_out is not None and attach_cards:
            card_hits = filter_results_for_cards(message_text, results, max_cards=5)
            cards_out.extend(
                self._build_product_cards(card_hits, reject_prices=reject_prices)
            )

        context = (
            self.rag.assemble_context(results, reject_prices=reject_prices)
            if results
            else None
        )
        system_prompt = self._build_store_system_prompt(store_obj, rag_context=context)

        collected = []
        async for token in self.ai_router.stream_text(
            message_text, system_prompt=system_prompt, history=history
        ):
            collected.append(token)
            yield token

        raw_content = "".join(collected).strip()
        if not raw_content:
            raw_content = (
                "죄송합니다. 잠시 답변이 지연되고 있어요. "
                "원하시는 상담 내용을 한 줄로 다시 말씀해 주시겠어요?"
            )
            yield raw_content
        intent = "stream_response"
        if results:
            intent = "ai_counselor_recommendation" if is_counselor_query else "rag_product_inquiry"
        full_content = self._guardrail_fix_claim_window(raw_content, store_obj)
        full_content = self._guardrail_shipping_not_product_price(full_content, store_obj)
        # Live correction for the widget: replace on-screen text if policy was re-anchored.
        if full_content != raw_content:
            yield {"__stream_replace__": full_content}
        assistant_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="assistant",
            content=full_content,
            intent=intent,
            detected_language=detected_lang,
        )
        session_db.add(assistant_msg)
        await session_db.commit()
