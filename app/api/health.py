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

    # Report the *effective* AI mode, not the config flag. The router silently
    # falls back to MockAIProvider when no provider key is present, so reading
    # settings.MOCK_AI alone can claim "live" while answering with canned text.
    ai_status: dict = {}
    try:
        from app.api.chat import chat_service

        ai_status = chat_service.ai_router.get_status()
    except Exception as exc:  # pragma: no cover - health must never raise
        ai_status = {"status_error": f"{type(exc).__name__}: {exc}"}
    effective_mock_ai = bool(ai_status.get("mock_mode", settings.MOCK_AI))

    return {
        "status": "healthy" if db_ok else "degraded",
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "database": "connected" if db_ok else "disconnected",
        "mock_ai": effective_mock_ai,
        "configured_mock_ai": settings.MOCK_AI,
        "mock_cafe24": settings.MOCK_CAFE24,
        "ai_provider_order": ai_status.get("provider_order"),
        "live_provider_count": ai_status.get("live_provider_count"),
        "deploy_marker": "schema-heal-v3",
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
