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
from app.application.commerce_service import commerce_service
from app.core.logging import logger
from app.core.security import encryption_available
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
    "raw_materials": {
        "theme_color": "#0284C7",
        "bot_icon_style": "flaticon_cute_robot",
        "bot_label": "코스봇 상담",
        "bot_name": "코스봇",
        "welcome_message": "안녕하세요. 코스라프리의 AI 상담사 '코스봇' 입니다. 🧪\n어떤 원료나 서비스가 궁금하신가요?",
        "quick_buttons": [
            "🧪 성분 규격 & 공급사",
            "🥕 원료 장터 이용 문의",
            "🏢 협회 COA/MSDS 조회",
            "🏭 제조사 등록 / 입점",
            "💬 그 외 다른 질문하기",
        ],
        "contact_email": "contact@cosrawfree.com",
        "input_placeholder": "궁금한 성분명(예: 레티놀)이나 질문을 입력하세요...",
        "upload_guide": "📄 성적서(COA) / 원료 샘플 사진 업로드 판독",
        "default_policy": {"max_claim_days": 7},
    },
    "beauty": {
        "theme_color": "#EC4899",
        "bot_icon_style": "preset_beauty_model",
        "bot_label": "뷰티봇 상담",
        "bot_name": "루나봇",
        "welcome_message": "안녕하세요! 뷰티&코스메틱 스킨케어 도우미입니다. 💄✨\n피부타입별 전성분 상담, 용기 누유/파손 사진 진단, 사용 중 트러블 접수 안내를 도와드립니다.",
        "quick_buttons": [
            "💄 피부고민별 맞춤 제품 추천",
            "🧪 전성분 & 임산부 안전 확인",
            "📸 용기 누유/파손 사진 판독",
            "🛡️ 트러블 접수 & 반품 문의",
            "💬 그 외 다른 질문하기",
        ],
        "contact_email": "beauty@cosmetic-mall.co.kr",
        "input_placeholder": "궁금한 성분명(예: 시카, 나이아신)이나 피부고민을 입력하세요...",
        "upload_guide": "💄 용기 누유/파손 및 트러블 사진 진단 접수",
        "default_policy": {
            "require_doctor_note_for_trouble": True,
            "unopened_seal_required_for_return": True,
            "leakage_auto_replacement": True,
        },
    },
    "fashion": {
        "theme_color": "#7C3AED",
        "bot_icon_style": "flaticon_shopping_bag",
        "bot_label": "패션봇 상담",
        "bot_name": "스타일봇",
        "welcome_message": "안녕하세요! 패션&의류 CS 고객센터입니다. 👗\n사이즈 추천, 맞교환 신청, 원단 오염/봉제 불량 사진 판독을 도와드립니다.",
        "quick_buttons": [
            "📐 체형별 사이즈 추천받기",
            "🔄 무료 사이즈 맞교환 신청",
            "📸 불량/오염 사진 판독 접수",
            "📦 주문 / 배송 현황 조회",
            "💬 그 외 다른 질문하기",
        ],
        "contact_email": "style@fashion-mall.co.kr",
        "input_placeholder": "상품명이나 사이즈 문의(또는 주문번호)를 입력하세요...",
        "upload_guide": "👗 원단 오염/봉제 불량 사진 교환 접수",
        "default_policy": {
            "max_exchange_days": 7,
            "free_exchange_for_defects": True,
        },
    },
    "fresh_food": {
        "theme_color": "#16A34A",
        "bot_icon_style": "flaticon_fresh_leaf",
        "bot_label": "신선봇 상담",
        "bot_name": "신선봇",
        "welcome_message": "안녕하세요! 식품·건강기능식품 AI 고객센터입니다. 🍎\n배송 조회, 보관법 및 신선도 변질/파손 사진 접수를 도와드립니다.",
        "quick_buttons": [
            "🍎 식품 보관법 & 섭취 안내",
            "📸 변질/파손 사진 환불 접수",
            "📦 주문 / 실시간 배송 조회",
            "🛡️ 48시간 100% 품질보상제",
            "💬 그 외 다른 질문하기",
        ],
        "contact_email": "fresh@market.co.kr",
        "input_placeholder": "궁금한 상품명이나 주문번호를 입력하세요...",
        "upload_guide": "📷 손상 상품 사진 업로드 접수",
        "default_policy": {
            "full_refund_damage_ratio": 30,
            "partial_refund_damage_ratio": 10,
            "max_claim_days": 2,
        },
    },
    "electronics": {
        "theme_color": "#1E40AF",
        "bot_icon_style": "flaticon_cute_robot",
        "bot_label": "테크봇 상담",
        "bot_name": "테크봇",
        "welcome_message": "안녕하세요! 리빙·가전·디지털 지능형 A/S 고객센터입니다. ⚡\n기기 작동 불량 자가진단, 고장 부위 사진 판독, 무상 A/S 수리 및 교환 접수를 도와드립니다.",
        "quick_buttons": [
            "⚡ 전원/작동 불량 자가진단",
            "🔧 고장/파손 사진 A/S 판독",
            "📦 주문 / 배송 현황 조회",
            "🛡️ 1년 무상 보증 규정 안내",
            "💬 그 외 다른 질문하기",
        ],
        "contact_email": "as@digital-center.co.kr",
        "input_placeholder": "증상(예: 전원불량)이나 모델명/주문번호를 입력하세요...",
        "upload_guide": "🔧 고장/파손 부위 사진 및 A/S 진단 요청",
        "default_policy": {
            "warranty_months": 12,
            "require_serial": True,
            "auto_repair_threshold_ratio": 20,
        },
    },
    "pet_supplies": {
        "theme_color": "#F97316",
        "bot_icon_style": "flaticon_cute_puppy",
        "bot_label": "펫봇 상담",
        "bot_name": "멍냥봇",
        "welcome_message": "안녕하세요! 반려동물 맞춤 케어 고객센터입니다. 🐶🐾\n우리 아이 연령/알러지별 사료·간식 추천, 사이즈 교환 및 파손 접수를 도와드립니다.",
        "quick_buttons": [
            "🐶 알러지/연령별 사료 추천",
            "📐 하네스/의류 사이즈 문의",
            "📸 포대 파손/불량 사진 접수",
            "📦 주문 / 정기배송 조회",
            "💬 그 외 다른 질문하기",
        ],
        "contact_email": "pet@petcare-mall.co.kr",
        "input_placeholder": "반려동물 견종/묘종이나 궁금한 상품명을 입력하세요...",
        "upload_guide": "🐾 사료 포대 파손 / 용품 불량 사진 접수",
        "default_policy": {"max_claim_days": 7},
    },
    "baby_kids": {
        "theme_color": "#F59E0B",
        "bot_icon_style": "flaticon_yellow_talk",
        "bot_label": "키즈봇 상담",
        "bot_name": "베베봇",
        "welcome_message": "안녕하세요! 유아동·출산·완구 안심 고객센터입니다. 👶🍼\n개월수별 맞춤 용품 추천, KC 안전인증 확인 및 교환/환불 접수를 도와드립니다.",
        "quick_buttons": [
            "👶 개월수별 맞춤 용품 추천",
            "🛡️ KC 안전인증 & 소재 확인",
            "📸 부품 누락/파손 사진 접수",
            "📦 주문 / 배송 현황 조회",
            "💬 그 외 다른 질문하기",
        ],
        "contact_email": "help@babykids.co.kr",
        "input_placeholder": "아이 개월수나 궁금한 육아용품명을 입력하세요...",
        "upload_guide": "🍼 유아용품 파손 / 부품 누락 사진 접수",
        "default_policy": {"max_claim_days": 7},
    },
    "sports_leisure": {
        "theme_color": "#059669",
        "bot_icon_style": "flaticon_shield_as",
        "bot_label": "레저봇 상담",
        "bot_name": "캠핑봇",
        "welcome_message": "안녕하세요! 스포츠·캠핑·아웃도어 고객센터입니다. ⛺⛳\n장비 스펙/호환 문의, 폴대·스킨 A/S 사진 진단 및 빠른 배송 조회를 도와드립니다.",
        "quick_buttons": [
            "⛺ 캠핑/스포츠 장비 스펙 문의",
            "🔧 장비 파손/A/S 사진 판독",
            "🔄 사이즈/옵션 교환 신청",
            "📦 주말 출고 / 배송 조회",
            "💬 그 외 다른 질문하기",
        ],
        "contact_email": "outdoor@sports-mall.co.kr",
        "input_placeholder": "장비 모델명이나 A/S/배송 문의를 입력하세요...",
        "upload_guide": "⛺ 장비 파손 / A/S 부위 사진 업로드 진단",
        "default_policy": {"max_claim_days": 14},
    },
    "medical_clinic": {
        "theme_color": "#0D9488",
        "bot_icon_style": "flaticon_derma_doctor",
        "bot_label": "진료/예약 상담",
        "bot_name": "메디봇",
        "welcome_message": "안녕하세요! 병원·클리닉 AI 진료 안내 데스크입니다. 🏥✨\n진료과목 및 시술 안내, 초진/재진 예약 문의, 오시는 길 및 증명서 발급 안내를 도와드립니다.",
        "quick_buttons": [
            "📅 진료/시술 예약 및 변경",
            "💉 주요 클리닉 & 비급여 안내",
            "🕒 진료시간 & 야간/주말 진료",
            "📍 오시는 길 & 주차 안내",
            "💬 원무과/상담실 연결 요청",
        ],
        "contact_email": "desk@clinic-center.co.kr",
        "input_placeholder": "증상, 희망 진료과목 또는 예약 문의사항을 입력하세요...",
        "upload_guide": "📸 환부 사진 / 처방전·서류 사전 업로드 상담",
        "default_policy": {"max_claim_days": 7},
    },
    "education_academy": {
        "theme_color": "#4F46E5",
        "bot_icon_style": "preset_sage_book",
        "bot_label": "입학/수강 상담",
        "bot_name": "에듀봇",
        "welcome_message": "안녕하세요! 교육·학원·온라인 클래스 AI 입학상담실입니다. 📚🎓\n레벨별 커리큘럼 추천, 수강료 및 시간표 안내, 무료 체험수업 신청을 도와드립니다.",
        "quick_buttons": [
            "🎓 수준별 맞춤 강의/반 추천",
            "🗓️ 개강 일정 & 시간표 조회",
            "💳 수강료 & 환불 규정 안내",
            "🎁 무료 레벨테스트/체험 신청",
            "💬 교육 상담사 연결 요청",
        ],
        "contact_email": "edu@academy-center.co.kr",
        "input_placeholder": "관심 과목/과정명이나 수강 문의를 입력하세요...",
        "upload_guide": "📄 성적표 / 과제 / 수강증빙 사진 업로드",
        "default_policy": {"max_claim_days": 7},
    },
    "professional_legal": {
        "theme_color": "#1E293B",
        "bot_icon_style": "flaticon_luxury_crown",
        "bot_label": "전문가 상담예약",
        "bot_name": "로앤봇",
        "welcome_message": "안녕하세요! 법률·세무·노무·컨설팅 전문 AI 비서입니다. ⚖️💼\n사건/업무 분야별 1:1 전문가 상담 예약, 필수 준비서류 및 수임 절차를 안내해 드립니다.",
        "quick_buttons": [
            "⚖️ 1:1 전문가 상담 예약하기",
            "📋 분야별 필요 서류 안내",
            "💰 자문/수임료 산정 기준",
            "🔒 비밀보장 & 진행 절차 안내",
            "💬 긴급 사건 담당자 직통 연결",
        ],
        "contact_email": "consult@law-tax.co.kr",
        "input_placeholder": "상담 희망 분야(예: 세무기장, 계약검토, 노무)를 입력하세요...",
        "upload_guide": "📄 관련 계약서 / 고지서 / 참고자료 사진 접수",
        "default_policy": {"max_claim_days": 7},
    },
    "interior_realestate": {
        "theme_color": "#B45309",
        "bot_icon_style": "flaticon_cat_butler",
        "bot_label": "견적/시공 상담",
        "bot_name": "하우징봇",
        "welcome_message": "안녕하세요! 인테리어·건축·부동산 AI 컨시어지입니다. 🏠✨\n평수별 가견적 산출, 포트폴리오 안내, 무료 방문 실측 예약 및 시공 후 A/S 접수를 도와드립니다.",
        "quick_buttons": [
            "📐 평수/공간별 무료 견적 문의",
            "🗓️ 방문 실측 & 상담 예약",
            "🖼️ 공간별 시공 포트폴리오",
            "🔧 시공 후 하자/A/S 사진 접수",
            "💬 전담 디자이너 연결 요청",
        ],
        "contact_email": "studio@interior-home.co.kr",
        "input_placeholder": "평수, 시공 희망 공간 또는 예산/일정을 입력하세요...",
        "upload_guide": "🏠 현장 사진 / 도면 / A/S 부위 사진 업로드",
        "default_policy": {"max_claim_days": 30},
    },
    "hotel_travel": {
        "theme_color": "#0284C7",
        "bot_icon_style": "flaticon_cat_butler",
        "bot_label": "컨시어지 상담",
        "bot_name": "스테이봇",
        "welcome_message": "안녕하세요! 호텔·펜션·스튜디오 AI 컨시어지입니다. 🏨🌴\n실시간 객실/스튜디오 예약 확인, 체크인·부대시설 안내, 주변 맛집 및 환불 규정을 안내해 드립니다.",
        "quick_buttons": [
            "🛏️ 객실/공간 예약 & 잔여 조회",
            "🕒 체크인/아웃 & 인원 규정",
            "🏊 바비큐/수영장 등 부대시설",
            "🔄 예약 변경 및 취소/환불 규정",
            "💬 프론트 데스크 연결 요청",
        ],
        "contact_email": "concierge@stay-resort.co.kr",
        "input_placeholder": "예약자 성함, 희망 날짜 또는 시설 문의를 입력하세요...",
        "upload_guide": "📸 객실 불편사항 / 분실물 사진 업로드 접수",
        "default_policy": {"max_claim_days": 7},
    },
    "it_corporate": {
        "theme_color": "#2563EB",
        "bot_icon_style": "flaticon_smart_ai",
        "bot_label": "도입/제휴 상담",
        "bot_name": "비즈봇",
        "welcome_message": "안녕하세요! 기업 공식 홈페이지·IT 솔루션 AI 매니저입니다. 🖥️🚀\n서비스 도입 및 요금제 안내, 기업 맞춤형 구축 견적, 기술 지원 및 제휴 문의를 도와드립니다.",
        "quick_buttons": [
            "🚀 솔루션 도입 & 무료 데모 신청",
            "💳 엔터프라이즈 요금제 안내",
            "🤝 비즈니스 제휴 / 제안 접수",
            "🛠️ 기술 지원 & 장애 문의",
            "💬 전담 매니저 미팅 요청",
        ],
        "contact_email": "biz@company-corp.com",
        "input_placeholder": "도입 문의, 요금제, 제휴 제안 등 궁금한 점을 입력하세요...",
        "upload_guide": "💻 오류 화면 캡처 / 제안서 이미지 업로드",
        "default_policy": {"max_claim_days": 14},
    },
    "restaurant_cafe": {
        "theme_color": "#DC2626",
        "bot_icon_style": "flaticon_bubble_bot",
        "bot_label": "예약/가맹 상담",
        "bot_name": "푸드봇",
        "welcome_message": "안녕하세요! 레스토랑·카페·프랜차이즈 AI 매니저입니다. 🍽️☕\n단체석 및 룸 예약, 시그니처 메뉴/알러지 안내, 주차 정보 및 가맹 창업을 상담해 드립니다.",
        "quick_buttons": [
            "🍽️ 단체석 / 룸 예약 문의",
            "📋 시그니처 메뉴 & 알러지 안내",
            "🚗 영업시간 & 주차장 안내",
            "🏪 프랜차이즈 가맹/창업 문의",
            "💬 매장 직통 연결 요청",
        ],
        "contact_email": "contact@fnb-brand.co.kr",
        "input_placeholder": "예약 인원/날짜, 메뉴 문의 또는 가맹 문의를 입력하세요...",
        "upload_guide": "📸 매장/메뉴 관련 사진 접수",
        "default_policy": {"max_claim_days": 3},
    },
    "general": {
        "theme_color": "#0D9488",
        "bot_icon_style": "flaticon_bubble_bot",
        "bot_label": "AI 상담톡",
        "bot_name": "상담봇",
        "welcome_message": "안녕하세요! 공식 홈페이지 AI 상담 도우미입니다. 💬\n서비스 이용 안내, 예약/견적 문의, 자주 묻는 질문 및 담당자 연결을 빠르고 정확하게 도와드립니다.",
        "quick_buttons": [
            "📌 주요 서비스 & 이용 안내",
            "💰 비용 / 견적 / 요금 문의",
            "📅 상담 예약 & 일정 확인",
            "📍 오시는 길 & 운영시간 안내",
            "💬 담당자 연결 / 기타 문의",
        ],
        "contact_email": "contact@mycompany.com",
        "input_placeholder": "궁금하신 내용이나 문의사항을 편하게 입력해 주세요...",
        "upload_guide": "📷 참고 사진 / 서류 이미지 업로드 접수",
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
                "서비스 이용 기간이 만료되었습니다. 연장 문의는 관리자에게 연락해 주세요.",
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
        try:
            q_buttons = json.loads(store.quick_buttons_json or "[]")
        except Exception:
            q_buttons = []
        if not q_buttons:
            ind_info = INDUSTRY_DEFAULTS.get(store.industry, INDUSTRY_DEFAULTS["general"])
            q_buttons = ind_info.get("quick_buttons", [])

        try:
            policy_dict = json.loads(store.policy_config_json or "{}")
        except Exception:
            policy_dict = {}
        comm_api = policy_dict.get("commerce_api", {}) if isinstance(policy_dict, dict) else {}
        comm_platform = comm_api.get("platform")
        comm_connected = bool(comm_platform and comm_platform != "none" and comm_api.get("client_key"))
        comm_uid = comm_api.get("store_uid")

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
            bot_icon_style=store.bot_icon_style or "flaticon_cute_robot",
            launcher_shape=store.launcher_shape or "cosbot_badge",
            bot_label=store.bot_label or "코스봇 상담",
            bot_name=store.bot_name or "코스봇",
            brand_badge=store.brand_badge or store.store_name[:8],
            header_title=store.header_title or "고객상담센터",
            chat_template=store.chat_template or "cosraw_grid",
            quick_buttons=q_buttons,
            contact_email=store.contact_email or "contact@cosrawfree.com",
            business_hours=store.business_hours or "평일 09:00~18:00",
            input_placeholder=store.input_placeholder or "궁금한 성분명이나 질문을 입력하세요...",
            bot_avatar_url=store.bot_avatar_url,
            commerce_platform=comm_platform,
            commerce_api_Connected=comm_connected,
            commerce_store_uid=comm_uid,
            direct_chat_url=f"/chat/{store.mall_id}",
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
        bot_name = request.bot_name or industry_info.get("bot_name", "상담봇")
        if request.welcome_message:
            welcome_message = request.welcome_message
        elif request.industry not in INDUSTRY_DEFAULTS and request.industry.strip():
            custom_ind = request.industry.strip()
            welcome_message = (
                f"안녕하세요! {request.store_name} ({custom_ind}) AI 상담사 '{bot_name}'입니다. ✨\n"
                f"궁금하신 서비스, 예약/견적 문의 또는 상담 내용을 편하게 말씀해 주세요!"
            )
        else:
            base_msg = industry_info["welcome_message"]
            second_line = base_msg.split("\n", 1)[1] if "\n" in base_msg else base_msg
            welcome_message = f"안녕하세요! {request.store_name} AI 상담사 '{bot_name}'입니다. ✨\n{second_line}"
        bot_icon_style = request.bot_icon_style or industry_info.get("bot_icon_style", "flaticon_cute_robot")
        bot_label = request.bot_label or industry_info.get("bot_label", f"{bot_name} 상담")
        brand_badge = request.brand_badge or request.store_name[:10]
        if request.quick_buttons:
            quick_buttons = request.quick_buttons
        elif request.industry not in INDUSTRY_DEFAULTS and request.industry.strip():
            custom_ind = request.industry.strip()
            quick_buttons = [
                f"📌 {custom_ind} 주요 안내",
                "💰 비용 / 견적 / 가격 문의",
                "📅 예약 / 신청 / 일정 확인",
                "📍 위치 / 운영시간 안내",
                "💬 담당자 연결 / 기타 문의",
            ]
        else:
            quick_buttons = industry_info.get("quick_buttons", [])
        contact_email = request.contact_email or industry_info.get("contact_email", "contact@cosrawfree.com")
        business_hours = request.business_hours or "평일 09:00~18:00"
        input_placeholder = request.input_placeholder or industry_info.get(
            "input_placeholder", "궁금한 성분명(예: 레티놀)이나 질문을 입력하세요..."
        )
        if request.bot_avatar_url:
            bot_icon_style = "custom_upload"

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
            bot_icon_style=bot_icon_style,
            launcher_shape=request.launcher_shape or "cosbot_badge",
            bot_label=bot_label,
            bot_name=bot_name,
            brand_badge=brand_badge,
            header_title=request.header_title or "고객상담센터",
            chat_template=request.chat_template or "cosraw_grid",
            quick_buttons_json=json.dumps(quick_buttons, ensure_ascii=False),
            contact_email=contact_email,
            business_hours=business_hours,
            input_placeholder=input_placeholder,
            bot_avatar_url=request.bot_avatar_url,
        )
        session.add(store)
        await session.commit()
        await session.refresh(store)

        # Persist Cafe24 API keys (encrypted) for live order lookup.
        # Only stores the keys -> status stays "pending" until the owner clicks
        # the Cafe24 "허용" button (OAuth). Blocked if ENCRYPTION_KEY is missing.
        await self._persist_commerce_keys(session, mall_id, merged_policy)

        return self._to_response(store)

    async def _persist_commerce_keys(
        self, session: AsyncSession, mall_id: str, policy: Dict[str, Any]
    ) -> None:
        """Encrypt & store Cafe24 client credentials from the showroom 5-step form."""
        comm = policy.get("commerce_api") if isinstance(policy, dict) else None
        if not isinstance(comm, dict) or comm.get("platform") != "cafe24":
            return
        cafe24_mall_id = (comm.get("store_uid") or "").strip()
        client_id = (comm.get("client_key") or "").strip()
        client_secret = (comm.get("client_secret") or "").strip()
        if not (cafe24_mall_id and client_id and client_secret):
            return
        if not encryption_available():
            logger.warning(
                f"[Commerce] ENCRYPTION_KEY missing; Cafe24 keys NOT saved for mall={mall_id}."
            )
            return
        try:
            await commerce_service.save_keys(
                session, mall_id, cafe24_mall_id, client_id, client_secret
            )
        except Exception as e:
            logger.error(f"[Commerce] Failed to save Cafe24 keys for mall={mall_id}: {e}")

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

        if update_req.bot_icon_style is not None:
            store.bot_icon_style = update_req.bot_icon_style

        if update_req.launcher_shape is not None:
            store.launcher_shape = update_req.launcher_shape

        if update_req.bot_label is not None:
            store.bot_label = update_req.bot_label

        if update_req.bot_name is not None:
            store.bot_name = update_req.bot_name

        if update_req.brand_badge is not None:
            store.brand_badge = update_req.brand_badge

        if update_req.header_title is not None:
            store.header_title = update_req.header_title

        if update_req.chat_template is not None:
            store.chat_template = update_req.chat_template

        if update_req.quick_buttons is not None:
            store.quick_buttons_json = json.dumps(update_req.quick_buttons, ensure_ascii=False)

        if update_req.contact_email is not None:
            store.contact_email = update_req.contact_email

        if update_req.business_hours is not None:
            store.business_hours = update_req.business_hours

        if update_req.input_placeholder is not None:
            store.input_placeholder = update_req.input_placeholder

        if update_req.bot_avatar_url is not None:
            store.bot_avatar_url = update_req.bot_avatar_url
            if update_req.bot_avatar_url and not update_req.bot_icon_style:
                store.bot_icon_style = "custom_upload"

        if update_req.reset_days is not None:
            store.trial_days = update_req.reset_days
            if update_req.reset_days == 0:
                store.expires_at = now - timedelta(seconds=10)
            else:
                store.expires_at = now + timedelta(days=update_req.reset_days)
            store.is_active = True
            if update_req.plan_type is None and store.plan_type in ("unlimited", "suspended"):
                store.plan_type = "active"

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
            if store.plan_type in ("suspended", "unlimited"):
                store.plan_type = update_req.plan_type or "active"

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

    async def _fetch_html(self, url: str, timeout: float = 10.0) -> str:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "ChatbotFactoryBot/2.0 (+https://railway.app)"},
            )
            resp.raise_for_status()
            return resp.text

    def _discover_product_urls(self, html_text: str, base_url: str) -> List[str]:
        parsed_base = urlparse(base_url)
        host = parsed_base.netloc.lower()
        if not host:
            return []

        hrefs = re.findall(r'href\s*=\s*["\']([^"\']+)["\']', html_text, re.IGNORECASE)
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", html_text, re.IGNORECASE)
        candidates = hrefs + locs

        product_signals = (
            "product", "goods", "item", "detail", "view", "shop_view",
            "/p/", "product_no", "productno", "goods_no", "goodsno",
        )
        skip_signals = (
            "cart", "checkout", "login", "register", "account", "myshop",
            "category", "search", "board", "notice", "faq", "policy",
            "about", "contact", "sitemap", "javascript:", "mailto:", "tel:", "#",
        )

        seen = set()
        result = []
        for raw in candidates:
            raw = raw.strip()
            if not raw:
                continue
            if raw.startswith("//"):
                raw = parsed_base.scheme + ":" + raw
            elif raw.startswith("/"):
                raw = parsed_base.scheme + "://" + host + raw
            elif not raw.startswith("http"):
                raw = parsed_base.scheme + "://" + host + "/" + raw.lstrip("./")
            try:
                p = urlparse(raw)
            except Exception:
                continue
            if p.netloc.lower() != host:
                continue
            low = (p.path + "?" + p.query).lower()
            if any(s in low for s in skip_signals):
                continue
            if not any(s in low for s in product_signals):
                continue
            clean = p._replace(fragment="").geturl()
            if clean in seen:
                continue
            seen.add(clean)
            result.append(clean)
            if len(result) >= 200:
                break
        return result

    async def crawl_store_catalog(
        self,
        session: AsyncSession,
        mall_id: str,
        crawl_req: "StoreCatalogCrawlRequest",
    ) -> "StoreCatalogCrawlResponse":
        from app.schemas.store import StoreCatalogCrawlResponse, StoreKnowledgeResponse

        raw_html = crawl_req.raw_html_override
        if not raw_html:
            try:
                raw_html = await self._fetch_html(crawl_req.url)
            except Exception as e:
                logger.warning("[CatalogCrawl] Failed to fetch %s: %s", crawl_req.url, e)
                return StoreCatalogCrawlResponse(
                    discovered=0,
                    learned=0,
                    skipped_duplicates=0,
                    failed=0,
                    items=[],
                    notes="목록 페이지를 가져오지 못했습니다: " + str(e),
                )

        urls = self._discover_product_urls(raw_html, crawl_req.url)

        if len(urls) < 3:
            try:
                parsed = urlparse(crawl_req.url)
                sitemap_url = parsed.scheme + "://" + parsed.netloc + "/sitemap.xml"
                sm_html = await self._fetch_html(sitemap_url)
                for u in self._discover_product_urls(sm_html, sitemap_url):
                    if u not in urls:
                        urls.append(u)
            except Exception:
                pass

        max_products = max(1, min(50, crawl_req.max_products or 20))
        urls = urls[: max_products * 2]

        existing_res = await session.execute(
            select(StoreKnowledgeModel.source_url).where(
                StoreKnowledgeModel.mall_id == mall_id
            )
        )
        existing = {r[0] for r in existing_res.all() if r[0]}

        learned_items = []
        skipped = 0
        failed = 0
        discovered = len(urls)
        for u in urls:
            if len(learned_items) >= max_products:
                break
            if u in existing:
                skipped += 1
                continue
            try:
                html_text = await self._fetch_html(u)
            except Exception as e:
                logger.warning("[CatalogCrawl] Fetch failed for %s: %s", u, e)
                failed += 1
                continue
            try:
                from app.schemas.store import StoreKnowledgeCrawlRequest
                single_req = StoreKnowledgeCrawlRequest(url=u, tags=crawl_req.tags)
                # reuse the single-product crawler (fetches+extracts+saves)
                resp = await self.crawl_and_learn_url(session, mall_id, single_req)
                learned_items.append(resp)
                existing.add(u)
            except Exception as e:
                logger.warning("[CatalogCrawl] Parse/save failed for %s: %s", u, e)
                failed += 1

        if discovered == 0:
            notes = (
                "상품 링크를 찾지 못했습니다. 카테고리/목록 페이지 URL을 넣거나, "
                "사이트맵(sitemap.xml) 주소를 직접 입력해 주세요. "
                "JavaScript로만 렌더링되는 스토어(쿠팡/네이버 스마트스토어)는 "
                "현재 자동 수집이 제한됩니다."
            )
        else:
            notes = (
                "총 " + str(discovered) + "개 상품 링크를 발견했고, "
                + str(len(learned_items)) + "개를 새로 학습했습니다. "
                "(중복 " + str(skipped) + "개 건너뜀, 실패 " + str(failed) + "개)"
            )

        return StoreCatalogCrawlResponse(
            discovered=discovered,
            learned=len(learned_items),
            skipped_duplicates=skipped,
            failed=failed,
            items=learned_items,
            notes=notes,
        )

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
