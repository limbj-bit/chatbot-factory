from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.infrastructure.database.session import get_db

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_db)):
    db_ok = False
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "database": "connected" if db_ok else "disconnected",
        "mock_ai": settings.MOCK_AI,
        "mock_cafe24": settings.MOCK_CAFE24,
        "deploy_marker": "schema-heal-v2",
    }


@router.get("/health/ai")
async def ai_health_check():
    """Live AI routing snapshot: provider order, models, cooldowns, latency.

    No secrets are exposed — this answers "which model is actually answering
    right now?" without digging through Render logs.
    """
    from app.api.chat import chat_service

    router = chat_service.ai_router
    if hasattr(router, "get_status"):
        return router.get_status()
    return {"mock_mode": settings.MOCK_AI, "providers": list(getattr(router, "providers", {}))}
