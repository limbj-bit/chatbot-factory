from typing import Any, Dict, List, Optional
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
    webhook_url: Optional[str] = Field(None, description="인간 상담원 이관/긴급 클레임 발생 시 알림을 받을 웹훅 URL (슬랙/텔레그램/디스코드 등)")
    allowed_domains: Optional[str] = Field(None, description="위젯 설치 허용 도메인 목록 (콤마 구분, 예: lumiere.co.kr,localhost)")
    daily_quota_limit: int = Field(300, ge=1, le=100000, description="스토어 일일 무료 AI 상담 호출 한도")
    bot_icon_style: Optional[str] = Field(
        None,
        description="봇 아이콘 프리셋 (flaticon_cute_robot, flaticon_beauty_fairy, flaticon_cs_agent, flaticon_bubble_bot, flaticon_smart_ai, custom_upload)",
    )
    launcher_shape: str = Field(
        "cosbot_badge",
        description="런처 버튼 모양 (cosbot_badge: 원형+하단캡슐라벨, sticker: 투명스티커형, circle: 심플원형, pill: 가로캡슐형)",
    )
    bot_label: Optional[str] = Field(
        None,
        max_length=24,
        description="버튼 하단 캡슐 배지 문구 (예: 코스봇 상담, 뷰티봇 상담, A/S봇 상담)",
    )
    bot_avatar_url: Optional[str] = Field(
        None,
        description="직접 업로드한 Flaticon PNG/GIF/SVG 데이터 URI 또는 외부 이미지 URL",
    )


class StoreSubscriptionUpdateRequest(BaseModel):
    extend_days: Optional[int] = Field(None, ge=1, le=3650, description="연장할 일수 (예: 30)")
    plan_type: Optional[str] = Field(None, description="요금제 상태 (free_trial, active, unlimited, suspended)")
    is_active: Optional[bool] = Field(None, description="활성화 여부")
    webhook_url: Optional[str] = Field(None, description="알림 웹훅 URL 변경")
    allowed_domains: Optional[str] = Field(None, description="허용 도메인 변경")
    daily_quota_limit: Optional[int] = Field(None, ge=1, le=100000, description="일일 AI 호출 쿼터 한도 변경")
    bot_icon_style: Optional[str] = Field(None, description="봇 아이콘 프리셋 변경")
    launcher_shape: Optional[str] = Field(None, description="런처 버튼 모양 변경")
    bot_label: Optional[str] = Field(None, max_length=24, description="하단 캡슐 라벨 문구 변경")
    bot_avatar_url: Optional[str] = Field(None, description="커스텀 아바타 이미지 URL 또는 Data URI 변경")


class StoreKnowledgeCreateRequest(BaseModel):
    doc_type: str = Field("product", description="지식 유형 (product, policy, faq, crawled_url)")
    title: str = Field(..., min_length=1, max_length=256, description="상품명 또는 규정 제목")
    content: str = Field(..., min_length=1, description="상품 상세 설명, 전성분, 주의사항 또는 규정 본문")
    price: Optional[int] = Field(None, ge=0, description="상품 판매가 (원)")
    purchase_url: Optional[str] = Field(None, description="상품 바로 구매하기 링크 URL")
    image_url: Optional[str] = Field(None, description="상품 썸네일 이미지 URL")
    tags: Optional[str] = Field(None, description="검색/추천 키워드 태그 (예: 건성,민감성,진정,시카,임산부)")


class StoreKnowledgeCrawlRequest(BaseModel):
    url: str = Field(..., description="자동 학습할 쇼핑몰 상품 상세페이지 URL")
    raw_html_override: Optional[str] = Field(
        None,
        description="외부 네트워크 차단 환경이나 테스트 시 직접 주입할 HTML 본문 (생략 시 URL에서 직접 수집)",
    )
    tags: Optional[str] = Field(None, description="추가할 추천 태그")


class StoreKnowledgeResponse(BaseModel):
    id: str
    mall_id: str
    doc_type: str
    title: str
    content: str
    source_url: Optional[str] = None
    price: Optional[int] = None
    purchase_url: Optional[str] = None
    image_url: Optional[str] = None
    tags: Optional[str] = None
    created_at: str


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
    webhook_url: Optional[str] = None
    allowed_domains: Optional[str] = None
    daily_quota_limit: int = 300
    daily_quota_used: int = 0
    bot_icon_style: str = "flaticon_cute_robot"
    launcher_shape: str = "cosbot_badge"
    bot_label: str = "AI봇 상담"
    bot_avatar_url: Optional[str] = None
    created_at: str
