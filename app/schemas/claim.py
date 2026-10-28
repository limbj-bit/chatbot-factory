from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ClaimCreateRequest(BaseModel):
    order_id: str = Field(..., description="E-commerce Order ID")
    customer_id: str = Field(..., description="Customer ID")
    claim_type: str = Field("fresh_defect", description="Type of claim (fresh_defect, wrong_delivery, etc.)")
    description: str = Field(..., min_length=2, max_length=2000, description="Customer issue description")


class ClaimResponse(BaseModel):
    claim_id: str
    order_id: str
    customer_id: str
    claim_type: str
    status: str
    description: str
    refund_amount: int


class ClaimImageUploadResponse(BaseModel):
    claim_id: str
    status: str
    decision: str
    reason_code: str
    refund_ratio: int
    refund_amount: int
    customer_message: str
    requires_manual_review: bool
    observation: Dict[str, Any]
