from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Client session ID")
    customer_id: str = Field("guest", description="Customer ID or guest")
    message: str = Field(..., min_length=1, max_length=2000, description="Customer question")


class ChatResponse(BaseModel):
    session_id: str
    message: str
    intent: str
