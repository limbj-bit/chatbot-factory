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

_INDUSTRY_KR = {
    "fresh_food": "신선식품/식품",
    "beauty": "뷰티/화장품",
    "fashion": "패션/의류",
    "electronics": "전자/가전",
    "pet": "반려동물용품",
    "general": "종합몰",
}

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
    "맛", "당도", "신선", "고르", "어떤",
]
_FRESH_DETAIL = [
    "보관", "냉장", "냉동", "상온", "후숙", "씻", "섭취", "레시피", "요리",
    "당도", "품종", "산지", "제철", "유통기한", "소비기한", "해동", "손질",
    "가격", "얼마", "kg", "인분", "몇개", "몇 개", "선물",
]
_FASHION_RECOMMEND = [
    "추천", "선물", "뭐가", "사이즈", "코디", "어울", "핏", "스타일", "고르", "어떤",
]
_FASHION_DETAIL = [
    "사이즈", "치수", "가슴", "허리", "기장", "소재", "원단", "세탁", "코디",
    "색상", "컬러", "핏", "오버핏", "슬림", "정장", "캐주얼", "가격", "얼마",
    "교환", "착용", "착용감",
]
_ELECTRONICS_RECOMMEND = [
    "추천", "뭐가", "고르", "어떤", "스펙", "호환", "AS", "고장",
]
_ELECTRONICS_DETAIL = [
    "스펙", "호환", "모델", "배터리", "충전", "보증", "AS", "용량", "인치",
    "와이파이", "블루투스", "가격", "얼마", "사용법", "설정",
]
_PET_RECOMMEND = [
    "추천", "뭐가", "고르", "사료", "간식", "장난감", "선물",
]
_PET_DETAIL = [
    "사료", "간식", "나이", "개월", "견종", "묘종", "알러지", "알레르기",
    "체중", "급여", "가격", "얼마", "성분", "급여량",
]
_GENERAL_RECOMMEND = ["추천", "선물", "뭐가", "고르", "어떤"]
_GENERAL_DETAIL = ["가격", "얼마", "사용법", "어떻게", "스펙", "구성", "옵션"]

_INDUSTRY_COUNSEL: Dict[str, Tuple[List[str], List[str]]] = {
    "beauty": (RECOMMENDATION_KEYWORDS, SKIN_DETAIL_KEYWORDS),
    "fresh_food": (_FRESH_RECOMMEND, _FRESH_DETAIL),
    "fashion": (_FASHION_RECOMMEND, _FASHION_DETAIL),
    "electronics": (_ELECTRONICS_RECOMMEND, _ELECTRONICS_DETAIL),
    "pet": (_PET_RECOMMEND, _PET_DETAIL),
    "general": (_GENERAL_RECOMMEND, _GENERAL_DETAIL),
}


