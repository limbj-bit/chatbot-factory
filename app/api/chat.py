import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.chat_service import ChatService
from app.infrastructure.database.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["Chat"])
chat_service = ChatService()


@router.post("", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, session: AsyncSession = Depends(get_db)):
    """Synchronous chat endpoint with FAQ, Multi-tenant RAG, AI Counselor product cards, and Daily Quota gating."""
    session_id, response_text, intent, recommended_products = await chat_service.handle_message(
        session_db=session,
        session_id=request.session_id,
        customer_id=request.customer_id,
        message_text=request.message,
        mall_id=request.mall_id,
    )
    return ChatResponse(
        session_id=session_id,
        message=response_text,
        intent=intent,
        recommended_products=recommended_products,
    )


@router.post("/stream")
async def chat_stream_endpoint(request: ChatRequest, session: AsyncSession = Depends(get_db)):
    """SSE streaming chat endpoint delivering real-time tokens and recommended product cards."""

    async def sse_event_generator():
        try:
            # Also retrieve recommended product cards if any
            results = await chat_service.rag.search_with_store_knowledge(
                session, request.mall_id, request.message, top_k=2
            )
            cards = chat_service._build_product_cards(results)

            async for token in chat_service.stream_chat_response(
                session_db=session,
                session_id=request.session_id,
                customer_id=request.customer_id,
                message_text=request.message,
                mall_id=request.mall_id,
            ):
                payload = json.dumps({"token": token}, ensure_ascii=False)
                yield f"data: {payload}\n\n"

            if cards:
                cards_payload = json.dumps(
                    {"recommended_products": [c.model_dump() for c in cards]},
                    ensure_ascii=False,
                )
                yield f"data: {cards_payload}\n\n"
        except Exception as e:
            err_payload = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"data: {err_payload}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
