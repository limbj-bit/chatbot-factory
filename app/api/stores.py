from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.notification_service import notification_service
from app.application.store_service import store_service
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
    """Extend a store's trial/subscription period, webhook URL, allowed domains, or daily quota."""
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
