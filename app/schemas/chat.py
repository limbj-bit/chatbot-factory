from typing import List, Optional
from pydantic import BaseModel, Field


class ProductRecommendationCard(BaseModel):
    product_id: str
    title: str
    price: Optional[int] = None
    summary: str
    purchase_url: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[str] = None


class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Client session ID")
    customer_id: str = Field("guest", description="Customer ID or guest")
    mall_id: str = Field("demo_mall", description="Store Mall ID for multi-tenant RAG and quota tracking")
    message: str = Field(..., min_length=1, max_length=2000, description="Customer question")


class ChatResponse(BaseModel):
    session_id: str
    message: str
    intent: str
    recommended_products: List[ProductRecommendationCard] = Field(
        default_factory=list,
        description="AI 카운슬러가 추천하는 스토어 맞춤 상품 카드 목록",
    )
