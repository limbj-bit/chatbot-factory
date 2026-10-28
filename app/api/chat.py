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
    """Synchronous chat endpoint with FAQ and RAG integration."""
    session_id, response_text, intent = await chat_service.handle_message(
        session_db=session,
        session_id=request.session_id,
        customer_id=request.customer_id,
        message_text=request.message,
    )
    return ChatResponse(
        session_id=session_id,
        message=response_text,
        intent=intent,
    )


@router.post("/stream")
async def chat_stream_endpoint(request: ChatRequest, session: AsyncSession = Depends(get_db)):
    """SSE streaming chat endpoint delivering real-time tokens."""

    async def sse_event_generator():
        try:
            async for token in chat_service.stream_chat_response(
                session_db=session,
                session_id=request.session_id,
                customer_id=request.customer_id,
                message_text=request.message,
            ):
                payload = json.dumps({"token": token}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
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