def _counsel_keywords(industry: Optional[str]) -> Tuple[List[str], List[str]]:
    """Return (recommendation_keywords, detail_keywords) for the store industry."""
    key = (industry or "general").strip().lower()
    return _INDUSTRY_COUNSEL.get(key, _INDUSTRY_COUNSEL["general"])



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
    def _build_product_cards(search_results: List[RAGSearchResult]) -> List[ProductRecommendationCard]:
        cards: List[ProductRecommendationCard] = []
        for r in search_results:
            doc = r.document
            if doc.source in ("product", "crawled_url"):
                cards.append(
                    ProductRecommendationCard(
                        product_id=doc.product_id or doc.document_id,
                        title=doc.title,
                        price=doc.metadata.get("price"),
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
        """Store policy → order tracking → global FAQ. Returns (intent, text) or None."""
        store_faq = self._lookup_store_policy_faq(message_text, store_obj)
        if store_faq:
            return "store_policy_faq", store_faq

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
    def _industry_persona_lines(
        industry_key: str, bot_display_name: str, industry_kr: str
    ) -> List[str]:
        """Industry-matched counselor persona lines for the system prompt."""
        lines: List[str] = []
        if industry_key == "beauty":
            lines += [
                "",
                "## 뷰티 전문 상담사 페르소나",
                (
                    f"당신은 {bot_display_name}. 뷰티&코스메틱 전문 상담사이자, "
                    "고객의 피부를 진심으로 걱정해주는 친한 언니/오빠 같은 존재입니다. "
                    "부드러운 존댓말(~요, ~이에요)을 씁니다."
                ),
                "",
                "### 상담 규칙",
                "- 피부타입·고민이 부족하면 추천/카드 전에 1~2개만 질문하세요.",
                "- 추천 시 이유·핵심 성분·사용법·가격을 근거와 함께 설명하세요.",
                "- 피부와 무관한 상품은 추천하지 마세요.",
                "- 학습된 지식에 없는 성분은 지어내지 마세요.",
            ]
        elif industry_key == "fresh_food":
            lines += [
                "",
                "## 신선식품 전문 상담사 페르소나",
                (
                    f"당신은 {bot_display_name}. 신선식품·농수산물 전문 상담사로서 "
                    "보관법·섭취법·제철 추천을 정확하게 안내합니다."
                ),
                "",
                "### 상담 규칙",
                "- 모호한 '추천해줘'에는 용도(선물/바로 섭취), 인원, 선호 맛(당도/산미)을 먼저 물어보세요.",
                "- 보관(냉장/상온/후숙)·섭취 기한·손질법을 학습 지식 기준으로 안내하세요.",
                "- 신선도·파손 문의 시 사진 접수를 안내할 수 있습니다(고객이 문제를 말한 뒤에만).",
                "- 없는 원산지·당도·유통기한은 추측하지 마세요.",
            ]
        elif industry_key == "fashion":
            lines += [
                "",
                "## 패션 전문 상담사 페르소나",
                (
                    f"당신은 {bot_display_name}. 패션/의류 전문 상담사로서 "
                    "사이즈·핏·코디·소재를 친절히 안내합니다."
                ),
                "",
                "### 상담 규칙",
                "- 모호한 추천에는 사이즈/키·몸무게 감안 여부·선호 핏(슬림/오버)·상황을 먼저 확인하세요.",
                "- 사이즈·소재·세탁·코디는 학습된 상품 정보만 인용하세요.",
                "- 사이즈 교환 정책은 스토어 정책을 따르고, 임의로 무료교환을 약속하지 마세요.",
            ]
        elif industry_key == "electronics":
            lines += [
                "",
                "## 전자/가전 전문 상담사 페르소나",
                f"당신은 {bot_display_name}. 전자·가전 상담사로서 스펙·호환·AS를 정확히 안내합니다.",
                "",
                "### 상담 규칙",
                "- 추천 전 사용 목적·호환 기기·예산부터 확인하세요.",
                "- 스펙·보증은 학습 지식만 인용하고, A/S는 사진 접수 안내가 가능합니다.",
            ]
        elif industry_key == "pet":
            lines += [
                "",
                "## 반려동물 용품 상담사 페르소나",
                f"당신은 {bot_display_name}. 반려동물 용품 상담사로서 급여·적합 연령을 신중히 안내합니다.",
                "",
                "### 상담 규칙",
                "- 추천 전 종/나이/체중/알러지 여부를 확인하세요.",
                "- 의료 진단처럼 단정하지 말고, 이상 증상은 수의사 상담을 권하세요.",
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

        industry_kr = _INDUSTRY_KR.get(store_obj.industry, store_obj.industry or "쇼핑몰")
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
        if store_obj.welcome_message:
            lines.append(f"- 인사말: {store_obj.welcome_message}")

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
        industry_key = (store_obj.industry or "").strip().lower()
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
        return "\n".join(lines)

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
                # Cards are gated: attach product cards ONLY when the customer
                # has shared enough detail. Vague "추천해줘" must NOT trigger
                # cards — the counselor first asks for skin type/concern.
                industry = (store_obj.industry if store_obj else None)
                rec_kw, detail_kw = _counsel_keywords(industry)
                is_specific_query = any(k in convo_text for k in detail_kw)
                is_counselor_query = any(k in message_text for k in rec_kw)

                # 4b. ALWAYS search store knowledge — advice/usage questions must
                # be answered with real product data. The gate above only controls
                # whether CARDS are attached.
                results = await self.rag.search_with_store_knowledge(
                    session_db, mall_id, message_text, top_k=3
                )

                if results:
                    intent = "ai_counselor_recommendation" if is_counselor_query else "rag_product_inquiry"
                    if is_specific_query:
                        recommended_products = self._build_product_cards(results)
                    context = self.rag.assemble_context(results)
                    system_prompt = self._build_store_system_prompt(store_obj, rag_context=context)
                    response_text = await self.ai_router.generate_text(
                        message_text, system_prompt=system_prompt, history=history
                    )
                else:
                    # Nothing learned matches: plain conversational CS with the
                    # counselor persona (asks skin type & concern, no cards).
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

        # RAG context only when the dialogue carries enough skin/concern detail.
        # Vague intake-phase messages must not drag in product knowledge.
        # BUT: for expert consultations (skin/ingredient/usage questions), we
        # ALWAYS search RAG so the bot can answer with real product data —
        # we just don't attach product CARDS unless the customer shared enough.
        convo_text = message_text + " " + " ".join(
            h.get("content", "") for h in history if h.get("role") == "user"
        )
        industry = (store_obj.industry if store_obj else None)
        rec_kw, detail_kw = _counsel_keywords(industry)
        is_specific_query = any(k in convo_text for k in detail_kw)
        is_counselor_query = any(k in message_text for k in rec_kw)

        # Always search RAG so expert answers are grounded in real product data.
        results = await self.rag.search_with_store_knowledge(
            session_db, mall_id, message_text, top_k=3
        )

        # Attach product cards ONLY when the customer has shared enough detail.
        if results and cards_out is not None and is_specific_query:
            cards_out.extend(self._build_product_cards(results))

        context = self.rag.assemble_context(results) if results else None
        system_prompt = self._build_store_system_prompt(store_obj, rag_context=context)

        collected = []
        async for token in self.ai_router.stream_text(
            message_text, system_prompt=system_prompt, history=history
        ):
            collected.append(token)
            yield token

        raw_content = "".join(collected)
        intent = "stream_response"
        if results:
            intent = "ai_counselor_recommendation" if is_counselor_query else "rag_product_inquiry"
        full_content = self._guardrail_fix_claim_window(raw_content, store_obj)
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
