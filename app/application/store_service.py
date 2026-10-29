import html
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import httpx
from sqlalchemy import func, select
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
            business_hours=store.business_hours or "365일 24시간",
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
                existing_store.welcome_message = request.welcome_message
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
                existing_store.bot_avatar_url = request.bot_avatar_url
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

        # Prefer JSON-LD Product name, then last og:title (Cafe24: store name first, product name second)
        jsonld_name = re.search(
            r'"@type"\s*:\s*"Product"[^}]*?"name"\s*:\s*"([^"]{2,200})"',
            raw_html,
            re.IGNORECASE | re.DOTALL,
        )
        og_titles = re.findall(
            r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']',
            raw_html,
            re.IGNORECASE,
        )
        if jsonld_name:
            title = html.unescape(jsonld_name.group(1).strip())
        elif og_titles:
            title = html.unescape(og_titles[-1].strip())
        else:
            title_match = re.search(r"<title>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
            title = html.unescape(title_match.group(1).strip()) if title_match else crawl_req.url

        # Extract price (og:price:amount, JSON-LD, Cafe24 JS vars, or "28,000원")
        price: Optional[int] = None
        # 1) OpenGraph / meta
        price_meta = re.search(
            r'property=["\'](?:product:price:amount|og:price:amount)["\']\s+content=["\']([0-9,]+)["\']',
            raw_html,
            re.IGNORECASE,
        )
        if price_meta:
            price = int(price_meta.group(1).replace(",", ""))
        # 2) JSON-LD Product offers.price
        if price is None:
            jsonld_price = re.search(
                r'"@type"\s*:\s*"Product"[^}]*?"price"\s*:\s*"?([0-9,]+)"?',
                raw_html,
                re.IGNORECASE | re.DOTALL,
            )
            if jsonld_price:
                try:
                    price = int(jsonld_price.group(1).replace(",", ""))
                except ValueError:
                    pass
        # 3) Cafe24 JS: var product_price = "28000" or EC_PRODUCT_INFO
        if price is None:
            cafe24_price = re.search(
                r'(?:product_price|productPrice|sale_price|salePrice)\s*[=:]\s*["\']?([0-9,]+)',
                raw_html,
                re.IGNORECASE,
            )
            if cafe24_price:
                try:
                    price = int(cafe24_price.group(1).replace(",", ""))
                except ValueError:
                    pass
        # 4) Fallback: "28,000원" in body text
        if price is None:
            krw_match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+)\s*원", raw_html)
            if krw_match:
                price = int(krw_match.group(1).replace(",", ""))
        # 5) Fallback: "28000원" (no comma)
        if price is None:
            krw_match2 = re.search(r"([0-9]{4,})\s*원", raw_html)
            if krw_match2:
                try:
                    price = int(krw_match2.group(1))
                except ValueError:
                    pass

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
        for _n in ['브랜드소개', '제품구매', '특가판매', '알뜰장터', '제품소개서', '이벤트', '공지사항', '문의하기', '회사소개', '로그인', 'About SHOP', '기능별', '탄력/주름개선', '수분/보습', '민감/진정', '영양', '미백/톤업', '지성/트러블', '모공/피지', '기미/잡티', '라인별', '스킨케어', '클린징', '마사지 오일', '세럼/에센스/앰플', '크림', '바디', '모델링팩/마스크', '이너뷰티', '메이크업/자외선 차단', '덴탈/두피', '소모품', '오뜨엘라', '전신마사지젤', 'Event Community', '상품 리뷰', 'FAQ', 'Join Order', '현재 위치', '홈 SHOP', '배송비', '용량', '추천메일 보내기', '상품조르기', '대량구매문의', '기본 정보', '상품명', '리뷰', '관련상품', '배송비', '용량']:
            cleaned = cleaned.replace(_n, " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        summary_content = (title + ". " + cleaned[:600]) if cleaned else title

        create_req = StoreKnowledgeCreateRequest(
            doc_type="crawled_url",
            title=title[:256],
            content=summary_content,
            price=price,
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
            if any(s in low for s in skip_signals):
                continue
            if not any(s in low for s in product_signals):
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
        max_pages = 100
        while queue and page_count < max_pages and len(product_urls) < max_urls:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            page_count += 1
            try:
                html = await self._fetch_html(url, timeout=10.0)
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
                if any(s in low for s in skip_signals):
                    continue
                clean = p._replace(fragment="").geturl()
                if any(s in low for s in product_signals):
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

    async def crawl_store_catalog(
        self,
        session: AsyncSession,
        mall_id: str,
        crawl_req: "StoreCatalogCrawlRequest",
        ) -> "StoreCatalogCrawlResponse":
        import asyncio as _asyncio
        from app.schemas.store import StoreCatalogCrawlResponse, StoreKnowledgeResponse
        from app.schemas.store import StoreKnowledgeCrawlRequest

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

        # Detect sitemap vs listing page
        is_sitemap = "sitemap" in (crawl_req.url or "").lower() or "<urlset" in (raw_html or "").lower() or "<sitemapindex" in (raw_html or "").lower()

        if is_sitemap:
            # Check if sitemap index (contains sub-sitemaps)
            sub_sitemaps = re.findall(r"<sitemap>\s*<loc>\s*(.*?)\s*</loc>", raw_html, re.IGNORECASE)
            if sub_sitemaps:
                all_locs = []
                for sm_url in sub_sitemaps:
                    try:
                        sm_html = await self._fetch_html(sm_url.strip(), timeout=15.0)
                        all_locs.extend(re.findall(r"<loc>\s*(.*?)\s*</loc>", sm_html, re.IGNORECASE))
                    except Exception:
                        pass
                locs = all_locs if all_locs else re.findall(r"<loc>\s*(.*?)\s*</loc>", raw_html, re.IGNORECASE)
            else:
                locs = re.findall(r"<loc>\s*(.*?)\s*</loc>", raw_html, re.IGNORECASE)
            skip_signals = ("shopinfo", "member/", "board/", "category/", "cart", "login", "register", "account", "search", "sitemap", "javascript:", "mailto:", "tel:", "#")
            urls = []
            seen = set()
            for loc in locs:
                loc = loc.strip()
                if not loc or loc in seen:
                    continue
                seen.add(loc)
                low = loc.lower()
                if any(s in low for s in skip_signals):
                    continue
                # For sitemaps, keep product URLs (contain /product/) and skip the rest
                if "/product/" in low:
                    urls.append(loc)
            # If no product URLs found, fall back to all non-skip URLs
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
            # Pagination: if listing page, try fetching additional pages
            if not is_sitemap and len(urls) > 0:
                base = crawl_req.url.split("?")[0].rstrip("/")
                for page_num in range(2, 11):
                    try:
                        page_url = base + "?page=" + str(page_num)
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
            # Deep crawl: if listing page discovery is thin, crawl the whole site
            if not is_sitemap and len(urls) < 50:
                try:
                    deep_urls = await self._deep_discover_product_urls(crawl_req.url, max_urls=5000)
                    for u in deep_urls:
                        if u not in urls:
                            urls.append(u)
                except Exception as e:
                    logger.warning("[CatalogCrawl] Deep crawl failed: %s", e)
            # Fallback: try sitemap.xml if discovery was thin
            if len(urls) < 3:
                try:
                    parsed = urlparse(crawl_req.url)
                    sitemap_url = parsed.scheme + "://" + parsed.netloc + "/sitemap.xml"
                    sm_html = await self._fetch_html(sitemap_url, timeout=15.0)
                    for u in self._discover_product_urls(sm_html, sitemap_url):
                        if u not in urls:
                            urls.append(u)
                except Exception:
                    pass

        total_discovered = len(urls)
        offset = max(0, crawl_req.offset or 0)
        max_products = max(1, min(50, crawl_req.max_products or 20))
        urls = urls[offset:]
        urls = urls[:max_products + 5]  # small buffer for dedup

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
        deadline = _asyncio.get_event_loop().time() + 55.0
        for u in urls:
            if len(learned_items) >= max_products:
                break
            if _asyncio.get_event_loop().time() > deadline:
                break
            if u in existing and not getattr(crawl_req, "force_refresh", False):
                skipped += 1
                continue
            try:
                single_req = StoreKnowledgeCrawlRequest(url=u, tags=crawl_req.tags)
                resp = await self.crawl_and_learn_url(session, mall_id, single_req)
                learned_items.append(resp)
                existing.add(u)
            except Exception as e:
                logger.warning("[CatalogCrawl] Failed for %s: %s", u, e)
                failed += 1

        # Count total learned products for this mall (cumulative progress)
        total_learned_res = await session.execute(
            select(func.count()).select_from(StoreKnowledgeModel).where(
                StoreKnowledgeModel.mall_id == mall_id,
                StoreKnowledgeModel.doc_type == "crawled_url",
            )
        )
        total_learned = total_learned_res.scalar() or 0

        if discovered == 0:
            notes = (
                "상품 링크를 찾지 못했습니다. 카테고리/목록 페이지 URL을 넣거나, "
                "사이트맵(sitemap.xml) 주소를 직접 입력해 주세요. "
                "JavaScript로만 렌더링되는 스토어(쿠팡/네이버 스마트스토어)는 "
                "현재 자동 수집이 제한됩니다."
            )
        else:
            remaining = max(0, total_discovered - total_learned)
            notes = (
                "이번 실행: " + str(len(learned_items)) + "개 새로 학습. "
                "누적: " + str(total_learned) + "/" + str(total_discovered) + "개 학습 완료. "
                "(중복 " + str(skipped) + "개 건너뜀, 실패 " + str(failed) + "개)"
            )
            if remaining > 0:
                notes += " → 계속 학습하려면 다시 버튼을 눌러주세요."

        return StoreCatalogCrawlResponse(
            discovered=discovered,
            learned=len(learned_items),
            skipped_duplicates=skipped,
            failed=failed,
            total_products=total_discovered,
            learned_total=total_learned,
            has_more=(offset + len(urls)) < total_discovered,
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

        async def delete_store(self, session: AsyncSession, mall_id: str) -> bool:
        """Delete a store and all related knowledge/messages."""
        from sqlalchemy import delete as sql_delete
        # Delete knowledge
        await session.execute(
            sql_delete(StoreKnowledgeModel).where(StoreKnowledgeModel.mall_id == mall_id)
        )
        # Delete messages
        try:
            await session.execute(
                sql_delete(MessageModel).where(MessageModel.mall_id == mall_id)
            )
        except Exception:
            pass
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
