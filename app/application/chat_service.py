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

_STATUS_KOR = {
    OrderStatus.PAID: "결제 완료",
    OrderStatus.PREPARING: "상품 준비 중",
    OrderStatus.SHIPPING: "배송 중",
    OrderStatus.DELIVERED: "배송 완료",
    OrderStatus.CANCELLED: "주문 취소",
    OrderStatus.REFUNDED: "반품/환불",
}


RECOMMENDATION_KEYWORDS = [
    "추천",
    "건조",
    "건성",
    "민감",
    "진정",
    "트러블",
    "홍조",
    "임산부",
    "보습",
    "수분",
    "시카",
    "앰플",
    "크림",
    "토너",
    "선물",
    "성분",
    "전성분",
    "나이아신",
    "바르면",
    "뭐가",
]


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
        self, session_db: AsyncSession, session_id: Optional[str], customer_id: str = "guest"
    ) -> SessionModel:
        if session_id:
            res = await session_db.execute(select(SessionModel).where(SessionModel.id == session_id))
            chat_session = res.scalar_one_or_none()
            if chat_session:
                return chat_session

        new_id = session_id or str(uuid.uuid4())
        chat_session = SessionModel(
            id=new_id,
            customer_id=customer_id,
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
        lines = [
            f"당신은 '{store_obj.store_name}'({industry_kr}) 고객센터 AI 상담원 '{store_obj.store_name}봇'입니다.",
            "원칙: 학습된 지식과 스토어 정책에만 근거해 답변합니다. 없는 정보는 지어내지 않고 "
            "'고객센터로 확인 후 안내드리겠습니다'라고 솔직히 답합니다.",
            "",
            "## 스토어 정보",
            f"- 스토어명: {store_obj.store_name}",
            f"- 업종: {industry_kr}",
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
            "3. 고객이 사용한 언어(일본어·영어·중국어 등)로 자연스럽게 답변합니다. "
            "한국어로만 고정하지 않습니다."
        )
        lines.append(
            "4. 답변은 두세 문장 이내의 간결한 존댓말로 하고, 필요 시 다음 단계"
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
        chat_session = await self.get_or_create_session(session_db, session_id, customer_id)
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

        # 2. Check 0-token Deterministic FAQ first (Does not consume AI quota)
        faq_answer = self.rag.lookup_deterministic_faq(message_text)
        if faq_answer:
            intent = "faq_deterministic"
            response_text = faq_answer
        elif "주문" in message_text or "배송" in message_text or _ORDER_ID_RE.search(message_text):
            intent = "shipping_inquiry"
            response_text = await self._lookup_order_reply(
                session_db, mall_id, chat_session.id, message_text
            )
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
                # 4. Search store-specific & default RAG knowledge
                results = await self.rag.search_with_store_knowledge(
                    session_db, mall_id, message_text, top_k=2
                )
                is_counselor_query = any(k in message_text for k in RECOMMENDATION_KEYWORDS)

                if results:
                    intent = "ai_counselor_recommendation" if is_counselor_query else "rag_product_inquiry"
                    recommended_products = self._build_product_cards(results)
                    context = self.rag.assemble_context(results)
                    top_doc = results[0].document
                    system_prompt = self._build_store_system_prompt(store_obj, rag_context=context)
                    llm_reply = await self.ai_router.generate_text(
                        message_text, system_prompt=system_prompt, history=history
                    )
                    # Ensure deterministic fact inclusion even when MockAIProvider is active
                    if top_doc.title not in llm_reply:
                        price_txt = f" ({top_doc.metadata.get('price'):,}원)" if top_doc.metadata.get("price") else ""
                        response_text = (
                            f"✨ **[{top_doc.title}{price_txt}]** 안내드립니다.\n"
                            f"{top_doc.content}\n\n{llm_reply}"
                        )
                    else:
                        response_text = llm_reply
                else:
                    intent = "general_cs"
                    system_prompt = self._build_store_system_prompt(store_obj)
                    response_text = await self.ai_router.generate_text(
                        message_text, system_prompt=system_prompt, history=history
                    )

        # 4.5 Hallucination guardrail: re-anchor any AI-stated claim window that
        # contradicts the store's own refund policy (AI branches only).
        if intent in ("general_cs", "rag_product_inquiry", "ai_counselor_recommendation"):
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
    ) -> AsyncIterator[str]:
        """Stream SSE tokens while saving messages and enforcing store daily quota."""
        chat_session = await self.get_or_create_session(session_db, session_id, customer_id)

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

        # Check FAQ first (0-token)
        faq_answer = self.rag.lookup_deterministic_faq(message_text)
        if faq_answer:
            words = faq_answer.split(" ")
            for i, w in enumerate(words):
                yield w + (" " if i < len(words) - 1 else "")
            assistant_msg = MessageModel(
                id=str(uuid.uuid4()),
                session_id=chat_session.id,
                role="assistant",
                content=faq_answer,
                intent="faq_deterministic",
            )
            session_db.add(assistant_msg)
            await session_db.commit()
            return

        # Check Order / Shipping inquiry (real Cafe24 order no or ORD-... test id)
        if "주문" in message_text or "배송" in message_text or _ORDER_ID_RE.search(message_text):
            order_reply = await self._lookup_order_reply(
                session_db, mall_id, chat_session.id, message_text
            )
            yield order_reply
            assistant_msg = MessageModel(
                id=str(uuid.uuid4()),
                session_id=chat_session.id,
                role="assistant",
                content=order_reply,
                intent="shipping_inquiry",
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

        # RAG context if applicable
        results = await self.rag.search_with_store_knowledge(
            session_db, mall_id, message_text, top_k=2
        )
        # Store-grounded system prompt; append learned RAG knowledge when we have it
        context = self.rag.assemble_context(results) if results else None
        system_prompt = self._build_store_system_prompt(store_obj, rag_context=context)

        collected = []
        async for token in self.ai_router.stream_text(
            message_text, system_prompt=system_prompt, history=history
        ):
            collected.append(token)
            yield token

        full_content = "".join(collected)
        assistant_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="assistant",
            content=full_content,
            intent="stream_response",
            detected_language=detected_lang,
        )
        session_db.add(assistant_msg)
        await session_db.commit()
