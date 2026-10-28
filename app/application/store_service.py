import json
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.models import StoreModel
from app.schemas.store import StoreCreateRequest, StoreResponse


INDUSTRY_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "fresh_food": {
        "theme_color": "#2E7D32",
        "welcome_message": "안녕하세요! 신선식품 AI 고객센터입니다. 🍎\n배송 조회, 보관법 및 과일 변질/파손 사진 접수를 도와드립니다.",
        "default_policy": {
            "full_refund_damage_ratio": 30,
            "partial_refund_damage_ratio": 10,
            "max_claim_days": 2,
        },
    },
    "electronics": {
        "theme_color": "#1E40AF",
        "welcome_message": "안녕하세요! 디지털/가전 지능형 A/S 고객센터입니다. ⚡\n기기 작동 불량 자가진단, 고장 부위 사진 판독, 무상 A/S 수리 및 교환 접수를 도와드립니다.",
        "default_policy": {
            "warranty_months": 12,
            "require_serial": True,
            "auto_repair_threshold_ratio": 20,
        },
    },
    "fashion": {
        "theme_color": "#7C3AED",
        "welcome_message": "안녕하세요! 패션&의류 CS 고객센터입니다. 👗\n사이즈 추천, 맞교환 신청, 원단 오염/봉제 불량 사진 판독을 도와드립니다.",
        "default_policy": {
            "max_exchange_days": 7,
            "free_exchange_for_defects": True,
        },
    },
    "beauty": {
        "theme_color": "#EC4899",
        "welcome_message": "안녕하세요! 뷰티&코스메틱 스킨케어 도우미입니다. 💄✨\n피부타입별 전성분 상담, 용기 누유/파손 사진 진단, 피부 트러블 안심 보장 접수를 도와드립니다.",
        "default_policy": {
            "skin_trouble_warranty_days": 14,
            "require_doctor_note_for_trouble": True,
            "unopened_seal_required_for_return": True,
            "leakage_auto_replacement": True,
        },
    },
    "general": {
        "theme_color": "#0D9488",
        "welcome_message": "안녕하세요! 고객센터 AI 도우미입니다. 💬\n배송 조회, 상품 문의 및 불량 접수를 도와드립니다.",
        "default_policy": {
            "max_claim_days": 7,
        },
    },
}


class StoreService:
    """Application Service for managing multi-tenant stores and AS chatbot generation."""

    async def create_store(self, session: AsyncSession, request: StoreCreateRequest) -> StoreResponse:
        store_id = str(uuid.uuid4())
        mall_id = request.mall_id or f"shop_{uuid.uuid4().hex[:8]}"

        # Apply industry defaults if not custom specified
        industry_info = INDUSTRY_DEFAULTS.get(request.industry, INDUSTRY_DEFAULTS["general"])
        theme_color = request.theme_color or industry_info["theme_color"]
        welcome_message = request.welcome_message or industry_info["welcome_message"]

        merged_policy = industry_info["default_policy"].copy()
        if request.policy_config:
            merged_policy.update(request.policy_config)

        store = StoreModel(
            id=store_id,
            mall_id=mall_id,
            store_name=request.store_name,
            industry=request.industry,
            theme_color=theme_color,
            welcome_message=welcome_message,
            policy_config_json=json.dumps(merged_policy, ensure_ascii=False),
        )
        session.add(store)
        await session.commit()
        await session.refresh(store)

        embed_tag = f'<script src="/api/widget/script?mall_id={store.mall_id}" async></script>'

        return StoreResponse(
            store_id=store.id,
            mall_id=store.mall_id,
            store_name=store.store_name,
            industry=store.industry,
            theme_color=store.theme_color,
            welcome_message=store.welcome_message,
            embed_script_tag=embed_tag,
            created_at=store.created_at.isoformat(),
        )

    async def get_store_by_mall_id(self, session: AsyncSession, mall_id: str) -> Optional[StoreModel]:
        q = select(StoreModel).where(StoreModel.mall_id == mall_id)
        res = await session.execute(q)
        return res.scalar_one_or_none()

    async def list_stores(self, session: AsyncSession) -> List[StoreResponse]:
        q = select(StoreModel).order_by(StoreModel.created_at.desc())
        res = await session.execute(q)
        stores = res.scalars().all()
        return [
            StoreResponse(
                store_id=s.id,
                mall_id=s.mall_id,
                store_name=s.store_name,
                industry=s.industry,
                theme_color=s.theme_color,
                welcome_message=s.welcome_message,
                embed_script_tag=f'<script src="/api/widget/script?mall_id={s.mall_id}" async></script>',
                created_at=s.created_at.isoformat(),
            )
            for s in stores
        ]


store_service = StoreService()
