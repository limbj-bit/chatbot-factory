import json
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.admin_service import AdminService
from app.core.security import verify_admin_key
from app.infrastructure.database.session import get_db
from app.schemas.admin import AdminClaimApproveRequest, AdminClaimRejectRequest

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
