from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.store_service import store_service
from app.infrastructure.database.session import get_db
from app.schemas.store import (
    StoreCreateRequest,
    StoreResponse,
    StoreSubscriptionUpdateRequest,
)

router = APIRouter(prefix="/api/stores", tags=["Stores"])


@router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
async def create_store_endpoint(
    request: StoreCreateRequest, session: AsyncSession = Depends(get_db)
):
    """Register a new e-commerce store and generate an intelligent AS chatbot."""
    return await store_service.create_store(session, request)


@router.get("", response_model=List[StoreResponse])
async def list_stores_endpoint(session: AsyncSession = Depends(get_db)):
    """List all registered stores and their embed script snippets."""
    return await store_service.list_stores(session)


@router.patch("/{mall_id}/subscription", response_model=StoreResponse)
async def update_store_subscription_endpoint(
    mall_id: str,
    request: StoreSubscriptionUpdateRequest,
    session: AsyncSession = Depends(get_db),
):
    """Extend a store's trial/subscription period or update its plan status."""
    updated = await store_service.update_subscription(session, mall_id, request)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store with mall_id '{mall_id}' not found.",
        )
    return updated
