import html
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database.models import StoreKnowledgeModel, StoreModel
from app.schemas.store import (
    StoreCreateRequest,
    StoreKnowledgeCrawlRequest,
    StoreKnowledgeCreateRequest,
    StoreKnowledgeResponse,
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
    """Application Service for managing multi-tenant stores, trial periods, knowledge crawling, and security quotas."""

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

        import math

        remaining_days = max(1, math.ceil(delta_seconds / 86400))
        expiry_warning = remaining_days <= 3

        if expiry_warning:
            exp_str = expires_at.strftime("%Y-%m-%d")
            status_message = f"⚠️ 사용기한 만료 임박 (D-{remaining_days}, {exp_str} 만료 예정) — 서비스가 중단되지 않도록 미리 연장해 주세요!"
        else:
            status_message = f"정상 이용 중 (D-{remaining_days} 남음)"

        return (remaining_days, False, expiry_warning, status_message)

    @staticmethod
    def is_domain_allowed(store: Optional[StoreModel], origin_or_referer: Optional[str]) -> bool:
        """Check if the request's Origin or Referer matches the store's allowed_domains whitelist."""
        if not store or not store.allowed_domains or store.allowed_domains.strip() in ("", "*"):
            return True
        if not origin_or_referer:
            return False

        allowed_list = [
            d.strip().lower()
            for d in store.allowed_domains.split(",")
            if d.strip()
        ]
        if "*" in allowed_list:
            return True

        parsed = urlparse(origin_or_referer)
        host = (parsed.hostname or origin_or_referer).lower()
        return any(host == domain or host.endswith("." + domain) for domain in allowed_list)

    async def check_and_consume_daily_quota(
        self, session: AsyncSession, mall_id: str
    ) -> Tuple[bool, int, int]:
        """
        Check and increment daily AI quota for a store.
        Returns (allowed, used, limit).
        """
        store = await self.get_store_by_mall_id(session, mall_id)
        if not store:
            return (True, 0, 300)

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if store.quota_reset_date != today_str:
            store.quota_reset_date = today_str
            store.daily_quota_used = 0

        if store.daily_quota_used >= store.daily_quota_limit:
            return (False, store.daily_quota_used, store.daily_quota_limit)

        store.daily_quota_used += 1
        await session.commit()
        return (True, store.daily_quota_used, store.daily_quota_limit)

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
            webhook_url=store.webhook_url,
            allowed_domains=store.allowed_domains,
            daily_quota_limit=store.daily_quota_limit,
            daily_quota_used=store.daily_quota_used,
            created_at=store.created_at.isoformat(),
        )

    async def create_store(
        self, session: AsyncSession, request: StoreCreateRequest
    ) -> StoreResponse:
        store_id = str(uuid.uuid4())
        mall_id = request.mall_id or f"shop_{uuid.uuid4().hex[:8]}"

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
            webhook_url=request.webhook_url,
            allowed_domains=request.allowed_domains,
            daily_quota_limit=request.daily_quota_limit,
            daily_quota_used=0,
            quota_reset_date=now.strftime("%Y-%m-%d"),
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

        if update_req.webhook_url is not None:
            store.webhook_url = update_req.webhook_url

        if update_req.allowed_domains is not None:
            store.allowed_domains = update_req.allowed_domains

        if update_req.daily_quota_limit is not None:
            store.daily_quota_limit = update_req.daily_quota_limit

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

    async def add_knowledge(
        self,
        session: AsyncSession,
        mall_id: str,
        req: StoreKnowledgeCreateRequest,
        source_url: Optional[str] = None,
    ) -> StoreKnowledgeResponse:
        doc = StoreKnowledgeModel(
            id=f"DOC-{uuid.uuid4().hex[:8].upper()}",
            mall_id=mall_id,
            doc_type=req.doc_type,
            title=req.title,
            content=req.content,
            source_url=source_url,
            price=req.price,
            purchase_url=req.purchase_url or source_url,
            image_url=req.image_url,
            tags=req.tags,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        return StoreKnowledgeResponse(
            id=doc.id,
            mall_id=doc.mall_id,
            doc_type=doc.doc_type,
            title=doc.title,
            content=doc.content,
            source_url=doc.source_url,
            price=doc.price,
            purchase_url=doc.purchase_url,
            image_url=doc.image_url,
            tags=doc.tags,
            created_at=doc.created_at.isoformat(),
        )

    async def crawl_and_learn_url(
        self,
        session: AsyncSession,
        mall_id: str,
        crawl_req: StoreKnowledgeCrawlRequest,
    ) -> StoreKnowledgeResponse:
        """Fetch product page HTML (or use override), parse title/price/ingredients/description, and store in knowledge base."""
        raw_html = crawl_req.raw_html_override
        if not raw_html:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(
                    crawl_req.url,
                    headers={"User-Agent": "ChatbotFactoryBot/2.0 (+https://railway.app)"},
                )
                resp.raise_for_status()
                raw_html = resp.text

        # Extract <title> or og:title
        title_match = re.search(
            r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']',
            raw_html,
            re.IGNORECASE,
        )
        if not title_match:
            title_match = re.search(r"<title>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
        title = html.unescape(title_match.group(1).strip()) if title_match else crawl_req.url

        # Extract price (e.g., 28,000원 or og:price:amount)
        price: Optional[int] = None
        price_meta = re.search(
            r'property=["\'](?:product:price:amount|og:price:amount)["\']\s+content=["\']([0-9,]+)["\']',
            raw_html,
            re.IGNORECASE,
        )
        if price_meta:
            price = int(price_meta.group(1).replace(",", ""))
        else:
            krw_match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*원", raw_html)
            if krw_match:
                price = int(krw_match.group(1).replace(",", ""))

        # Extract og:image
        img_match = re.search(
            r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']',
            raw_html,
            re.IGNORECASE,
        )
        image_url = img_match.group(1).strip() if img_match else None

        # Strip script/style tags and extract readable body text
        cleaned = re.sub(r"<(script|style|noscript).*?>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = html.unescape(re.sub(r"\s+", " ", cleaned)).strip()
        summary_content = cleaned[:2000] if cleaned else title

        create_req = StoreKnowledgeCreateRequest(
            doc_type="crawled_url",
            title=title[:256],
            content=summary_content,
            price=price,
            purchase_url=crawl_req.url,
            image_url=image_url,
            tags=crawl_req.tags,
        )
        return await self.add_knowledge(session, mall_id, create_req, source_url=crawl_req.url)

    async def list_knowledge(
        self, session: AsyncSession, mall_id: str
    ) -> List[StoreKnowledgeResponse]:
        q = (
            select(StoreKnowledgeModel)
            .where(StoreKnowledgeModel.mall_id == mall_id)
            .order_by(StoreKnowledgeModel.created_at.desc())
        )
        res = await session.execute(q)
        docs = res.scalars().all()
        return [
            StoreKnowledgeResponse(
                id=d.id,
                mall_id=d.mall_id,
                doc_type=d.doc_type,
                title=d.title,
                content=d.content,
                source_url=d.source_url,
                price=d.price,
                purchase_url=d.purchase_url,
                image_url=d.image_url,
                tags=d.tags,
                created_at=d.created_at.isoformat(),
            )
            for d in docs
        ]

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
