from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class StoreCreateRequest(BaseModel):
    store_name: str = Field(..., min_length=2, max_length=128, description="스토어 명칭 (예: 한빛디지털 AS센터)")
    industry: str = Field("electronics", description="업종 템플릿 (electronics, fresh_food, fashion, beauty, general)")
    mall_id: Optional[str] = Field(None, description="스토어 고유 ID (생략 시 자동 생성)")
    theme_color: Optional[str] = Field(None, description="위젯 테마 색상 HEX 코드 (생략 시 업종 기본 테마 적용)")
    welcome_message: Optional[str] = Field(None, description="고객 첫 접속 웰컴 인사말")
    policy_config: Optional[Dict[str, Any]] = Field(None, description="스토어별 AS/환불 정책 임계값")
    trial_days: Optional[int] = Field(
        14,
        ge=0,
        le=3650,
        description="무료 사용기한 일수 (예: 14일, 0이면 즉시 만료 테스트, None이면 무제한)",
    )


class StoreSubscriptionUpdateRequest(BaseModel):
    extend_days: Optional[int] = Field(None, ge=1, le=3650, description="연장할 일수 (예: 30)")
    plan_type: Optional[str] = Field(None, description="요금제 상태 (free_trial, active, unlimited, suspended)")
    is_active: Optional[bool] = Field(None, description="활성화 여부")


class StoreResponse(BaseModel):
    store_id: str
    mall_id: str
    store_name: str
    industry: str
    theme_color: str
    welcome_message: str
    embed_script_tag: str
    plan_type: str
    trial_days: Optional[int]
    expires_at: Optional[str]
    remaining_days: Optional[int]
    is_expired: bool
    expiry_warning: bool
    status_message: str
    created_at: str
