import json
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.application.claim_service import ClaimService
from app.infrastructure.database.models import ClaimImageModel, ClaimModel
from app.infrastructure.database.session import get_db
from app.schemas.claim import (
    ClaimCreateRequest,
    ClaimImageUploadResponse,
    ClaimResponse,
)

router = APIRouter(prefix="/api/claims", tags=["Claims"])
claim_service = ClaimService()


@router.post("", response_model=ClaimResponse)
async def create_claim_endpoint(
    request: ClaimCreateRequest, session: AsyncSession = Depends(get_db)
):
    claim = await claim_service.create_claim(
        session=session,
        order_id=request.order_id,
        customer_id=request.customer_id,
        claim_type=request.claim_type,
        description=request.description,
    )
    return ClaimResponse(
        claim_id=claim.id,
        order_id=claim.order_id,
        customer_id=claim.customer_id,
        claim_type=claim.claim_type,
        status=claim.status,
        description=claim.description,
        refund_amount=claim.refund_amount,
    )


@router.post("/{claim_id}/images", response_model=ClaimImageUploadResponse)
async def upload_claim_image_endpoint(
    claim_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    content = await file.read()
    try:
        claim, decision = await claim_service.process_image_and_evaluate(
            session=session,
            claim_id=claim_id,
            file_bytes=content,
            filename=file.filename or "upload.jpg",
            declared_mime=file.content_type or "image/jpeg",
        )
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        )

    # Get latest image observation for response
    img_q = (
        select(ClaimImageModel)
        .where(ClaimImageModel.claim_id == claim_id)
        .order_by(ClaimImageModel.created_at.desc())
    )
    img_res = await session.execute(img_q)
    latest_img = img_res.scalars().first()

    observation_data = {}
    if latest_img:
        observation_data = {
            "defect_type": latest_img.defect_type,
            "damage_ratio": latest_img.damage_ratio,
            "confidence": latest_img.confidence,
            "evidence": json.loads(latest_img.evidence_json or "[]"),
            "image_quality": latest_img.image_quality,
        }

    return ClaimImageUploadResponse(
        claim_id=claim.id,
        status=claim.status,
        decision=decision.decision.value,
        reason_code=decision.reason_code.value,
        refund_ratio=decision.refund_ratio,
        refund_amount=claim.refund_amount,
        customer_message=decision.suggested_customer_message,
        requires_manual_review=decision.requires_manual_review,
        observation=observation_data,
    )


@router.get("/{claim_id}", response_model=ClaimResponse)
async def get_claim_endpoint(claim_id: str, session: AsyncSession = Depends(get_db)):
    claim_q = await session.execute(select(ClaimModel).where(ClaimModel.id == claim_id))
    claim = claim_q.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Claim not found")

    return ClaimResponse(
        claim_id=claim.id,
        order_id=claim.order_id,
        customer_id=claim.customer_id,
        claim_type=claim.claim_type,
        status=claim.status,
        description=claim.description,
        refund_amount=claim.refund_amount,
    )
