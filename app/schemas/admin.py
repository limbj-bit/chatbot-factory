from typing import Optional
from pydantic import BaseModel, Field


class AdminClaimApproveRequest(BaseModel):
    refund_amount: int = Field(..., ge=0, description="Approved refund amount in KRW")
    reason: str = Field(..., min_length=2, description="Admin approval reason")


class AdminClaimRejectRequest(BaseModel):
    reason: str = Field(..., min_length=2, description="Admin rejection reason")
