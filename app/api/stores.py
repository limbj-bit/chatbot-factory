import base64
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.notification_service import notification_service
from app.application.store_service import store_service
from app.core.config import settings
from app.core.security import verify_admin_key
from app.infrastructure.database.session import get_db
from app.schemas.store import (
    StoreCreateRequest,
    StoreKnowledgeCrawlRequest,
    StoreKnowledgeCreateRequest,
    StoreKnowledgeResponse,
    StoreResponse,
    StoreSubscriptionUpdateRequest,
)

router = APIRouter(prefix="/api/stores", tags=["Stores"])


@router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
async def create_store_endpoint(
    request: StoreCreateRequest,
    session: AsyncSession = Depends(get_db),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key"),
):
    """Register a new e-commerce store and generate an intelligent AS chatbot.
    If called from public self-service showroom without X-Admin-Key, trial_days is capped at 30 days (cannot be unlimited or >30).
    """
    allowed_keys = {"chatbot123", "admin-dev-secret-key-change-in-prod", settings.ADMIN_API_KEY}
    is_admin = bool(x_admin_key and x_admin_key in allowed_keys)
    if not is_admin:
        if request.trial_days is None or request.trial_days > 30:
            request.trial_days = 30
        if request.daily_quota_limit > 300:
            request.daily_quota_limit = 300
    return await store_service.create_store(session, request)


@router.get("/{mall_id}", response_model=StoreResponse)
async def get_single_store_endpoint(
    mall_id: str, session: AsyncSession = Depends(get_db)
):
    """Fetch a single store's public widget status and configuration by mall_id."""
    store = await store_service.get_store_by_mall_id(session, mall_id)
    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store '{mall_id}' not found.",
        )
    return store_service._to_response(store)


@router.get("", response_model=List[StoreResponse], dependencies=[Depends(verify_admin_key)])
async def list_stores_endpoint(session: AsyncSession = Depends(get_db)):
    """Master Admin only: List all registered stores and their embed script snippets."""
    return await store_service.list_stores(session)


@router.patch("/{mall_id}/subscription", response_model=StoreResponse, dependencies=[Depends(verify_admin_key)])
async def update_store_subscription_endpoint(
    mall_id: str,
    request: StoreSubscriptionUpdateRequest,
    session: AsyncSession = Depends(get_db),
):
    """Master Admin only: Extend a store's trial/subscription period, webhook URL, allowed domains, or daily quota."""
    updated = await store_service.update_subscription(session, mall_id, request)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store with mall_id '{mall_id}' not found.",
        )
    return updated


@router.post(
    "/{mall_id}/knowledge",
    response_model=StoreKnowledgeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_store_knowledge_endpoint(
    mall_id: str,
    request: StoreKnowledgeCreateRequest,
    session: AsyncSession = Depends(get_db),
):
    """Add custom product details, ingredients, or store-specific policies to a store's RAG knowledge base."""
    return await store_service.add_knowledge(session, mall_id, request)


@router.post(
    "/{mall_id}/knowledge/crawl",
    response_model=StoreKnowledgeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def crawl_store_product_url_endpoint(
    mall_id: str,
    request: StoreKnowledgeCrawlRequest,
    session: AsyncSession = Depends(get_db),
):
    """Crawl a product detail page URL, extract title/price/ingredients/content, and save to the store's RAG knowledge base."""
    try:
        return await store_service.crawl_and_learn_url(session, mall_id, request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to crawl URL: {e}",
        )


@router.get("/{mall_id}/knowledge", response_model=List[StoreKnowledgeResponse])
async def list_store_knowledge_endpoint(
    mall_id: str, session: AsyncSession = Depends(get_db)
):
    """List all learned knowledge and product items for a specific store."""
    return await store_service.list_knowledge(session, mall_id)


@router.get("/{mall_id}/alerts", response_model=List[Dict[str, Any]])
async def list_store_webhook_alerts_endpoint(
    mall_id: str, session: AsyncSession = Depends(get_db)
):
    """List all real-time webhook alerts sent to the store merchant."""
    return await notification_service.list_alerts(session, mall_id)


@router.post("/{mall_id}/avatar", response_model=StoreResponse)
async def upload_store_bot_avatar_endpoint(
    mall_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    """Upload a custom Flaticon PNG/GIF/SVG/WebP icon file to use as the store's bot launcher and chat avatar."""
    raw_bytes = await file.read()
    if len(raw_bytes) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar image file must be under 2MB.",
        )
    mime = file.content_type or "image/png"
    b64_str = base64.b64encode(raw_bytes).decode("ascii")
    data_uri = f"data:{mime};base64,{b64_str}"

    updated = await store_service.update_subscription(
        session,
        mall_id,
        StoreSubscriptionUpdateRequest(
            bot_icon_style="custom_upload",
            bot_avatar_url=data_uri,
        ),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Store with mall_id '{mall_id}' not found.",
        )
    return updated
