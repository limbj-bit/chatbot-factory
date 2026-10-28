import re
import time
import uuid
from typing import AsyncIterator, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.order_service import OrderService
from app.application.store_service import store_service
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.router import AIProviderRouter
from app.infrastructure.database.models import MessageModel, SessionModel
from app.infrastructure.rag.engine import RAGEngine, RAGSearchResult, rag_engine
from app.schemas.chat import ProductRecommendationCard


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

        # 1. Record User Message
        user_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="user",
            content=message_text,
        )
        session_db.add(user_msg)
        await session_db.flush()

        # 2. Check 0-token Deterministic FAQ first (Does not consume AI quota)
        faq_answer = self.rag.lookup_deterministic_faq(message_text)
        if faq_answer:
            intent = "faq_deterministic"
            response_text = faq_answer
        elif "주문" in message_text or "배송" in message_text or "ORD-" in message_text:
            intent = "shipping_inquiry"
            order_match = re.search(r"ORD-[A-Za-z0-9-]+", message_text)
            if order_match:
                order_id = order_match.group(0)
                order = await self.order_service.get_order_details(order_id)
                if order:
                    status_kor = "배송 완료" if order.is_delivered() else "배송 진행 중"
                    response_text = f"주문번호 [{order.order_id}]는 현재 [{status_kor}] 상태입니다. 상품: {order.items[0].product_name}"
                else:
                    response_text = f"주문번호 [{order_id}]를 조회할 수 없습니다. 번호를 다시 확인해 주세요."
            else:
                response_text = "주문 및 배송 조회를 원하시면 'ORD-'로 시작하는 주문번호를 함께 입력해 주세요."
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
                    system_prompt = (
                        "당신은 스토어 전문 AI 카운슬러이자 CS 매니저입니다. "
                        "주어진 공식 지식 베이스의 성분, 가격, 특징을 바탕으로 고객에게 친절하게 설명하고 맞춤 상품을 추천하세요.\n"
                        f"{context}"
                    )
                    llm_reply = await self.ai_router.generate_text(
                        message_text, system_prompt=system_prompt
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
                    response_text = await self.ai_router.generate_text(message_text)

        latency_ms = int((time.time() - start_time) * 1000)

        # 5. Record Assistant Message
        assistant_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="assistant",
            content=response_text,
            intent=intent,
            latency_ms=latency_ms,
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

        user_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="user",
            content=message_text,
        )
        session_db.add(user_msg)
        await session_db.commit()

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
        system_prompt = None
        if results:
            context = self.rag.assemble_context(results)
            system_prompt = f"당신은 스토어 전문 AI 카운슬러입니다. 사실에 기반하여 친절하게 답변하세요.\n{context}"

        collected = []
        async for token in self.ai_router.stream_text(message_text, system_prompt=system_prompt):
            collected.append(token)
            yield token

        full_content = "".join(collected)
        assistant_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="assistant",
            content=full_content,
            intent="stream_response",
        )
        session_db.add(assistant_msg)
        await session_db.commit()
