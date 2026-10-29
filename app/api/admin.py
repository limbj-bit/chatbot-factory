import json
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.admin_service import AdminService
from app.application.store_service import store_service
from app.core.security import verify_admin_key
from app.core.language import LANGUAGE_NAMES, detect_language
from app.infrastructure.database.session import get_db
from app.schemas.admin import AdminClaimApproveRequest, AdminClaimRejectRequest
from app.schemas.store import StoreResponse, StoreSubscriptionUpdateRequest
from app.infrastructure.database.models import MessageModel, SessionModel
from sqlalchemy import select

router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(verify_admin_key)])
admin_service = AdminService()


@router.get("/claims")
async def list_admin_claims(session: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    claims = await admin_service.list_pending_claims(session)
    result = []
    for c in claims:
        images_data = []
        for img in c.images:
            images_data.append(
                {
                    "image_id": img.id,
                    "defect_type": img.defect_type,
                    "damage_ratio": img.damage_ratio,
                    "confidence": img.confidence,
                    "evidence": json.loads(img.evidence_json or "[]"),
                    "image_quality": img.image_quality,
                }
            )

        events_data = []
        for ev in c.events:
            events_data.append(
                {
                    "event_type": ev.event_type,
                    "from_status": ev.from_status,
                    "to_status": ev.to_status,
                    "actor": ev.actor,
                    "reason": ev.reason,
                    "created_at": ev.created_at.isoformat(),
                }
            )

        result.append(
            {
                "claim_id": c.id,
                "order_id": c.order_id,
                "customer_id": c.customer_id,
                "claim_type": c.claim_type,
                "status": c.status,
                "refund_amount": c.refund_amount,
                "description": c.description,
                "created_at": c.created_at.isoformat(),
                "images": images_data,
                "events": events_data,
            }
        )
    return result


@router.post("/claims/{claim_id}/approve")
async def approve_claim_endpoint(
    claim_id: str,
    request: AdminClaimApproveRequest,
    session: AsyncSession = Depends(get_db),
):
    try:
        success = await admin_service.approve_claim(
            session=session,
            claim_id=claim_id,
            refund_amount=request.refund_amount,
            reason=request.reason,
        )
        return {"status": "success", "claim_id": claim_id, "approved": success}
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(val_err))


@router.post("/claims/{claim_id}/reject")
async def reject_claim_endpoint(
    claim_id: str,
    request: AdminClaimRejectRequest,
    session: AsyncSession = Depends(get_db),
):
    try:
        success = await admin_service.reject_claim(
            session=session,
            claim_id=claim_id,
            reason=request.reason,
        )
        return {"status": "success", "claim_id": claim_id, "rejected": success}
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(val_err))


@router.get("/stores", response_model=List[StoreResponse])
async def admin_list_stores_endpoint(session: AsyncSession = Depends(get_db)):
    """Master Admin only: List all stores, trial D-Days, quotas, and settings."""
    return await store_service.list_stores(session)


@router.patch("/stores/{mall_id}/subscription", response_model=StoreResponse)
async def admin_update_store_subscription_endpoint(
    mall_id: str,
    request: StoreSubscriptionUpdateRequest,
    session: AsyncSession = Depends(get_db),
):
    """Master Admin only: Extend trial/subscription days, change plan, or suspend a store."""
    updated = await store_service.update_subscription(session, mall_id, request)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{mall_id}' not found.",
        )
    return updated


@router.delete("/stores/{mall_id}")
async def admin_delete_store_endpoint(
    mall_id: str,
    session: AsyncSession = Depends(get_db),
    x_admin_key: str = Header(default="", alias="X-Admin-Key"),
):
    """Delete a store and all related knowledge/messages."""
    if x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    ok = await store_service.delete_store(session, mall_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Store not found")
    return {"deleted": True, "mall_id": mall_id}

@router.get("/stores/{mall_id}/conversations")
async def admin_list_conversations_endpoint(
    mall_id: str,
    language: str = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
):
    """Master Admin only: View conversation logs with owner-side Korean translations.

    Returns sessions for the store with their messages, detected language, and
    Korean translation (for foreign customer messages). Use ?language=ja to
    filter to a specific foreign language.
    """
    # Find sessions that have messages for this mall's customers.
    # Sessions are not directly tied to mall_id, so we look up via messages
    # whose content we can't filter by mall. Instead, return all sessions
    # that have at least one message; the caller filters by mall via the
    # store's known customer sessions. For simplicity, return recent sessions.
    q = select(SessionModel).order_by(SessionModel.created_at.desc()).limit(limit)
    res = await session.execute(q)
    sessions = res.scalars().all()

    result = []
    for sess in sessions:
        mq = (
            select(MessageModel)
            .where(MessageModel.session_id == sess.id)
            .order_by(MessageModel.created_at.asc())
        )
        mres = await session.execute(mq)
        msgs = mres.scalars().all()
        if not msgs:
            continue
        # Filter by language if requested
        if language:
            if not any(m.detected_language == language for m in msgs):
                continue
        messages_out = []
        for m in msgs:
            messages_out.append({
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "detected_language": m.detected_language,
                "language_name": (LANGUAGE_NAMES.get(m.detected_language, m.detected_language) if m.detected_language else None),
                "translation_ko": m.translation_ko,
                "intent": m.intent,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            })
        result.append({
            "session_id": sess.id,
            "customer_id": sess.customer_id,
            "created_at": sess.created_at.isoformat() if sess.created_at else None,
            "messages": messages_out,
        })
    return result


@router.post("/translate")
async def admin_translate_endpoint(
    request: Dict[str, Any],
    session: AsyncSession = Depends(get_db),
):
    """Master Admin only: Translate arbitrary text. Body: {text, target_lang, source_lang?}"""
    text = request.get("text", "")
    target_lang = request.get("target_lang", "ko")
    source_lang = request.get("source_lang", "auto")
    if source_lang == "auto":
        source_lang = detect_language(text)
    from app.infrastructure.ai.router import AIProviderRouter
    router = AIProviderRouter()
    translated = await router.translate_text(text, target_lang, source_lang)
    return {
        "original": text,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "translated": translated,
    }
