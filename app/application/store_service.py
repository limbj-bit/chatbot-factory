import html
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse
import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer
from app.application.commerce_service import commerce_service
from app.application.first_screen import (
    merge_first_screen_into_policy,
    merge_teaser_into_policy,
    read_first_screen,
    read_teaser,
)
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
        "welcome_message": "안녕하세요, 원료/B2B AI 상담사입니다. 🧪\n\n성분 규격, COA/MSDS 조회, 원료 장터 이용, 제조사 등록까지 — B2B 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 뷰티&코스메틱 AI 상담사입니다. ✨\n\n피부타입별 맞춤 전성분 상담, 용기 누유·파손 사진 진단, 사용 중 트러블 접수까지 — 뷰티 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
        "quick_buttons": [
            "✨ 피부타입별\n맞춤 상품 추천",
            "🌿 전성분 &\n임산부 안전 성분",
            "📸 파손·불량\n사진 진단",
            "💬 트러블 접수\n& 반품 문의",
            "❓ 다른 질문하기",
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
        "welcome_message": "안녕하세요, 패션 AI 상담사입니다. 👗\n\n사이즈 추천, 코디 상담, 교환·반품 접수, 배송 조회까지 — 패션 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 식품 전문 AI 상담사입니다. 🍎\n\n신선도 유지법, 보관 방법, 배송 일정, 성분·알레르기 정보까지 — 식품 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 전자/가전 AI 상담사입니다. ⚡\n\n제품 사용법, 고장 진단, A/S 접수, 배송·반품 안내까지 — 전자 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 반려동물 AI 상담사입니다. 🐶\n\n맞춤 사료·간식 추천, 건강 상담, 배송·교환 안내까지 — 펫 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 유아동 AI 상담사입니다. 👶\n\n월령별 맞춤 상품 추천, KC 안전 인증 확인, 교환·환불 안내까지 — 유아동 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 스포츠·캠핑 AI 상담사입니다. ⛺\n\n장비 스펙·호환 문의, A/S 사진 진단, 빠른 배송 조회까지 — 스포츠 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 병원·클리닉 AI 상담사입니다. 🏥\n\n진료과목 및 시술 안내, 초진·재진 예약 문의, 진료비·증명서 발급 안내까지 — 의료 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 교육·학원 AI 상담사입니다. 📚\n\n레벨별 커리큘럼 추천, 수강료·시간표 안내, 무료 체험 신청까지 — 교육 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 전문직 AI 상담사입니다. ⚖️\n\n법률·세무·노무·컨설팅 상담 예약, 수임료 안내, 서류 발급 안내까지 — 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 인테리어·건축 AI 상담사입니다. 🏠\n\n무료 견적 산출, 현장 방문 예약, 자재·시공 안내, A/S 접수까지 — 건축 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 호텔·숙박 AI 상담사입니다. 🏨\n\n객실 예약, 요금 안내, 부대시설 이용, 불편 접수까지 — 숙박 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, IT/SaaS AI 상담사입니다. 🖥️\n\n서비스 이용 안내, 요금제 문의, 기술 지원, 도입 상담까지 — IT 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, 레스토랑·카페 AI 상담사입니다. 🍽️\n\n메뉴 안내, 예약, 배달·포장 주문, 영업시간 문의까지 — F&B 전문 AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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
        "welcome_message": "안녕하세요, AI 상담사입니다. ✨\n\n상품 추천, 배송 조회, 반품·교환 안내, 사용법 상담까지 — AI가 빠르고 정확하게 도와드립니다.\n\n궁금한 점을 편하게 말씀해 주세요. 😊",
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

    _CATALOG_CACHE_TTL_SEC = 2 * 3600

    def __init__(self) -> None:
        # mall_id|seed_url → {urls, created_at, sitemap_count, category_count}
        self._catalog_url_cache: Dict[str, Dict[str, Any]] = {}

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
        widget_layout = (
            policy_dict.get("widget_layout")
            if isinstance(policy_dict, dict)
            else None
        )
        if not isinstance(widget_layout, dict):
            widget_layout = None

        _pol = policy_dict if isinstance(policy_dict, dict) else {}
        fs = read_first_screen(_pol, store.welcome_message or "")
        teaser = read_teaser(
            _pol,
            industry=store.industry or "general",
            bot_name=store.bot_name or "상담봇",
        )

        return StoreResponse(
            store_id=store.id,
            mall_id=store.mall_id,
            store_name=store.store_name,
            industry=store.industry,
            theme_color=store.theme_color,
            welcome_message=store.welcome_message,
            welcome_bubbles=fs["bubbles"],
            bubble_first_delay_ms=fs["first_delay_ms"],
            bubble_gap_ms=fs["bubble_gap_ms"],
            teaser_prompts=teaser["prompts"],
            teaser_first_delay_ms=teaser["first_delay_ms"],
            teaser_visible_ms=teaser["visible_ms"],
            teaser_gap_ms=teaser["gap_ms"],
            teaser_max_shows=teaser["max_shows"],
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
            business_hours=store.business_hours or "365일 24시간",
            input_placeholder=store.input_placeholder or "궁금한 성분명이나 질문을 입력하세요...",
            bot_avatar_url=store.bot_avatar_url,
            brand_logo_url=self._safe_brand_logo_url(store),
            widget_layout=widget_layout,
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

        # UPSERT: if a store with this mall_id already exists, update its
        # branding/policy fields instead of failing on the unique constraint.
        # This lets the showroom act as the AS (after-sales) tool: re-generate
        # with the same mall_id and the embed script never needs re-install.
        existing_store = await self.get_store_by_mall_id(session, mall_id)
        if existing_store is not None:
            existing_store.store_name = request.store_name
            existing_store.industry = request.industry
            if request.theme_color:
                existing_store.theme_color = request.theme_color
            if request.welcome_message:
                wm = request.welcome_message
                if request.bot_name and request.bot_name.encode() not in wm.encode():
                    wm = wm.replace("AI 상담사입니다", "AI 상담사(" + request.bot_name + ")입니다", 1)
                existing_store.welcome_message = wm
            if request.contact_email:
                existing_store.contact_email = request.contact_email
            if request.business_hours:
                existing_store.business_hours = request.business_hours
            if request.bot_name:
                existing_store.bot_name = request.bot_name
            if request.brand_badge:
                existing_store.brand_badge = request.brand_badge
            if request.header_title:
                existing_store.header_title = request.header_title
            if request.bot_icon_style:
                existing_store.bot_icon_style = request.bot_icon_style
            if request.launcher_shape:
                existing_store.launcher_shape = request.launcher_shape
            if request.bot_label:
                existing_store.bot_label = request.bot_label
            if request.chat_template:
                existing_store.chat_template = request.chat_template
            if request.quick_buttons:
                existing_store.quick_buttons_json = json.dumps(request.quick_buttons, ensure_ascii=False)
            if request.input_placeholder:
                existing_store.input_placeholder = request.input_placeholder
            if request.bot_avatar_url:
                from app.infrastructure.avatar_compress import (
                    HARD_RECOMPRESS_ABOVE,
                    compress_avatar_data_uri,
                )

                av = request.bot_avatar_url
                if av.startswith("data:") and len(av) > HARD_RECOMPRESS_ABOVE:
                    av = compress_avatar_data_uri(av, force=True) or av
                existing_store.bot_avatar_url = av
                if not request.bot_icon_style:
                    existing_store.bot_icon_style = "custom_upload"
            if request.brand_logo_url is not None:
                if request.brand_logo_url == "":
                    existing_store.brand_logo_url = None
                else:
                    existing_store.brand_logo_url = request.brand_logo_url
            if request.allowed_domains is not None:
                existing_store.allowed_domains = request.allowed_domains
            if request.webhook_url is not None:
                existing_store.webhook_url = request.webhook_url
            if request.daily_quota_limit is not None:
                existing_store.daily_quota_limit = request.daily_quota_limit
            try:
                merged = json.loads(existing_store.policy_config_json or "{}")
            except Exception:
                merged = {}
            if request.policy_config:
                merged.update(request.policy_config)
            if (
                request.welcome_bubbles is not None
                or request.bubble_first_delay_ms is not None
                or request.bubble_gap_ms is not None
            ):
                merged, joined = merge_first_screen_into_policy(
                    merged,
                    bubbles=request.welcome_bubbles,
                    first_delay_ms=request.bubble_first_delay_ms,
                    bubble_gap_ms=request.bubble_gap_ms,
                )
                if request.welcome_bubbles is not None:
                    existing_store.welcome_message = joined
            if (
                request.teaser_prompts is not None
                or request.teaser_first_delay_ms is not None
                or request.teaser_visible_ms is not None
                or request.teaser_gap_ms is not None
                or request.teaser_max_shows is not None
            ):
                merged = merge_teaser_into_policy(
                    merged,
                    prompts=request.teaser_prompts,
                    first_delay_ms=request.teaser_first_delay_ms,
                    visible_ms=request.teaser_visible_ms,
                    gap_ms=request.teaser_gap_ms,
                    max_shows=request.teaser_max_shows,
                )
            existing_store.policy_config_json = json.dumps(merged, ensure_ascii=False)
            await session.commit()
            await session.refresh(existing_store)
            return self._to_response(existing_store)

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
        business_hours = request.business_hours or "365일 24시간"
        input_placeholder = request.input_placeholder or industry_info.get(
            "input_placeholder", "궁금한 성분명(예: 레티놀)이나 질문을 입력하세요..."
        )
        saved_avatar_url = None
        if request.bot_avatar_url:
            from app.infrastructure.avatar_compress import (
                HARD_RECOMPRESS_ABOVE,
                compress_avatar_data_uri,
            )

            bot_icon_style = "custom_upload"
            av = request.bot_avatar_url
            if av.startswith("data:") and len(av) > HARD_RECOMPRESS_ABOVE:
                av = compress_avatar_data_uri(av, force=True) or av
            saved_avatar_url = av

        merged_policy = industry_info["default_policy"].copy()
        if request.policy_config:
            merged_policy.update(request.policy_config)
        if (
            request.welcome_bubbles is not None
            or request.bubble_first_delay_ms is not None
            or request.bubble_gap_ms is not None
        ):
            default_bubbles = request.welcome_bubbles
            if default_bubbles is None:
                from app.application.first_screen import split_welcome_to_bubbles

                default_bubbles = split_welcome_to_bubbles(welcome_message)
            merged_policy, welcome_message = merge_first_screen_into_policy(
                merged_policy,
                bubbles=default_bubbles,
                first_delay_ms=request.bubble_first_delay_ms
                if request.bubble_first_delay_ms is not None
                else 0,
                bubble_gap_ms=request.bubble_gap_ms
                if request.bubble_gap_ms is not None
                else 450,
            )
        if (
            request.teaser_prompts is not None
            or request.teaser_first_delay_ms is not None
            or request.teaser_visible_ms is not None
            or request.teaser_gap_ms is not None
            or request.teaser_max_shows is not None
        ):
            merged_policy = merge_teaser_into_policy(
                merged_policy,
                prompts=request.teaser_prompts,
                first_delay_ms=request.teaser_first_delay_ms,
                visible_ms=request.teaser_visible_ms,
                gap_ms=request.teaser_gap_ms,
                max_shows=request.teaser_max_shows,
            )

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
            bot_avatar_url=saved_avatar_url,
            brand_logo_url=request.brand_logo_url or None,
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
            from app.infrastructure.avatar_compress import (
                HARD_RECOMPRESS_ABOVE,
                compress_avatar_data_uri,
            )

            av = update_req.bot_avatar_url
            if av == "":
                store.bot_avatar_url = None
            else:
                if av.startswith("data:") and len(av) > HARD_RECOMPRESS_ABOVE:
                    av = compress_avatar_data_uri(av, force=True) or av
                store.bot_avatar_url = av
                if not update_req.bot_icon_style:
                    store.bot_icon_style = "custom_upload"

        if update_req.brand_logo_url is not None:
            from app.infrastructure.avatar_compress import (
                HARD_RECOMPRESS_ABOVE,
                compress_avatar_data_uri,
                compress_logo_bytes,
                bytes_to_data_uri,
            )
            import base64 as _b64

            logo = update_req.brand_logo_url
            if logo == "":
                store.brand_logo_url = None
            elif logo.startswith("data:") and len(logo) > HARD_RECOMPRESS_ABOVE:
                try:
                    comma = logo.find(",")
                    raw = _b64.b64decode(logo[comma + 1 :], validate=False)
                    data, mime = compress_logo_bytes(raw)
                    store.brand_logo_url = bytes_to_data_uri(data, mime)
                except Exception:
                    store.brand_logo_url = compress_avatar_data_uri(logo, force=True) or logo
            else:
                store.brand_logo_url = logo

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

        teaser_touched = (
            update_req.teaser_prompts is not None
            or update_req.teaser_first_delay_ms is not None
            or update_req.teaser_visible_ms is not None
            or update_req.teaser_gap_ms is not None
            or update_req.teaser_max_shows is not None
        )
        if (
            update_req.welcome_bubbles is not None
            or update_req.bubble_first_delay_ms is not None
            or update_req.bubble_gap_ms is not None
            or teaser_touched
        ):
            try:
                pol = json.loads(store.policy_config_json or "{}")
            except Exception:
                pol = {}
            if (
                update_req.welcome_bubbles is not None
                or update_req.bubble_first_delay_ms is not None
                or update_req.bubble_gap_ms is not None
            ):
                pol, joined = merge_first_screen_into_policy(
                    pol,
                    bubbles=update_req.welcome_bubbles,
                    first_delay_ms=update_req.bubble_first_delay_ms,
                    bubble_gap_ms=update_req.bubble_gap_ms,
                )
                if update_req.welcome_bubbles is not None:
                    store.welcome_message = joined
            if teaser_touched:
                pol = merge_teaser_into_policy(
                    pol,
                    prompts=update_req.teaser_prompts,
                    first_delay_ms=update_req.teaser_first_delay_ms,
                    visible_ms=update_req.teaser_visible_ms,
                    gap_ms=update_req.teaser_gap_ms,
                    max_shows=update_req.teaser_max_shows,
                )
            store.policy_config_json = json.dumps(pol, ensure_ascii=False)

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
            original_price=req.original_price,
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
            original_price=getattr(doc, "original_price", None),
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

        # ---- Structured data first: JSON-LD (Cafe24 emits ProductGroup/Product) ----
        jsonld_data = None
        jsonld_match = re.search(
            r'<script type=["\']application/ld\+json["\']>([\s\S]*?)</script>',
            raw_html,
            re.IGNORECASE,
        )
        if jsonld_match:
            try:
                parsed = json.loads(jsonld_match.group(1))
                if isinstance(parsed, dict):
                    jsonld_data = parsed
            except Exception:
                jsonld_data = None

        # Title: ProductGroup.name (clean) → variant name → og:title → <title>
        title = None
        if jsonld_data:
            if jsonld_data.get("@type") == "ProductGroup":
                gname = (jsonld_data.get("name") or "").strip()
                variants = jsonld_data.get("hasVariant") or []
                vname = ((variants[0] or {}).get("name") or "").strip() if variants else ""
                # Cafe24 variant names repeat the group name — keep only the suffix
                if vname and gname and vname.startswith(gname):
                    vname = vname[len(gname):].strip()
                title = html.unescape(vname or gname)
            elif jsonld_data.get("@type") == "Product" and jsonld_data.get("name"):
                title = html.unescape(str(jsonld_data["name"]).strip())
        if not title:
            og_titles = re.findall(
                r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']',
                raw_html,
                re.IGNORECASE,
            )
            title = html.unescape(og_titles[-1].strip()) if og_titles else None
        if not title:
            title_match = re.search(r"<title>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
            title = html.unescape(title_match.group(1).strip()) if title_match else crawl_req.url

        # ---- Price: sale + list (skip shipping/point; reject store delivery_fee) ----
        # Live crawl: Cafe24 Front API (if client_id set) → Playwright JS render.
        # raw_html_override (tests/fixtures): static extract only — no network enrich.
        from app.application.product_price_extract import (
            extract_product_image_url,
            extract_product_prices,
            reject_price_set,
        )
        from app.application.product_price_enrich import enrich_product_prices

        reject_prices = set()
        try:
            store_row = await self.get_store_by_mall_id(session, mall_id)
            pol = {}
            if store_row and store_row.policy_config_json:
                pol = json.loads(store_row.policy_config_json or "{}") or {}
            ship = pol.get("shipping_policy") if isinstance(pol, dict) else {}
            ship = ship if isinstance(ship, dict) else {}
            reject_prices = reject_price_set(
                ship.get("delivery_fee"), ship.get("free_over_amount")
            )
        except Exception:
            reject_prices = set()

        if crawl_req.raw_html_override:
            price_info = extract_product_prices(
                raw_html, jsonld_data, reject_prices=reject_prices
            )
            price_source = "static_override"
        else:
            price_info, raw_html, price_source = await enrich_product_prices(
                crawl_req.url,
                raw_html,
                jsonld_data,
                reject_prices=reject_prices,
            )
        price = price_info.price
        original_price = price_info.original_price
        if price_source not in ("static", "static_override"):
            logger.info(
                "[crawl] price enriched via %s mall_id=%s url=%s price=%s",
                price_source,
                mall_id,
                crawl_req.url,
                price,
            )

        # ---- Image: Cafe24 bigImage → JSON-LD/extruct → og:image ----
        image_url = extract_product_image_url(raw_html)
        if not image_url and jsonld_data:
            imgs = jsonld_data.get("image")
            if isinstance(imgs, list) and imgs and isinstance(imgs[0], str):
                image_url = imgs[0].strip()
            elif isinstance(imgs, str) and imgs.strip():
                image_url = imgs.strip()

        # ---- Content: HTML comments first (Cafe24 leaves "-->" template debris), ----
        # then strip script/style, tags, and common navigation boilerplate.
        cleaned = re.sub(r"<!--[\s\S]*?-->", " ", raw_html)  # HTML comments incl. {#title} blocks
        cleaned = re.sub(r"<(script|style|noscript)[^>]*>[\s\S]*?</\1>", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"\{#[a-zA-Z_]+\}", " ", cleaned)  # leftover {#title} tokens
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        for _n in ['브랜드소개', '제품구매', '특가판매', '알뜰장터', '제품소개서', '이벤트', '공지사항', '문의하기', '회사소개', '로그인', 'About SHOP', '기능별', '탄력/주름개선', '수분/보습', '민감/진정', '영양', '미백/톤업', '지성/트러블', '모공/피지', '기미/잡티', '라인별', '스킨케어', '클린징', '마사지 오일', '세럼/에센스/앰플', '크림', '바디', '모델링팩/마스크', '이너뷰티', '메이크업/자외선 차단', '덴탈/두피', '소모품', '오뜨엘라', '전신마사지젤', 'Event Community', '상품 리뷰', 'FAQ', 'Join Order', '현재 위치', '홈 SHOP', '추천메일 보내기', '상품조르기', '대량구매문의', '리뷰']:
            cleaned = cleaned.replace(_n, " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # ---- Structured spec table (Cafe24 상품요약정보): "용량: 25ml x 100ea" etc. ----
        spec_parts: list = []
        spec_idx = raw_html.find("상품요약정보")
        if spec_idx > -1:
            spec_html = raw_html[spec_idx:spec_idx + 3000]
            for row in re.finditer(
                r"<th[^>]*>([\s\S]*?)</th>\s*<td[^>]*>([\s\S]*?)</td>", spec_html
            ):
                k = re.sub(r"<[^>]+>", "", row.group(1)).strip()
                v = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row.group(2)))).strip()
                if k and v and len(k) < 30 and len(v) < 200:
                    spec_parts.append(f"{k}: {v}")

        # ---- Product description from #prdDetail, cut before the payment/shipping ----
        # boilerplate that is identical on every page of the store.
        desc = ""
        detail_idx = raw_html.find('id="prdDetail"')
        if detail_idx == -1:
            detail_idx = raw_html.find("id='prdDetail'")
        if detail_idx > -1:
            # Start from the opening tag so tag-stripping removes it too
            tag_start = raw_html.rfind("<div", max(0, detail_idx - 200), detail_idx)
            detail_html = raw_html[tag_start if tag_start > -1 else detail_idx:detail_idx + 30000]
            for marker in ("상품결제정보", "배송정보", "교환 및 반품", "교환반품", "환불안내"):
                cut = detail_html.find(marker)
                if cut > 500:  # keep the description that precedes the boilerplate
                    detail_html = detail_html[:cut]
                    break
            d = re.sub(r"<!--[\s\S]*?-->", " ", detail_html)
            d = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", d, flags=re.IGNORECASE)
            d = re.sub(r"<img[^>]*>", " ", d)
            d = re.sub(r"<[^>]+>", " ", d)
            d = html.unescape(re.sub(r"\s+", " ", d)).strip()
            d = re.sub(r"\[\s*\]", " ", d)  # "[ ]" lazy-image placeholders
            # Strip mobile sticky-nav / option-table boilerplate that bleeds in
            for _n in (
                "멤버십 혜택을 누려보세요", "해외배송 가능상품", "기본 정보", "상품요약정보",
                "주기결제", "구매방법", "구매하기", "보기 ", "상품명", "리뷰",
            ):
                d = d.replace(_n, " ")
            d = re.sub(r"\s+", " ", d).strip()
            # Keep only if it carries real prose (image-only detail pages yield junk)
            if len(d) >= 80 and not d.startswith(("상품결제정보", "배송정보")):
                desc = d[:1500]

        # ---- Ingredient line (전성분) if present in text ----
        ingredient_snip = ""
        ing_m = re.search(r"전성분[:\s]{1,5}([^\n]{10,500})", cleaned)
        if ing_m:
            ingredient_snip = "전성분: " + ing_m.group(1).strip()[:400]

        # Assemble: title + specs + ingredients + description. When a store page
        # has no #prdDetail (simple landing pages, test fixtures), fall back to
        # the cleaned body text — but only if it survived junk filtering and
        # carries real sentences (Cafe24 nav/banner debris fails this check).
        content_bits = [title]
        if price_info.on_sale and price and original_price:
            pct = price_info.discount_percent or 0
            content_bits.append(
                f"판매가: {price:,}원 (정상가 {original_price:,}원, {pct}% 할인 중)"
            )
        elif price:
            content_bits.append(f"판매가: {price:,}원")
        if spec_parts:
            content_bits.append(" | ".join(spec_parts))
        if ingredient_snip:
            content_bits.append(ingredient_snip)
        if desc:
            content_bits.append(desc)
        if not desc and len(cleaned) >= 60:
            # Drop leading repeated title and nav leftovers, keep real prose
            fallback = cleaned
            if fallback.startswith(title):
                fallback = fallback[len(title):].strip(" .:|")
            junk_tokens = ("[ ]", "멤버십 혜택", "구매하기", "보기 ", "해외배송 가능상품", "상품요약정보")
            if not any(t in fallback[:200] for t in junk_tokens) or "전성분" in fallback:
                content_bits.append(fallback[:600])
        summary_content = ". ".join(b for b in content_bits if b)[:1800]

        create_req = StoreKnowledgeCreateRequest(
            doc_type="crawled_url",
            title=title[:256],
            content=summary_content,
            price=price,
            original_price=original_price,
            purchase_url=crawl_req.url,
            image_url=image_url,
            tags=crawl_req.tags,
        )
        # Update existing entry if same URL already learned
        existing_res = await session.execute(
            select(StoreKnowledgeModel).where(
                StoreKnowledgeModel.mall_id == mall_id,
                StoreKnowledgeModel.source_url == crawl_req.url,
            )
        )
        existing_doc = existing_res.scalar_one_or_none()
        if existing_doc:
            existing_doc.title = create_req.title[:256]
            existing_doc.content = create_req.content
            existing_doc.price = create_req.price
            existing_doc.original_price = create_req.original_price
            existing_doc.purchase_url = create_req.purchase_url or crawl_req.url
            existing_doc.image_url = create_req.image_url
            existing_doc.tags = create_req.tags
            await session.commit()
            await session.refresh(existing_doc)
            return StoreKnowledgeResponse(
                id=existing_doc.id,
                mall_id=existing_doc.mall_id,
                doc_type=existing_doc.doc_type,
                title=existing_doc.title,
                content=existing_doc.content,
                source_url=existing_doc.source_url,
                price=existing_doc.price,
                original_price=getattr(existing_doc, "original_price", None),
                purchase_url=existing_doc.purchase_url,
                image_url=existing_doc.image_url,
                tags=existing_doc.tags,
                created_at=existing_doc.created_at.isoformat(),
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
            has_product = any(s in low for s in product_signals)
            has_skip = any(s in low for s in skip_signals)
            if has_skip and not has_product:
                continue
            if not has_product:
                continue
            clean = p._replace(fragment="").geturl()
            if clean in seen:
                continue
            seen.add(clean)
            result.append(clean)
            if len(result) >= 5000:
                break
        return result

    async def _deep_discover_product_urls(self, start_url: str, max_urls: int = 5000) -> List[str]:
        """BFS crawl from start_url: follow internal links and collect product URLs."""
        parsed_start = urlparse(start_url)
        host = parsed_start.netloc.lower()
        if not host:
            return []
        visited = set()
        queue = [start_url]
        product_urls = []
        product_seen = set()
        skip_signals = (
            "cart", "checkout", "login", "register", "account", "myshop",
            "search", "board", "notice", "faq", "policy",
            "about", "contact", "sitemap", "javascript:", "mailto:", "tel:", "#",
        )
        product_signals = (
            "product", "goods", "item", "detail", "view", "shop_view",
            "/p/", "product_no", "productno", "goods_no", "goodsno",
        )
        listing_signals = ("category", "list", "shop", "goods_list", "product_list")
        page_count = 0
        max_pages = 20
        while queue and page_count < max_pages and len(product_urls) < max_urls:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            page_count += 1
            try:
                html = await self._fetch_html(url, timeout=5.0)
            except Exception:
                continue
            # Extract product URLs from this page
            hrefs = re.findall(r'href\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
            locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", html, re.IGNORECASE)
            for raw in hrefs + locs:
                raw = raw.strip()
                if not raw:
                    continue
                if raw.startswith("//"):
                    raw = parsed_start.scheme + ":" + raw
                elif raw.startswith("/"):
                    raw = parsed_start.scheme + "://" + host + raw
                elif not raw.startswith("http"):
                    raw = parsed_start.scheme + "://" + host + "/" + raw.lstrip("./")
                try:
                    p = urlparse(raw)
                except Exception:
                    continue
                if p.netloc.lower() != host:
                    continue
                low = (p.path + "?" + p.query).lower()
                has_product = any(s in low for s in product_signals)
                has_skip = any(s in low for s in skip_signals)
                if has_skip and not has_product:
                    continue
                clean = p._replace(fragment="").geturl()
                if has_product:
                    if clean not in product_seen:
                        product_seen.add(clean)
                        product_urls.append(clean)
                        if len(product_urls) >= max_urls:
                            break
                elif any(s in low for s in listing_signals):
                    if clean not in visited and clean not in queue:
                        queue.append(clean)
            # Also try pagination
            for pn in range(2, 6):
                paginated = url.split("?")[0] + "?page=" + str(pn)
                if paginated not in visited and paginated not in queue:
                    # Only add if original URL looks like a listing
                    if any(s in url.lower() for s in listing_signals):
                        queue.append(paginated)
        return product_urls[:max_urls]

    @staticmethod
    def _normalize_product_url(url: str) -> str:
        """Collapse Cafe24 product URL variants to a stable dedupe key."""
        raw = (url or "").strip()
        if not raw:
            return ""
        try:
            p = urlparse(raw)
        except Exception:
            return raw
        if not p.netloc:
            return raw
        path = (p.path or "").rstrip("/")
        host = p.netloc.lower()
        m = re.search(r"/product/[^/]+/(\d+)$", path, re.IGNORECASE)
        if m:
            return f"{p.scheme}://{host}/product/_/{m.group(1)}"
        qs = parse_qs(p.query)
        for key in ("product_no", "productno", "goods_no", "goodsno"):
            vals = qs.get(key)
            if vals and vals[0]:
                return f"{p.scheme}://{host}/product/_/{vals[0]}"
        return f"{p.scheme}://{host}{path}" + (f"?{p.query}" if p.query else "")

    @staticmethod
    def _dedupe_product_urls(urls: List[str]) -> List[str]:
        out: List[str] = []
        seen: set = set()
        for u in urls:
            key = StoreService._normalize_product_url(u) or u
            if key in seen:
                continue
            seen.add(key)
            out.append(u)
        return out

    @staticmethod
    def _catalog_cache_key(mall_id: str, seed_url: str) -> str:
        p = urlparse((seed_url or "").strip())
        seed = f"{p.scheme}://{p.netloc.lower()}{p.path}".rstrip("/")
        if p.query:
            seed += "?" + p.query
        return f"{mall_id}|{seed}"

    def _catalog_cache_get(self, mall_id: str, seed_url: str) -> Optional[Dict[str, Any]]:
        key = self._catalog_cache_key(mall_id, seed_url)
        entry = self._catalog_url_cache.get(key)
        if not entry:
            return None
        age = (datetime.now(timezone.utc) - entry["created_at"]).total_seconds()
        if age > self._CATALOG_CACHE_TTL_SEC:
            self._catalog_url_cache.pop(key, None)
            return None
        return entry

    def _catalog_cache_put(
        self,
        mall_id: str,
        seed_url: str,
        urls: List[str],
        *,
        sitemap_count: int = 0,
        category_count: int = 0,
        expanded: bool = False,
    ) -> None:
        key = self._catalog_cache_key(mall_id, seed_url)
        self._catalog_url_cache[key] = {
            "urls": list(urls),
            "created_at": datetime.now(timezone.utc),
            "sitemap_count": sitemap_count,
            "category_count": category_count,
            "expanded": expanded,
        }

    @staticmethod
    def _extract_category_urls(html_or_xml: str, base_url: str) -> List[str]:
        """Collect /category/ links from HTML or sitemap XML."""
        parsed = urlparse(base_url)
        host = (parsed.netloc or "").lower()
        if not host:
            return []
        locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", html_or_xml or "", re.IGNORECASE)
        hrefs = re.findall(
            r'href\s*=\s*["\']([^"\']+)["\']', html_or_xml or "", re.IGNORECASE
        )
        out: List[str] = []
        seen: set = set()
        for raw in locs + hrefs:
            raw = (raw or "").strip()
            if not raw:
                continue
            if raw.startswith("//"):
                raw = (parsed.scheme or "https") + ":" + raw
            elif raw.startswith("/"):
                raw = f"{parsed.scheme}://{host}{raw}"
            elif not raw.startswith("http"):
                raw = f"{parsed.scheme}://{host}/{raw.lstrip('./')}"
            try:
                p = urlparse(raw)
            except Exception:
                continue
            if p.netloc.lower() != host:
                continue
            low = (p.path or "").lower()
            if "/category/" not in low:
                continue
            clean = p._replace(fragment="").geturl()
            if clean in seen:
                continue
            seen.add(clean)
            out.append(clean)
        return out

    async def _expand_catalog_from_categories(
        self,
        category_urls: List[str],
        seed_urls: List[str],
        budget_seconds: float = 28.0,
        max_categories: int = 60,
        max_pages: int = 20,
    ) -> Tuple[List[str], Dict[str, int]]:
        """Paginate category listing pages to grow product URL coverage past thin sitemaps."""
        import time as _time

        out = self._dedupe_product_urls(list(seed_urls))
        seen_norm = {self._normalize_product_url(u) for u in out}
        deadline = _time.monotonic() + max(5.0, budget_seconds)
        cats_visited = 0
        pages_fetched = 0

        def _over() -> bool:
            return _time.monotonic() >= deadline

        for cat_url in category_urls[:max_categories]:
            if _over():
                break
            cats_visited += 1
            parsed_cat = urlparse(cat_url)
            no_progress = 0
            for pn in range(1, max_pages + 1):
                if _over():
                    break
                try:
                    if pn == 1:
                        page_url = cat_url
                    else:
                        cat_params = parse_qs(parsed_cat.query)
                        cat_params.pop("page", None)
                        cat_params["page"] = [str(pn)]
                        page_url = (
                            parsed_cat.scheme
                            + "://"
                            + parsed_cat.netloc
                            + parsed_cat.path
                            + "?"
                            + urlencode(cat_params, doseq=True)
                        )
                    page_html = await self._fetch_html(page_url, timeout=8.0)
                    pages_fetched += 1
                    added = 0
                    for u in self._discover_product_urls(page_html, page_url):
                        key = self._normalize_product_url(u)
                        if key in seen_norm:
                            continue
                        seen_norm.add(key)
                        out.append(u)
                        added += 1
                    if pn > 1 and added == 0:
                        no_progress += 1
                        if no_progress >= 2:
                            break
                    else:
                        no_progress = 0
                except Exception:
                    break

        stats = {
            "categories_visited": cats_visited,
            "pages_fetched": pages_fetched,
            "product_urls": len(out),
        }
        logger.info(
            "[CatalogCrawl] Category expand: seed=%d → %d (cats=%d pages=%d budget=%.1fs)",
            len(seed_urls),
            len(out),
            cats_visited,
            pages_fetched,
            budget_seconds,
        )
        return out, stats

    async def _deep_crawl_product_urls(
        self,
        seed_url: str,
        urls: List[str],
        budget_seconds: float = 12.0,
        max_categories: int = 5,
        max_pages: int = 3,
    ) -> List[str]:
        """Budgeted homepage/category crawl used only when discovery is thin.

        Caps categories/pages and stops when the wall-clock budget expires so
        catalog learning can still finish inside a single HTTP request.
        """
        import time as _time

        out = list(urls)
        seen = set(out)
        deadline = _time.monotonic() + max(3.0, budget_seconds)

        def _over_budget() -> bool:
            return _time.monotonic() >= deadline

        try:
            parsed_dc = urlparse(seed_url)
            home_url = parsed_dc.scheme + "://" + parsed_dc.netloc + "/"
            home_html = await self._fetch_html(home_url, timeout=8.0)
            for u in self._discover_product_urls(home_html, home_url):
                if u not in seen:
                    seen.add(u)
                    out.append(u)

            cat_hrefs = re.findall(
                r'href\s*=\s*["\']([^"\']+category[^"\']*)["\']', home_html, re.IGNORECASE
            )
            cat_urls_to_visit: List[str] = []
            seen_cats: set = set()
            for raw in cat_hrefs:
                raw = raw.strip()
                if raw.startswith("/"):
                    raw = home_url.rstrip("/") + raw
                elif not raw.startswith("http"):
                    raw = home_url.rstrip("/") + "/" + raw.lstrip("./")
                if raw not in seen_cats and parsed_dc.netloc in raw:
                    seen_cats.add(raw)
                    cat_urls_to_visit.append(raw)

            async def _add_with_pagination(cat_url: str) -> None:
                if _over_budget():
                    return
                first_html = await self._fetch_html(cat_url, timeout=6.0)
                for u in self._discover_product_urls(first_html, cat_url):
                    if u not in seen:
                        seen.add(u)
                        out.append(u)
                parsed_cat = urlparse(cat_url)
                no_progress = 0
                for pn in range(2, max_pages + 1):
                    if _over_budget():
                        return
                    try:
                        cat_params = parse_qs(parsed_cat.query)
                        cat_params.pop("page", None)
                        cat_params["page"] = [str(pn)]
                        paginated = (
                            parsed_cat.scheme
                            + "://"
                            + parsed_cat.netloc
                            + parsed_cat.path
                            + "?"
                            + urlencode(cat_params, doseq=True)
                        )
                        pag_html = await self._fetch_html(paginated, timeout=6.0)
                        added = 0
                        for u in self._discover_product_urls(pag_html, paginated):
                            if u not in seen:
                                seen.add(u)
                                out.append(u)
                                added += 1
                        if added == 0:
                            no_progress += 1
                            if no_progress >= 2:
                                break
                        else:
                            no_progress = 0
                    except Exception:
                        break

            cate_nos = list(set(re.findall(r"cate_no=(\d+)", home_html)))[:max_categories]
            for cn in cate_nos:
                if _over_budget():
                    break
                try:
                    cat_url = home_url.rstrip("/") + "/product/list.html?cate_no=" + cn
                    await _add_with_pagination(cat_url)
                except Exception:
                    pass

            for cat_url in cat_urls_to_visit[:max_categories]:
                if _over_budget():
                    break
                try:
                    await _add_with_pagination(cat_url)
                except Exception:
                    pass

            logger.info(
                "[CatalogCrawl] Deep crawl finished: %d URLs (budget=%.1fs remaining=%.1fs)",
                len(out),
                budget_seconds,
                max(0.0, deadline - _time.monotonic()),
            )
        except Exception as e:
            logger.warning("[CatalogCrawl] Deep crawl failed: %s", e)
        return out

    async def crawl_store_catalog(
        self,
        session: AsyncSession,
        mall_id: str,
        crawl_req: "StoreCatalogCrawlRequest",
        ) -> "StoreCatalogCrawlResponse":
        import asyncio as _asyncio
        from app.schemas.store import StoreCatalogCrawlResponse
        from app.schemas.store import StoreKnowledgeCrawlRequest

        max_products = max(1, min(50, crawl_req.max_products or 20))
        offset = max(0, crawl_req.offset or 0)
        sitemap_count = 0
        category_count = 0
        used_cache = False
        expand_partial = False

        cached = None if offset == 0 else self._catalog_cache_get(mall_id, crawl_req.url)
        if cached and cached.get("urls"):
            urls = list(cached["urls"])
            sitemap_count = int(cached.get("sitemap_count") or 0)
            category_count = int(cached.get("category_count") or 0)
            used_cache = True
            logger.info(
                "[CatalogCrawl] Cache hit mall=%s urls=%d offset=%d",
                mall_id,
                len(urls),
                offset,
            )
        else:
            if offset > 0:
                logger.info(
                    "[CatalogCrawl] Cache miss at offset=%d → rediscover then resume",
                    offset,
                )

            raw_html = crawl_req.raw_html_override
            if not raw_html:
                try:
                    raw_html = await self._fetch_html(crawl_req.url, timeout=15.0)
                except Exception as e:
                    logger.warning("[CatalogCrawl] Failed to fetch %s: %s", crawl_req.url, e)
                    return StoreCatalogCrawlResponse(
                        discovered=0,
                        learned=0,
                        skipped_duplicates=0,
                        failed=0,
                        items=[],
                        notes="목록/사이트맵 페이지를 가져오지 못했습니다: " + str(e),
                    )

            is_sitemap = (
                "sitemap" in (crawl_req.url or "").lower()
                or "<urlset" in (raw_html or "").lower()
                or "<sitemapindex" in (raw_html or "").lower()
            )
            category_urls: List[str] = []
            urls: List[str] = []

            if is_sitemap:
                sub_sitemaps = re.findall(
                    r"<sitemap>\s*<loc>\s*(.*?)\s*</loc>", raw_html, re.IGNORECASE
                )
                if sub_sitemaps:
                    all_locs: List[str] = []
                    for sm_url in sub_sitemaps:
                        try:
                            sm_html = await self._fetch_html(sm_url.strip(), timeout=15.0)
                            all_locs.extend(
                                re.findall(r"<loc>\s*(.*?)\s*</loc>", sm_html, re.IGNORECASE)
                            )
                        except Exception:
                            pass
                    locs = all_locs or re.findall(
                        r"<loc>\s*(.*?)\s*</loc>", raw_html, re.IGNORECASE
                    )
                else:
                    locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", raw_html, re.IGNORECASE)

                category_urls = self._extract_category_urls(
                    "\n".join(f"<loc>{x}</loc>" for x in locs), crawl_req.url
                )
                skip_signals = (
                    "shopinfo",
                    "member/",
                    "board/",
                    "category/",
                    "cart",
                    "login",
                    "register",
                    "account",
                    "search",
                    "sitemap",
                    "javascript:",
                    "mailto:",
                    "tel:",
                    "#",
                )
                seen: set = set()
                for loc in locs:
                    loc = loc.strip()
                    if not loc or loc in seen:
                        continue
                    seen.add(loc)
                    low = loc.lower()
                    if any(s in low for s in skip_signals):
                        continue
                    if "/product/" in low:
                        urls.append(loc)
                if not urls:
                    for loc in locs:
                        loc = loc.strip()
                        if not loc or loc in urls:
                            continue
                        low = loc.lower()
                        if any(s in low for s in skip_signals):
                            continue
                        urls.append(loc)
            else:
                urls = self._discover_product_urls(raw_html, crawl_req.url)
                category_urls = self._extract_category_urls(raw_html, crawl_req.url)
                if urls:
                    parsed_pg = urlparse(crawl_req.url)
                    for page_num in range(2, 11):
                        try:
                            pg_params = parse_qs(parsed_pg.query)
                            pg_params.pop("page", None)
                            pg_params["page"] = [str(page_num)]
                            page_url = (
                                parsed_pg.scheme
                                + "://"
                                + parsed_pg.netloc
                                + parsed_pg.path
                                + "?"
                                + urlencode(pg_params, doseq=True)
                            )
                            page_html = await self._fetch_html(page_url, timeout=10.0)
                            new_urls = self._discover_product_urls(page_html, page_url)
                            added = 0
                            for u in new_urls:
                                if u not in urls:
                                    urls.append(u)
                                    added += 1
                            if added == 0:
                                break
                        except Exception:
                            break

            urls = self._dedupe_product_urls(urls)
            sitemap_count = len(urls)
            category_count = len(category_urls)

            # Always expand via categories when present — Cafe24 sitemaps are often incomplete.
            if category_urls:
                before = len(urls)
                urls, expand_stats = await self._expand_catalog_from_categories(
                    category_urls=category_urls,
                    seed_urls=urls,
                    budget_seconds=45.0,
                    max_categories=80,
                    max_pages=30,
                )
                if (
                    expand_stats.get("categories_visited", 0) < len(category_urls)
                    and len(urls) <= before
                ):
                    expand_partial = True
                elif expand_stats.get("categories_visited", 0) < min(len(category_urls), 80):
                    expand_partial = True

            # Thin fallback only when still almost empty (avoid long deep crawl after rich sitemap).
            if len(urls) < max(max_products, 3):
                urls = await self._deep_crawl_product_urls(
                    seed_url=crawl_req.url,
                    urls=urls,
                    budget_seconds=12.0,
                    max_categories=5,
                    max_pages=3,
                )
                if len(urls) < 3:
                    try:
                        parsed = urlparse(crawl_req.url)
                        sitemap_url = parsed.scheme + "://" + parsed.netloc + "/sitemap.xml"
                        sm_html = await self._fetch_html(sitemap_url, timeout=15.0)
                        for u in self._discover_product_urls(sm_html, sitemap_url):
                            if self._normalize_product_url(u) not in {
                                self._normalize_product_url(x) for x in urls
                            }:
                                urls.append(u)
                        urls = self._dedupe_product_urls(urls)
                    except Exception:
                        pass
            else:
                logger.info(
                    "[CatalogCrawl] Skip thin deep crawl: have %d URLs (sitemap=%d cats=%d)",
                    len(urls),
                    sitemap_count,
                    category_count,
                )

            # Cafe24 Admin API gap-fill when OAuth is connected (selling+display only).
            api_added = 0
            try:
                from app.application.commerce_service import commerce_service

                api_urls = await commerce_service.list_selling_product_detail_urls(
                    session, mall_id, crawl_req.url
                )
                before_api = len(urls)
                for u in api_urls:
                    urls.append(u)
                urls = self._dedupe_product_urls(urls)
                api_added = max(0, len(urls) - before_api)
                if api_added:
                    logger.info(
                        "[CatalogCrawl] Cafe24 API added %d new product URLs (total=%d)",
                        api_added,
                        len(urls),
                    )
            except Exception as e:
                logger.warning("[CatalogCrawl] Cafe24 API enrich skipped: %s", e)

            urls = self._dedupe_product_urls(urls)
            self._catalog_cache_put(
                mall_id,
                crawl_req.url,
                urls,
                sitemap_count=sitemap_count,
                category_count=category_count,
                expanded=bool(category_urls) or api_added > 0,
            )

        total_discovered = len(urls)
        if offset > total_discovered:
            offset = 0

        existing_res = await session.execute(
            select(StoreKnowledgeModel.source_url).where(
                StoreKnowledgeModel.mall_id == mall_id
            )
        )
        existing_raw = {r[0] for r in existing_res.all() if r[0]}
        existing_norm = {self._normalize_product_url(u) for u in existing_raw}

        learned_items = []
        skipped = 0
        failed = 0
        timed_out = False
        cursor = offset
        force_refresh = bool(getattr(crawl_req, "force_refresh", False))
        learn_deadline = _asyncio.get_event_loop().time() + 40.0

        for u in urls[offset:]:
            if len(learned_items) >= max_products:
                break
            if _asyncio.get_event_loop().time() > learn_deadline:
                timed_out = True
                break
            cursor += 1
            norm = self._normalize_product_url(u)
            if (u in existing_raw or norm in existing_norm) and not force_refresh:
                skipped += 1
                continue
            try:
                single_req = StoreKnowledgeCrawlRequest(url=u, tags=crawl_req.tags)
                resp = await self.crawl_and_learn_url(session, mall_id, single_req)
                learned_items.append(resp)
                existing_raw.add(u)
                existing_norm.add(norm)
            except Exception as e:
                logger.warning("[CatalogCrawl] Failed for %s: %s", u, e)
                failed += 1

        discovered = max(0, cursor - offset)

        total_learned_res = await session.execute(
            select(func.count()).select_from(StoreKnowledgeModel).where(
                StoreKnowledgeModel.mall_id == mall_id,
                StoreKnowledgeModel.doc_type == "crawled_url",
            )
        )
        total_learned = total_learned_res.scalar() or 0

        next_offset = cursor
        has_more = next_offset < total_discovered

        discovery_bit = ""
        if not used_cache and (sitemap_count or category_count):
            discovery_bit = (
                f"발견 {total_discovered}개"
                f"(사이트맵 상품 {sitemap_count}"
                + (f"+카테고리 {category_count}개 확장" if category_count else "")
                + "). "
            )
        elif used_cache:
            discovery_bit = f"캐시된 발견 URL {total_discovered}개 사용. "

        if total_discovered == 0:
            notes = (
                "상품 링크를 찾지 못했습니다. 카테고리/목록 페이지 URL을 넣거나, "
                "사이트맵(sitemap.xml) 주소를 직접 입력해 주세요. "
                "JavaScript로만 렌더링되는 스토어(쿠팡/네이버 스마트스토어)는 "
                "현재 자동 수집이 제한됩니다."
            )
        elif not has_more:
            notes = (
                discovery_bit
                + "학습 완료! 누적 "
                + str(total_learned)
                + "/"
                + str(total_discovered)
                + "개. (이번 +"
                + str(len(learned_items))
                + ", 중복 "
                + str(skipped)
                + ", 실패 "
                + str(failed)
                + ")"
            )
        else:
            notes = (
                discovery_bit
                + "이번 배치 +"
                + str(len(learned_items))
                + "개. 누적 "
                + str(total_learned)
                + "/"
                + str(total_discovered)
                + " ("
                + str(int(100 * total_learned / total_discovered) if total_discovered else 0)
                + "%). (중복 "
                + str(skipped)
                + ", 실패 "
                + str(failed)
                + ", next_offset="
                + str(next_offset)
                + ")"
            )
            if timed_out:
                notes += " 배치 시간 제한 → 이어서 학습하세요."
            else:
                notes += " → 다음 배치 계속."
            if expand_partial:
                notes += " (카테고리 확장 일부만 완료 — offset=0 재시작 시 추가 확장 가능)"

        return StoreCatalogCrawlResponse(
            discovered=discovered,
            learned=len(learned_items),
            skipped_duplicates=skipped,
            failed=failed,
            total_products=total_discovered,
            learned_total=total_learned,
            has_more=has_more,
            next_offset=next_offset,
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
                original_price=getattr(d, "original_price", None),
                purchase_url=d.purchase_url,
                image_url=d.image_url,
                tags=d.tags,
                created_at=d.created_at.isoformat(),
            )
            for d in docs
        ]

    async def delete_store(self, session: AsyncSession, mall_id: str) -> bool:
        """Delete a store and all related knowledge/messages."""
        from sqlalchemy import delete as sql_delete
        # Delete knowledge
        await session.execute(
            sql_delete(StoreKnowledgeModel).where(StoreKnowledgeModel.mall_id == mall_id)
        )
        # Delete related data
        try:
            from app.infrastructure.database.models import WebhookAlertLogModel, OrderCacheModel, ClaimModel, CommerceConnectionModel
            await session.execute(sql_delete(WebhookAlertLogModel).where(WebhookAlertLogModel.mall_id == mall_id))
            await session.execute(sql_delete(OrderCacheModel).where(OrderCacheModel.mall_id == mall_id))
            await session.execute(sql_delete(ClaimModel).where(ClaimModel.mall_id == mall_id))
            await session.execute(sql_delete(CommerceConnectionModel).where(CommerceConnectionModel.mall_id == mall_id))
        except Exception:
            pass
        # Messages are linked to sessions, not stores - skip message deletion
        # Delete store
        q = select(StoreModel).where(StoreModel.mall_id == mall_id)
        res = await session.execute(q)
        store = res.scalar_one_or_none()
        if store:
            await session.delete(store)
            await session.commit()
            return True
        await session.commit()
        return False

    @staticmethod
    def _safe_brand_logo_url(store: StoreModel) -> Optional[str]:
        """Read logo without forcing a lazy SELECT when the column is deferred/missing."""
        if "brand_logo_url" in store.__dict__:
            return store.__dict__.get("brand_logo_url")
        try:
            return store.brand_logo_url
        except Exception:
            return None

    @staticmethod
    def _is_brand_logo_schema_error(exc: Exception) -> bool:
        err = f"{type(exc).__name__}: {exc}".lower()
        return (
            "brand_logo_url" in err
            or "no such column" in err
            or "does not exist" in err
        )

    async def get_store_by_mall_id(
        self, session: AsyncSession, mall_id: str
        ) -> Optional[StoreModel]:
        q_full = select(StoreModel).where(StoreModel.mall_id == mall_id)
        q_defer = (
            select(StoreModel)
            .options(defer(StoreModel.brand_logo_url))
            .where(StoreModel.mall_id == mall_id)
        )
        try:
            res = await session.execute(q_full)
            return res.scalar_one_or_none()
        except Exception as e:
            if not self._is_brand_logo_schema_error(e):
                raise
            logger.warning(
                "[Store] schema drift on get_store (%s); applying lightweight migrations",
                e,
            )
            await session.rollback()
            from app.infrastructure.database.session import apply_lightweight_migrations

            await apply_lightweight_migrations()
            try:
                res = await session.execute(q_full)
                return res.scalar_one_or_none()
            except Exception as e2:
                if not self._is_brand_logo_schema_error(e2):
                    raise
                await session.rollback()
                res = await session.execute(q_defer)
                return res.scalar_one_or_none()

    async def list_stores(self, session: AsyncSession) -> List[StoreResponse]:
        q = select(StoreModel).order_by(StoreModel.created_at.desc())
        res = await session.execute(q)
        stores = res.scalars().all()
        return [self._to_response(s) for s in stores]


store_service = StoreService()
