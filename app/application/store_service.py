import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.models import StoreModel
from app.schemas.store import (
    StoreCreateRequest,
    StoreResponse,
    StoreSubscriptionUpdateRequest,
)


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
    """Application Service for managing multi-tenant stores, trial periods, and AS chatbot generation."""

    @staticmethod
    def evaluate_subscription_status(
        store: StoreModel,
    ) -> Tuple[Optional[int], bool, bool, str]:
        """
        Evaluate a store's subscription status.
        Returns: (remaining_days, is_expired, expiry_warning, status_message)
        """
        if not store.is_active or store.plan_type == "suspended":
            return (
                0,
                True,
                False,
                "서비스 이용이 일시 중지되었습니다. 관리자에게 문의해 주세요.",
            )

        if store.plan_type == "unlimited" or store.expires_at is None:
            return (None, False, False, "정상 이용 중 (무제한 플랜)")

        now = datetime.now(timezone.utc)
        expires_at = store.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        delta_seconds = (expires_at - now).total_seconds()
        if delta_seconds <= 0:
            return (
                0,
                True,
                False,
                "무료 체험(이용) 기간이 만료되었습니다. 서비스 연장 문의는 관리자에게 연락해 주세요.",
            )

        # Calculate ceil remaining days (e.g., 2.1 days -> 3 days, 0.5 days -> 1 day)
        import math

        remaining_days = max(1, math.ceil(delta_seconds / 86400))
        expiry_warning = remaining_days <= 3

        if expiry_warning:
            exp_str = expires_at.strftime("%Y-%m-%d")
            status_message = f"⚠️ 사용기한 만료 임박 (D-{remaining_days}, {exp_str} 만료 예정) — 서비스가 중단되지 않도록 미리 연장해 주세요!"
        else:
            status_message = f"정상 이용 중 (D-{remaining_days} 남음)"

        return (remaining_days, False, expiry_warning, status_message)

    def _to_response(self, store: StoreModel) -> StoreResponse:
        remaining_days, is_expired, expiry_warning, status_message = (
            self.evaluate_subscription_status(store)
        )
        embed_tag = f'<script src="/api/widget/script?mall_id={store.mall_id}" async></script>'
        return StoreResponse(
            store_id=store.id,
            mall_id=store.mall_id,
            store_name=store.store_name,
            industry=store.industry,
            theme_color=store.theme_color,
            welcome_message=store.welcome_message,
            embed_script_tag=embed_tag,
            plan_type=store.plan_type,
            trial_days=store.trial_days,
            expires_at=store.expires_at.isoformat() if store.expires_at else None,
            remaining_days=remaining_days,
            is_expired=is_expired,
            expiry_warning=expiry_warning,
            status_message=status_message,
            created_at=store.created_at.isoformat(),
        )

    async def create_store(
        self, session: AsyncSession, request: StoreCreateRequest
    ) -> StoreResponse:
        store_id = str(uuid.uuid4())
        mall_id = request.mall_id or f"shop_{uuid.uuid4().hex[:8]}"

        # Apply industry defaults if not custom specified
        industry_info = INDUSTRY_DEFAULTS.get(
            request.industry, INDUSTRY_DEFAULTS["general"]
        )
        theme_color = request.theme_color or industry_info["theme_color"]
        welcome_message = request.welcome_message or industry_info["welcome_message"]

        merged_policy = industry_info["default_policy"].copy()
        if request.policy_config:
            merged_policy.update(request.policy_config)

        now = datetime.now(timezone.utc)
        if request.trial_days is None:
            plan_type = "unlimited"
            expires_at = None
        elif request.trial_days == 0:
            plan_type = "free_trial"
            expires_at = now - timedelta(seconds=1)
        else:
            plan_type = "free_trial"
            expires_at = now + timedelta(days=request.trial_days)

        store = StoreModel(
            id=store_id,
            mall_id=mall_id,
            store_name=request.store_name,
            industry=request.industry,
            theme_color=theme_color,
            welcome_message=welcome_message,
            policy_config_json=json.dumps(merged_policy, ensure_ascii=False),
            plan_type=plan_type,
            trial_days=request.trial_days,
            expires_at=expires_at,
            is_active=True,
        )
        session.add(store)
        await session.commit()
        await session.refresh(store)

        return self._to_response(store)

    async def update_subscription(
        self,
        session: AsyncSession,
        mall_id: str,
        update_req: StoreSubscriptionUpdateRequest,
    ) -> Optional[StoreResponse]:
        store = await self.get_store_by_mall_id(session, mall_id)
        if not store:
            return None

        now = datetime.now(timezone.utc)

        if update_req.plan_type is not None:
            store.plan_type = update_req.plan_type
            if update_req.plan_type == "unlimited":
                store.expires_at = None

        if update_req.is_active is not None:
            store.is_active = update_req.is_active

        if update_req.extend_days is not None and update_req.extend_days > 0:
            base_time = now
            if store.expires_at:
                exp = store.expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp > now:
                    base_time = exp
            store.expires_at = base_time + timedelta(days=update_req.extend_days)
            store.is_active = True
            if store.plan_type == "suspended":
                store.plan_type = "active"

        await session.commit()
        await session.refresh(store)
        return self._to_response(store)

    async def get_store_by_mall_id(
        self, session: AsyncSession, mall_id: str
    ) -> Optional[StoreModel]:
        q = select(StoreModel).where(StoreModel.mall_id == mall_id)
        res = await session.execute(q)
        return res.scalar_one_or_none()

    async def list_stores(self, session: AsyncSession) -> List[StoreResponse]:
        q = select(StoreModel).order_by(StoreModel.created_at.desc())
        res = await session.execute(q)
        stores = res.scalars().all()
        return [self._to_response(s) for s in stores]


store_service = StoreService()
