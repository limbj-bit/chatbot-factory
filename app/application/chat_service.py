import time
import uuid
from typing import AsyncIterator, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger
from app.domain.ports.ai_port import AIProviderPort
from app.infrastructure.ai.router import AIProviderRouter
from app.infrastructure.database.models import MessageModel, SessionModel
from app.infrastructure.rag.engine import RAGEngine, rag_engine
from app.application.order_service import OrderService


class ChatService:
    """Application Service for chat orchestration, intent routing, and SSE streaming."""

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

    async def handle_message(
        self,
        session_db: AsyncSession,
        session_id: Optional[str],
        customer_id: str,
        message_text: str,
    ) -> Tuple[str, str, str]:
        """Handle synchronous chat message with Cache -> FAQ -> RAG -> LLM routing.
        
        Returns (session_id, response_text, intent).
        """
        chat_session = await self.get_or_create_session(session_db, session_id, customer_id)
        start_time = time.time()

        # 1. Record User Message
        user_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="user",
            content=message_text,
        )
        session_db.add(user_msg)
        await session_db.flush()

        # 2. Check 0-token Deterministic FAQ first
        faq_answer = self.rag.lookup_deterministic_faq(message_text)
        if faq_answer:
            intent = "faq_deterministic"
            response_text = faq_answer
        elif "주문" in message_text or "배송" in message_text or "ORD-" in message_text:
            intent = "shipping_inquiry"
            # Extract potential order id
            import re
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
        elif any(k in message_text for k in ["보관", "먹는법", "섭취", "토마토", "딸기", "품질", "보상"]):
            intent = "rag_product_inquiry"
            results = self.rag.search(message_text, top_k=2)
            context = self.rag.assemble_context(results)
            system_prompt = (
                "당신은 신선식품 전문 상담 AI입니다. 주어진 공식 지식 베이스의 사실만 기반으로 친절하고 간결하게 답변하세요.\n"
                f"{context}"
            )
            response_text = await self.ai_router.generate_text(message_text, system_prompt=system_prompt)
        else:
            intent = "general_cs"
            response_text = await self.ai_router.generate_text(message_text)

        latency_ms = int((time.time() - start_time) * 1000)

        # 3. Record Assistant Message
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

        return chat_session.id, response_text, intent

    async def stream_chat_response(
        self,
        session_db: AsyncSession,
        session_id: Optional[str],
        customer_id: str,
        message_text: str,
    ) -> AsyncIterator[str]:
        """Stream SSE tokens while saving messages."""
        chat_session = await self.get_or_create_session(session_db, session_id, customer_id)

        # Record User Message
        user_msg = MessageModel(
            id=str(uuid.uuid4()),
            session_id=chat_session.id,
            role="user",
            content=message_text,
        )
        session_db.add(user_msg)
        await session_db.commit()

        # Check FAQ first
        faq_answer = self.rag.lookup_deterministic_faq(message_text)
        if faq_answer:
            words = faq_answer.split(" ")
            for i, w in enumerate(words):
                yield w + (" " if i < len(words) - 1 else "")
            # Save Assistant Message
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

        # RAG context if applicable
        system_prompt = None
        if any(k in message_text for k in ["보관", "먹는법", "토마토", "딸기"]):
            results = self.rag.search(message_text, top_k=2)
            context = self.rag.assemble_context(results)
            system_prompt = f"당신은 신선식품 전문 상담 AI입니다. 사실에 기반하여 친절하게 답변하세요.\n{context}"

        collected = []
        async for token in self.ai_router.stream_text(message_text, system_prompt=system_prompt):
            collected.append(token)
            yield token

        # Save complete stream to DB
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
