import json
from typing import Dict, List
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.commerce_service import commerce_service
from app.application.store_service import INDUSTRY_DEFAULTS, store_service
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/api/widget", tags=["Widget"])


# 18 Luxury Commercial-Grade Vector & Portrait Badges (Bright, Minimal, Real Photo Portrait & Brand Signatures)
FLATICON_PRESET_SVGS: Dict[str, str] = {
    # 1. K-뷰티 실사 모델 카운슬러 (사장님 업로드 뷰티 화보 모델 아바타)
    "preset_beauty_model": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <clipPath id="clip_bm"><circle cx="32" cy="32" r="29.5"/></clipPath>
        <linearGradient id="ring_bm" x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
          <stop stop-color="#F9A8D4"/><stop offset="0.5" stop-color="#EC4899"/><stop offset="1" stop-color="#F43F5E"/>
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="31" fill="url(#ring_bm)"/>
      <image href="/static/presets/beauty_model.jpg" x="2" y="2" width="60" height="60" preserveAspectRatio="xMidYMin slice" clip-path="url(#clip_bm)"/>
    </svg>""",
    # 2. 세이지 그린 지식백과 & 아이디어 전구 (사장님 업로드 원료/지식 일러스트)
    "preset_sage_book": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <clipPath id="clip_sb"><circle cx="32" cy="32" r="30"/></clipPath>
      </defs>
      <circle cx="32" cy="32" r="31" fill="#A3B19B"/>
      <image href="/static/presets/sage_book_bulb.jpg" x="1" y="1" width="62" height="62" preserveAspectRatio="xMidYMid slice" clip-path="url(#clip_sb)"/>
    </svg>""",
    # 3. 모던 에메랄드 미니멀 톡 (사장님 첨부 레퍼런스: 깔끔한 그린 원형 + 화이트 라인 말풍선)
    "flaticon_bubble_bot": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bg_emerald" x1="10" y1="6" x2="54" y2="58" gradientUnits="userSpaceOnUse">
          <stop stop-color="#34A853"/><stop offset="1" stop-color="#1E7E34"/>
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="url(#bg_emerald)"/>
      <path d="M20 22H44C45.6569 22 47 23.3431 47 25V37C47 38.6569 45.6569 40 44 40H27L20 45.5V40C18.8954 40 18 39.1046 18 38V25C18 23.3431 19.3431 22 20 22Z" stroke="#FFFFFF" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>""",
    # 2. 코스봇 시그니처 로봇 (밝은 스카이블루 & 화이트 3D 글래스 로봇)
    "flaticon_cute_robot": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bg_cosbot" x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse">
          <stop stop-color="#0284C7"/><stop offset="1" stop-color="#1E3A8A"/>
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="url(#bg_cosbot)"/>
      <line x1="32" y1="12" x2="32" y2="18" stroke="#BAE6FD" stroke-width="2.8" stroke-linecap="round"/>
      <circle cx="32" cy="11" r="3.2" fill="#38BDF8"/>
      <rect x="17" y="18" width="30" height="26" rx="11" fill="#FFFFFF"/>
      <rect x="21" y="23" width="22" height="13" rx="6" fill="#0F172A"/>
      <circle cx="27.5" cy="29.5" r="2.3" fill="#38BDF8"/><circle cx="36.5" cy="29.5" r="2.3" fill="#38BDF8"/>
      <path d="M28.5 39C30 40.3 34 40.3 35.5 39" stroke="#0284C7" stroke-width="2.2" stroke-linecap="round"/>
    </svg>""",
    # 3. 브라이트 오로라 AI 스파클 (Apple Intelligence 감성 화이트&라벤더 오로라)
    "flaticon_smart_ai": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bg_aurora" x1="6" y1="6" x2="58" y2="58" gradientUnits="userSpaceOnUse">
          <stop stop-color="#EEF2FF"/><stop offset="0.5" stop-color="#FCE7F3"/><stop offset="1" stop-color="#E0F2FE"/>
        </linearGradient>
        <linearGradient id="star_grad" x1="16" y1="16" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop stop-color="#6366F1"/><stop offset="0.5" stop-color="#EC4899"/><stop offset="1" stop-color="#06B6D4"/>
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="url(#bg_aurora)" stroke="#E2E8F0" stroke-width="1.5"/>
      <path d="M31 14C31.8 23.2 34.8 26.2 44 27C34.8 27.8 31.8 30.8 31 40C30.2 30.8 27.2 27.8 18 27C27.2 26.2 30.2 23.2 31 14Z" fill="url(#star_grad)"/>
      <path d="M45 36C45.4 40.2 46.8 41.6 51 42C46.8 42.4 45.4 43.8 45 48C44.6 43.8 43.2 42.4 39 42C43.2 41.6 44.6 40.2 45 36Z" fill="#EC4899"/>
    </svg>""",
    # 4. 채널톡 스타일 브라이트 스마일톡 (선명한 로얄블루 + 화이트 스마일 버블)
    "flaticon_yellow_talk": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bg_ch" x1="10" y1="8" x2="54" y2="56" gradientUnits="userSpaceOnUse">
          <stop stop-color="#4F46E5"/><stop offset="1" stop-color="#2563EB"/>
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="url(#bg_ch)"/>
      <path d="M18 30.5C18 22.5 24.3 16.5 32.5 16.5C40.7 16.5 47 22.5 47 30.5C47 38.5 40.7 44.5 32.5 44.5C29.8 44.5 27.3 43.8 25.1 42.6L18.5 45.5L20.1 39.2C18.8 36.7 18 33.7 18 30.5Z" fill="#FFFFFF"/>
      <circle cx="27.5" cy="29" r="2.2" fill="#2563EB"/><circle cx="37.5" cy="29" r="2.2" fill="#2563EB"/>
      <path d="M27.5 34.2C29.5 36.8 35.5 36.8 37.5 34.2" stroke="#2563EB" stroke-width="2.5" stroke-linecap="round"/>
    </svg>""",
    # 5. 로즈골드 뷰티 컨시어지 (화사한 핑크 코랄 + 세련된 부티크 보틀 라인아트)
    "flaticon_beauty_fairy": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bg_rose" x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse">
          <stop stop-color="#FFF1F2"/><stop offset="1" stop-color="#FCE7F3"/>
        </linearGradient>
        <linearGradient id="fg_rose" x1="20" y1="16" x2="44" y2="48" gradientUnits="userSpaceOnUse">
          <stop stop-color="#F43F5E"/><stop offset="1" stop-color="#DB2777"/>
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="url(#bg_rose)" stroke="#FBCFE8" stroke-width="1.5"/>
      <rect x="28" y="15" width="8" height="5" rx="2" fill="url(#fg_rose)"/>
      <path d="M26 22H38L41 27V44C41 46.2 39.2 48 37 48H27C24.8 48 23 46.2 23 44V27L26 22Z" fill="#FFFFFF" stroke="url(#fg_rose)" stroke-width="2.6" stroke-linejoin="round"/>
      <circle cx="32" cy="35" r="4.5" stroke="url(#fg_rose)" stroke-width="2"/>
      <path d="M46 16L47 19L50 20L47 21L46 24L45 21L42 20L45 19L46 16Z" fill="#F43F5E"/>
    </svg>""",
    # 6. 클린 화이트 헤드셋 컨시어지 (밝은 스카이화이트 + 모던 블루 헤드셋 아이콘)
    "flaticon_cs_agent": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bg_sky" x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse">
          <stop stop-color="#F0F9FF"/><stop offset="1" stop-color="#DBEAFE"/>
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="url(#bg_sky)" stroke="#BFDBFE" stroke-width="1.5"/>
      <path d="M19 32V29C19 21.8203 24.8203 16 32 16C39.1797 16 45 21.8203 45 29V32" stroke="#0284C7" stroke-width="3.2" stroke-linecap="round"/>
      <rect x="16" y="29" width="6" height="11" rx="3" fill="#0284C7"/>
      <rect x="42" y="29" width="6" height="11" rx="3" fill="#0284C7"/>
      <path d="M45 38C45 42.5 40.5 46 34 46H30" stroke="#0284C7" stroke-width="2.8" stroke-linecap="round"/>
      <circle cx="30" cy="46" r="2.5" fill="#0284C7"/>
    </svg>""",
    # 7. 티파니 민트 더마 클리닉 (화사한 민트 배경 + 에메랄드 더마 실드 & 크로스)
    "flaticon_derma_doctor": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" fill="#ECFDF5" stroke="#A7F3D0" stroke-width="1.5"/>
      <path d="M32 15L46 20.5V31C46 40.5 39.8 47.5 32 50.5C24.2 47.5 18 40.5 18 31V20.5L32 15Z" fill="#FFFFFF" stroke="#059669" stroke-width="2.6" stroke-linejoin="round"/>
      <path d="M32 25V37M26 31H38" stroke="#10B981" stroke-width="3.2" stroke-linecap="round"/>
    </svg>""",
    # 8. 바이오 랩 글래스 플라스크 (아이스블루 배경 + 미니멀 연구 플라스크)
    "flaticon_lab_flask": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" fill="#F0FDFA" stroke="#99F6E4" stroke-width="1.5"/>
      <path d="M27 17H37M29.5 17V26L20.5 41.5C19.5 43.2 20.7 45.5 22.8 45.5H41.2C43.3 45.5 44.5 43.2 43.5 41.5L34.5 26V17" stroke="#0D9488" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M23 37.5H41L43 41.2C43.8 42.6 42.8 44 41.2 44H22.8C21.2 44 20.2 42.6 21 41.2L23 37.5Z" fill="#14B8A6"/>
      <circle cx="30" cy="32" r="1.8" fill="#14B8A6"/><circle cx="34.5" cy="29" r="1.4" fill="#14B8A6"/>
    </svg>""",
    # 9. 아쿠아 수분 세럼 드롭 (투명감 있는 아쿠아 블루 그라데이션 + 화이트 물방울)
    "flaticon_serum_drop": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bg_aqua" x1="12" y1="8" x2="52" y2="56" gradientUnits="userSpaceOnUse">
          <stop stop-color="#38BDF8"/><stop offset="1" stop-color="#0284C7"/>
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="url(#bg_aqua)"/>
      <path d="M32 15C32 15 19 29.5 19 38.5C19 45.6797 24.8203 51.5 32 51.5C39.1797 51.5 45 45.6797 45 38.5C45 29.5 32 15 32 15Z" fill="#FFFFFF"/>
      <path d="M25.5 36.5C25.5 39.8 27.8 42.5 31 43.2" stroke="#0284C7" stroke-width="2.5" stroke-linecap="round"/>
    </svg>""",
    # 10. 샴페인 골드 VIP 크라운 (크림 아이보리 배경 + 럭셔리 골드 라인 크라운)
    "flaticon_luxury_crown": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" fill="#FFFBEB" stroke="#FDE68A" stroke-width="1.5"/>
      <path d="M17 42L20.5 24L28 31.5L32 20L36 31.5L43.5 24L47 42H17Z" fill="#FEF3C7" stroke="#D97706" stroke-width="2.6" stroke-linejoin="round"/>
      <line x1="18" y1="46" x2="46" y2="46" stroke="#D97706" stroke-width="2.8" stroke-linecap="round"/>
      <circle cx="32" cy="17.5" r="2.2" fill="#D97706"/><circle cx="19.5" cy="21" r="1.8" fill="#D97706"/><circle cx="44.5" cy="21" r="1.8" fill="#D97706"/>
    </svg>""",
    # 11. 인터콤 스타일 듀얼 버블 (세련된 바이올렛 퍼플 + 겹침 말풍선)
    "flaticon_cyber_bot": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bg_violet" x1="10" y1="8" x2="54" y2="56" gradientUnits="userSpaceOnUse">
          <stop stop-color="#8B5CF6"/><stop offset="1" stop-color="#6D28D9"/>
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="url(#bg_violet)"/>
      <rect x="16" y="18" width="24" height="18" rx="6" fill="#DDD6FE" fill-opacity="0.45"/>
      <path d="M23 25H44C46.2091 25 48 26.7909 48 29V39C48 41.2091 46.2091 43 44 43H31L24 47.5V43H23C20.7909 43 19 41.2091 19 39V29C19 26.7909 20.7909 25 23 25Z" fill="#FFFFFF"/>
      <line x1="26" y1="32" x2="41" y2="32" stroke="#6D28D9" stroke-width="2.6" stroke-linecap="round"/>
      <line x1="26" y1="36.5" x2="36" y2="36.5" stroke="#6D28D9" stroke-width="2.6" stroke-linecap="round"/>
    </svg>""",
    # 12. 파스텔 코랄 하트 케어 (따뜻한 피치핑크 + 하트 말풍선 아이콘)
    "flaticon_cute_puppy": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" fill="#FFF1F2" stroke="#FECDD3" stroke-width="1.5"/>
      <path d="M32 45.5C32 45.5 17 36.2 17 26.2C17 21.4 20.8 17.8 25.3 17.8C28.2 17.8 30.7 19.3 32 21.6C33.3 19.3 35.8 17.8 38.7 17.8C43.2 17.8 47 21.4 47 26.2C47 36.2 32 45.5 32 45.5Z" fill="#FB7185" stroke="#E11D48" stroke-width="2" stroke-linejoin="round"/>
      <path d="M23.5 24C22.2 25.2 21.8 27 22.2 28.5" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round"/>
    </svg>""",
    # 13. 호텔 컨시어지 골드 벨 (밝은 웜그레이 + 프리미엄 컨시어지 데스크 벨)
    "flaticon_cat_butler": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" fill="#F8FAFC" stroke="#E2E8F0" stroke-width="1.5"/>
      <path d="M29 18H35M32 18V21" stroke="#0F172A" stroke-width="2.6" stroke-linecap="round"/>
      <path d="M19 39C19 31.8203 24.8203 26 32 26C39.1797 26 45 31.8203 45 39H19Z" fill="#FBBF24" stroke="#0F172A" stroke-width="2.6" stroke-linejoin="round"/>
      <line x1="16" y1="43" x2="48" y2="43" stroke="#0F172A" stroke-width="3" stroke-linecap="round"/>
    </svg>""",
    # 14. 부티크 쇼퍼백 컨시어지 (화사한 핑크 화이트 + 미니멀 브랜드 쇼퍼백)
    "flaticon_shopping_bag": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" fill="#FDF2F8" stroke="#FBCFE8" stroke-width="1.5"/>
      <rect x="19" y="24" width="26" height="23" rx="4" fill="#FFFFFF" stroke="#DB2777" stroke-width="2.6"/>
      <path d="M26 26V21C26 17.6863 28.6863 15 32 15C35.3137 15 38 17.6863 38 21V26" stroke="#DB2777" stroke-width="2.6" stroke-linecap="round"/>
      <path d="M28 35.5L31 38.5L37 32.5" stroke="#EC4899" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>""",
    # 15. 오가닉 보태니컬 리프 (밝은 프레시 그린 + 자연주의 보태니컬 잎사귀)
    "flaticon_fresh_leaf": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="32" cy="32" r="30" fill="#F0FDF4" stroke="#BBF7D0" stroke-width="1.5"/>
      <path d="M21 43C21 29 31 19 45 19C45 33 35 43 21 43Z" fill="#DCFCE7" stroke="#16A34A" stroke-width="2.6" stroke-linejoin="round"/>
      <path d="M21 43L36 28" stroke="#16A34A" stroke-width="2.6" stroke-linecap="round"/>
    </svg>""",
    # 16. 트러스트 실드 A/S 보증 (선명한 코발트 블루 + 화이트 안심 체크 실드)
    "flaticon_shield_as": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="bg_trust" x1="10" y1="8" x2="54" y2="56" gradientUnits="userSpaceOnUse">
          <stop stop-color="#2563EB"/><stop offset="1" stop-color="#1D4ED8"/>
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill="url(#bg_trust)"/>
      <path d="M32 15L46 20.5V31C46 40.5 39.8 47.5 32 50.5C24.2 47.5 18 40.5 18 31V20.5L32 15Z" stroke="#FFFFFF" stroke-width="2.8" stroke-linejoin="round"/>
      <path d="M26.5 32.5L30.5 36.5L38.5 27.5" stroke="#FFFFFF" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>""",
}


@router.get("/script")
async def get_dynamic_widget_script(
    request: Request,
    mall_id: str = Query("demo_mall", description="Store Mall ID"),
    preview_icon: str = Query("", description="Instant preview icon override"),
    preview_shape: str = Query("", description="Instant preview launcher shape override"),
    preview_template: str = Query("", description="Instant preview chat template override"),
    preview_bot_name: str = Query("", description="Instant preview bot name override"),
    preview_store_name: str = Query("", description="Instant preview store name override"),
    preview_label: str = Query("", description="Instant preview bot label override"),
    preview_badge: str = Query("", description="Instant preview brand badge override"),
    preview_industry: str = Query("", description="Instant preview industry override"),
    preview_email: str = Query("", description="Instant preview contact email override"),
    preview_hours: str = Query("", description="Instant preview business hours override"),
    preview_quick_buttons: str = Query("", description="Instant preview comma-separated quick buttons override"),
    preview_pos: str = Query("", description="Instant preview horizontal position (bottom_right or bottom_left)"),
    preview_bottom: int = Query(0, description="Instant preview bottom offset in px"),
    preview_side: int = Query(0, description="Instant preview side offset in px"),
    preview_commerce: str = Query("", description="Instant preview commerce platform override"),
    session: AsyncSession = Depends(get_db),
):
    """Serve a dynamically customized JavaScript widget with 10 Commercial Chat Window Templates & 16 Flaticon Avatars."""
    store = await store_service.get_store_by_mall_id(session, mall_id)

    origin_or_referer = request.headers.get("origin") or request.headers.get("referer")
    # The widget talks back to THIS backend (Render), not the host page origin.
    backend_origin = str(request.base_url).rstrip("/")
    # Render terminates TLS upstream; force https so the widget never
    # talks to the backend over plain http (which would be blocked).
    if backend_origin.startswith("http://"):
        backend_origin = "https://" + backend_origin[len("http://"):]
    if not store_service.is_domain_allowed(store, origin_or_referer):
        blocked_js = f'console.warn("[ChatbotFactory] Unauthorized domain for mall_id={mall_id}. Allowed domains: {store.allowed_domains if store else ""}");'
        return Response(content=blocked_js, media_type="application/javascript")

    title = preview_store_name or (store.store_name if store else "코스라프리")
    industry = preview_industry or (store.industry if store else "general")
    ind_defaults = INDUSTRY_DEFAULTS.get(industry, INDUSTRY_DEFAULTS["general"])
    theme_color = (
        ind_defaults.get("theme_color", "#0284C7")
        if preview_industry
        else (store.theme_color if store else ind_defaults.get("theme_color", "#0284C7"))
    )
    bot_name = preview_bot_name or (store.bot_name if store and store.bot_name else ind_defaults.get("bot_name", "코스봇"))
    brand_badge = preview_badge or (store.brand_badge if store and store.brand_badge else title[:8])
    header_title = (store.header_title if store and store.header_title else "고객상담센터")
    chat_template = preview_template or (store.chat_template if store and store.chat_template else "cosraw_grid")
    contact_email = preview_email or (store.contact_email if store and store.contact_email else ind_defaults.get("contact_email", "contact@cosrawfree.com"))
    business_hours = preview_hours or (store.business_hours if store and store.business_hours else "평일 09:00~18:00")
    input_placeholder = (
        store.input_placeholder
        if store and store.input_placeholder and not preview_industry
        else ind_defaults.get("input_placeholder", "궁금한 내용이나 질문을 입력하세요...")
    )

    quick_buttons: List[str] = []
    if preview_quick_buttons.strip():
        quick_buttons = [x.strip() for x in preview_quick_buttons.split(",") if x.strip()]
    elif store and store.quick_buttons_json and not preview_industry:
        try:
            quick_buttons = json.loads(store.quick_buttons_json)
        except Exception:
            quick_buttons = []
    if not quick_buttons:
        if industry not in INDUSTRY_DEFAULTS and industry.strip():
            custom_ind = industry.strip()
            quick_buttons = [
                f"📌 {custom_ind} 주요 안내",
                "💰 비용 / 견적 / 가격 문의",
                "📅 예약 / 신청 / 일정 확인",
                "📍 위치 / 운영시간 안내",
                "💬 담당자 연결 / 기타 문의",
            ]
        else:
            quick_buttons = ind_defaults.get("quick_buttons", [])

    if store and store.welcome_message and not preview_store_name and not preview_bot_name and not preview_industry:
        welcome_msg = store.welcome_message.replace("\n", "\\n")
    elif industry in INDUSTRY_DEFAULTS and industry != "raw_materials":
        base_welcome = ind_defaults.get("welcome_message", "")
        welcome_msg = f"안녕하세요! <b>{title}</b> AI 상담사 <b>'{bot_name}'</b>입니다. ✨\\n" + (
            base_welcome.split("\n", 1)[1] if "\n" in base_welcome else base_welcome
        )
    elif industry not in INDUSTRY_DEFAULTS and industry.strip():
        welcome_msg = f"안녕하세요! <b>{title} ({industry.strip()})</b> AI 상담사 <b>'{bot_name}'</b>입니다. ✨\\n궁금하신 서비스, 예약/견적 문의 또는 상담 내용을 편하게 말씀해 주세요!"
    else:
        welcome_msg = f"안녕하세요. {title}의 AI 상담사 <b>'{bot_name}'</b> 입니다. 🧪\\n어떤 원료나 서비스가 궁금하신가요?"

    bot_icon_style = preview_icon or (store.bot_icon_style if store and store.bot_icon_style else ind_defaults.get("bot_icon_style", "flaticon_cute_robot"))
    launcher_shape = preview_shape or (store.launcher_shape if store and store.launcher_shape else "cosbot_badge")
    bot_label = preview_label or (store.bot_label if store and store.bot_label else f"{bot_name} 상담")
    bot_avatar_url = (store.bot_avatar_url if store and store.bot_avatar_url and not preview_icon else "")

    if bot_avatar_url:
        safe_url = bot_avatar_url.replace('"', '\\"')
        icon_graphic_html = f'<img src="{safe_url}" alt="bot" class="fresh-bot-avatar-img" />'
    else:
        svg_raw = FLATICON_PRESET_SVGS.get(bot_icon_style, FLATICON_PRESET_SVGS["flaticon_cute_robot"])
        svg_single_line = " ".join(line.strip() for line in svg_raw.splitlines())
        icon_graphic_html = svg_single_line

    remaining_days = None
    is_expired = False
    expiry_warning = False
    status_message = ""
    if store:
        remaining_days, is_expired, expiry_warning, status_message = (
            store_service.evaluate_subscription_status(store)
        )

    upload_guide = ind_defaults.get("upload_guide", "📷 손상 상품 / 참고 사진 업로드 접수")

    saved_layout = {}
    saved_commerce_platform = "none"
    if store and store.policy_config_json:
        try:
            p_dict = json.loads(store.policy_config_json)
            if isinstance(p_dict, dict):
                saved_layout = p_dict.get("widget_layout", {}) or {}
                comm_info = p_dict.get("commerce_api", {}) or {}
                if isinstance(comm_info, dict) and comm_info.get("platform"):
                    saved_commerce_platform = str(comm_info.get("platform"))
        except Exception:
            saved_layout = {}

    commerce_platform = (preview_commerce or saved_commerce_platform or "none").strip()
    commerce_badge_map = {
        "coupang_wing": "🚀 쿠팡 Wing 실시간 연동",
        "coupang": "🚀 쿠팡 Wing 실시간 연동",
        "naver_smartstore": "🟢 스마트스토어 실시간 연동",
        "smartstore": "🟢 스마트스토어 실시간 연동",
        "cafe24": "🛍️ 카페24 실시간 연동",
        "imweb": "🎨 아임웹 실시간 연동",
    }
    commerce_badge = commerce_badge_map.get(commerce_platform, "📦 스토어 API 실시간 연동" if commerce_platform != "none" else "")

    # Cafe24: only show "실시간 연동" when the owner actually finished OAuth.
    # Keys saved but not yet authorized -> "연동 대기" badge.
    if commerce_platform == "cafe24" and store and not preview_commerce:
        conn = await commerce_service.get_connection(session, store.mall_id)
        if conn is None or conn.status != "connected":
            commerce_badge = "⏳ 카페24 연동 대기"

    widget_pos = preview_pos or saved_layout.get("pos", "bottom_right")
    bottom_px = preview_bottom if preview_bottom > 0 else int(saved_layout.get("bottom_px", 24))
    side_px = preview_side if preview_side > 0 else int(saved_layout.get("side_px", 24))
    bottom_px = max(10, min(260, bottom_px))
    side_px = max(10, min(220, side_px))
    win_bottom_px = bottom_px + 92
    horiz_css = f"left: {side_px}px; right: auto;" if widget_pos == "bottom_left" else f"right: {side_px}px; left: auto;"

    is_expired_js = "true" if is_expired else "false"
    expiry_warning_js = "true" if expiry_warning else "false"
    remaining_days_js = str(remaining_days) if remaining_days is not None else "null"
    safe_status_msg = status_message.replace('"', '\\"').replace("\n", "\\n")
    safe_label = bot_label.replace('"', '\\"')
    safe_bot_name = bot_name.replace('"', '\\"')
    safe_brand_badge = brand_badge.replace('"', '\\"')
    safe_header_title = header_title.replace('"', '\\"')
    safe_email = contact_email.replace('"', '\\"')
    safe_hours = business_hours.replace('"', '\\"')
    safe_placeholder = input_placeholder.replace('"', '\\"')
    safe_commerce_platform = commerce_platform.replace('"', '\\"')
    safe_commerce_badge = commerce_badge.replace('"', '\\"')
    quick_buttons_js = json.dumps(quick_buttons, ensure_ascii=False)
    presets_js = json.dumps(
        {k: " ".join(line.strip() for line in v.splitlines()) for k, v in FLATICON_PRESET_SVGS.items()},
        ensure_ascii=False,
    )

    js_content = f"""
(function () {{
  "use strict";

  // Remove any previous instance for live preview hot-reload
  const oldLauncher = document.querySelector(".fresh-widget-launcher");
  const oldWindow = document.querySelector(".fresh-widget-window");
  if (oldLauncher) oldLauncher.remove();
  if (oldWindow) oldWindow.remove();

  window.CHATBOT_FACTORY_SVGS = {presets_js};

  const config = {{
    mallId: "{mall_id}",
    title: "{title}",
    industry: "{industry}",
    primaryColor: "{theme_color}",
    botIconStyle: "{bot_icon_style}",
    launcherShape: "{launcher_shape}",
    botLabel: "{safe_label}",
    botName: "{safe_bot_name}",
    brandBadge: "{safe_brand_badge}",
    headerTitle: "{safe_header_title}",
    chatTemplate: "{chat_template}",
    quickButtons: {quick_buttons_js},
    contactEmail: "{safe_email}",
    businessHours: "{safe_hours}",
    inputPlaceholder: "{safe_placeholder}",
    welcomeMessage: "{welcome_msg}",
    uploadGuide: "{upload_guide}",
    commercePlatform: "{safe_commerce_platform}",
    commerceBadge: "{safe_commerce_badge}",
    isExpired: {is_expired_js},
    expiryWarning: {expiry_warning_js},
    remainingDays: {remaining_days_js},
    statusMessage: "{safe_status_msg}",
    apiBase: "{backend_origin}"
  }};

  const iconGraphicHtml = `{icon_graphic_html}`;
  let sessionId = localStorage.getItem("claim_chat_session_" + config.mallId) || "";

  const style = document.createElement("style");
  style.innerHTML = `
    @keyframes cosbotFloat {{
      0%, 100% {{ transform: translateY(0px); }}
      50% {{ transform: translateY(-5px); }}
    }}
    .fresh-widget-launcher {{
      position: fixed;
      bottom: {bottom_px}px;
      {horiz_css}
      cursor: pointer;
      z-index: 999999;
      user-select: none;
      font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", Roboto, sans-serif;
      animation: cosbotFloat 3.2s ease-in-out infinite;
      transition: all 0.22s ease;
    }}
    .fresh-widget-launcher:hover {{ filter: brightness(1.06); transform: scale(1.05); }}
    .fresh-widget-launcher.shape-cosbot_badge {{
      width: 78px; height: 84px; display: flex; flex-direction: column; align-items: center; justify-content: flex-start;
    }}
    .fresh-cosbot-ring {{
      width: 68px; height: 68px; border-radius: 50%; padding: 3px;
      background: linear-gradient(145deg, #FFFDF9 0%, #F3DFB6 48%, ${{config.primaryColor}} 100%);
      box-shadow: 0 10px 26px rgba(15, 23, 42, 0.22), inset 0 1px 2px rgba(255,255,255,0.95);
      display: flex; align-items: center; justify-content: center; box-sizing: border-box;
    }}
    .fresh-cosbot-inner {{
      width: 100%; height: 100%; border-radius: 50%;
      background: #FFFFFF;
      display: flex; align-items: center; justify-content: center; overflow: hidden;
    }}
    .fresh-cosbot-inner svg {{ width: 100%; height: 100%; }}
    .fresh-cosbot-label {{
      margin-top: -13px;
      background: linear-gradient(90deg, ${{config.primaryColor}} 0%, #D97706 100%);
      color: #FFFFFF; font-size: 11px; font-weight: 700; letter-spacing: -0.3px;
      padding: 3px 10px; border-radius: 999px; border: 1.5px solid #FFFFFF;
      box-shadow: 0 4px 12px rgba(15, 23, 42, 0.18); white-space: nowrap; z-index: 2;
    }}
    .fresh-widget-launcher.shape-sticker {{
      width: 72px; height: 72px; background: transparent; display: flex; flex-direction: column; align-items: center;
      filter: drop-shadow(0 6px 14px rgba(15,23,42,0.18));
    }}
    .fresh-widget-launcher.shape-sticker svg {{ width: 64px; height: 64px; }}
    .fresh-widget-launcher.shape-circle {{
      width: 64px; height: 64px; border-radius: 50%; background: transparent;
      filter: drop-shadow(0 6px 16px rgba(15, 23, 42, 0.22)); display: flex; align-items: center; justify-content: center;
    }}
    .fresh-widget-launcher.shape-circle svg {{ width: 64px; height: 64px; }}
    .fresh-widget-launcher.shape-pill {{
      background: #FFFFFF; border: 1.5px solid #E5D5B5; border-radius: 999px;
      padding: 6px 16px 6px 8px; display: flex; align-items: center; gap: 8px;
      box-shadow: 0 8px 22px rgba(15, 23, 42, 0.14); color: #141413; font-size: 13.5px; font-weight: 700;
    }}
    .fresh-widget-launcher.shape-pill svg {{ width: 38px; height: 38px; }}
    .fresh-bot-avatar-img {{ width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }}

    /* Base Chat Window */
    .fresh-widget-window {{
      position: fixed; bottom: {win_bottom_px}px; {horiz_css} width: 520px; height: 700px;
      max-width: calc(100vw - 32px); max-height: calc(100vh - {win_bottom_px + 20}px);
      background: #ffffff; border-radius: 22px;
      border: 1px solid rgba(197, 160, 89, 0.28);
      box-shadow: 0 24px 60px rgba(15, 23, 42, 0.24);
      display: none; flex-direction: column; z-index: 999999; overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", Roboto, sans-serif;
      transition: bottom 0.22s ease, left 0.22s ease, right 0.22s ease;
    }}
    .fresh-widget-header {{
      background: linear-gradient(135deg, ${{config.primaryColor}} 0%, #2563EB 100%); color: #ffffff; padding: 15px 18px;
      display: flex; justify-content: space-between; align-items: center;
    }}
    .fresh-widget-window.tpl-cosraw_grid .fresh-widget-header {{
      background: linear-gradient(135deg, ${{config.primaryColor}} 0%, #3B82F6 100%);
    }}
    .fresh-header-left {{ display: flex; align-items: center; gap: 10px; }}
    .fresh-brand-pill {{
      background: rgba(255, 255, 255, 0.22); backdrop-filter: blur(4px); color: #FFFFFF; font-size: 12px; font-weight: 700;
      padding: 4px 10px; border-radius: 6px; letter-spacing: -0.2px;
    }}
    .fresh-widget-window.tpl-cosraw_grid .fresh-brand-pill {{
      background: #0284C7;
    }}
    .fresh-header-main-title {{ margin: 0; font-size: 16px; font-weight: 700; color: #FFFFFF; }}
    .fresh-header-controls {{ display: flex; align-items: center; gap: 14px; color: #CBD5E1; }}
    .fresh-widget-close {{ cursor: pointer; font-size: 22px; line-height: 1; opacity: 0.85; }}
    .fresh-widget-close:hover {{ opacity: 1; color: #FFFFFF; }}

    /* Template Overrides (10 Commercial UX Templates) */
    /* 2. floating_hero (첨부자료 1: 딥 히어로 헤더 + 겹침 플로팅 카드) */
    .fresh-widget-window.tpl-floating_hero .fresh-widget-header {{
      background: linear-gradient(135deg, #1E3A8A 0%, ${{config.primaryColor}} 100%);
      padding: 22px 18px 34px;
    }}
    .fresh-hero-floating-card {{
      margin-top: -28px; margin-bottom: 6px; background: #FFFFFF; border-radius: 14px;
      padding: 14px; box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12); border: 1px solid #E2E8F0;
    }}
    /* 3. app_icon_matrix (첨부자료 2: 3x2 원형 컬러 아이콘 그리드 런처) */
    .fresh-icon-matrix {{
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; width: 96%; margin-top: 4px;
    }}
    .fresh-matrix-item {{
      background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 10px 6px;
      display: flex; flex-direction: column; align-items: center; gap: 6px; cursor: pointer;
      font-size: 11.5px; font-weight: 600; color: #1E293B; text-align: center;
      transition: transform 0.15s, border-color 0.15s;
    }}
    .fresh-matrix-item:hover {{ transform: translateY(-2px); border-color: ${{config.primaryColor}}; }}
    .fresh-matrix-circle {{
      width: 34px; height: 34px; border-radius: 50%; background: #EFF6FF;
      display: flex; align-items: center; justify-content: center; font-size: 16px;
    }}
    /* 4. tabbed_portal (첨부자료 IA: 상단 [홈 / AI상담 / A/S접수] 탭 바) */
    .fresh-portal-tabs {{
      display: flex; background: #F1F5F9; padding: 4px; border-radius: 10px; margin-bottom: 6px; width: 94%;
    }}
    .fresh-portal-tab {{
      flex: 1; text-align: center; padding: 6px 0; font-size: 12px; font-weight: 700;
      border-radius: 8px; cursor: pointer; color: #64748B;
    }}
    .fresh-portal-tab.active {{ background: #FFFFFF; color: #0F172A; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
    /* 5. step_wizard (단계별 피부문진 / A/S 자가진단 스텝퍼) */
    .fresh-step-bar {{
      display: flex; align-items: center; justify-content: space-between;
      background: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 10px;
      padding: 8px 12px; font-size: 11.5px; font-weight: 700; color: #1D4ED8; width: 92%;
    }}
    /* 6. kakao_yellow (카카오톡 알림톡 감성 옐로우 & 파스텔블루) */
    .fresh-widget-window.tpl-kakao_yellow .fresh-widget-header {{
      background: #FEE500; color: #191919;
    }}
    .fresh-widget-window.tpl-kakao_yellow .fresh-header-main-title {{ color: #191919; }}
    .fresh-widget-window.tpl-kakao_yellow .fresh-brand-pill {{ background: #191919; color: #FEE500; }}
    .fresh-widget-window.tpl-kakao_yellow .fresh-widget-body {{ background: #BACEE0; }}
    .fresh-widget-window.tpl-kakao_yellow .fresh-msg.user {{ background: #FEE500; color: #191919; font-weight: 600; }}
    /* 7. channel_card & 8. commerce_showcase */
    .fresh-widget-window.tpl-channel_card .fresh-widget-header,
    .fresh-widget-window.tpl-commerce_showcase .fresh-widget-header {{
      background: linear-gradient(135deg, ${{config.primaryColor}} 0%, #6366F1 100%);
    }}
    /* 9. glass_dark */
    .fresh-widget-window.tpl-glass_dark {{ background: #0F172A; border: 1px solid #1E293B; }}
    .fresh-widget-window.tpl-glass_dark .fresh-widget-body {{ background: #0B1120; color: #F1F5F9; }}
    .fresh-widget-window.tpl-glass_dark .fresh-msg.bot {{ background: #1E293B; color: #F8FAFC; border-color: #334155; }}
    .fresh-widget-window.tpl-glass_dark .fresh-cosraw-btn {{ background: #1E293B; color: #E2E8F0; border-color: #334155; }}
    .fresh-widget-window.tpl-glass_dark .fresh-bot-meta-name {{ color: #E2E8F0; }}
    .fresh-widget-window.tpl-glass_dark .fresh-widget-footer,
    .fresh-widget-window.tpl-glass_dark .fresh-contact-bar {{ background: #0F172A; border-top-color: #1E293B; color: #94A3B8; }}
    /* 10. luxury_editorial (명품 블랙 & 골드) */
    .fresh-widget-window.tpl-luxury_editorial .fresh-widget-header {{
      background: #09090B; border-bottom: 1.5px solid #D4AF37;
    }}
    .fresh-widget-window.tpl-luxury_editorial .fresh-brand-pill {{
      background: #D4AF37; color: #09090B;
    }}
    .fresh-widget-window.tpl-luxury_editorial .fresh-cosraw-btn {{
      border-color: #D4AF37; color: #18181B; background: #FFFBEB;
    }}

    .fresh-widget-banner {{
      padding: 10px 14px; font-size: 12px; font-weight: 600; line-height: 1.4;
      border-bottom: 1px solid #FDE68A; background: #FFFBEB; color: #92400E;
    }}
    .fresh-widget-banner.expired {{ background: #FEF2F2; border-bottom-color: #FECACA; color: #991B1B; }}
    .fresh-widget-body {{
      flex: 1; padding: 18px 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; background: #F8FAFC;
    }}
    .fresh-bot-block {{ display: flex; flex-direction: column; align-items: flex-start; gap: 6px; width: 100%; }}
    .fresh-bot-meta {{ display: flex; align-items: center; gap: 7px; }}
    .fresh-bot-sq-avatar {{
      width: 28px; height: 28px; border-radius: 50%; background: transparent;
      display: flex; align-items: center; justify-content: center; overflow: hidden;
    }}
    .fresh-bot-sq-avatar svg {{ width: 28px; height: 28px; }}
    .fresh-bot-meta-name {{ font-size: 12.5px; font-weight: 700; color: #1E293B; }}
    .fresh-bot-meta-time {{ font-size: 11.5px; color: #94A3B8; }}
    .fresh-msg {{
      max-width: 88%; padding: 13px 16px; border-radius: 14px; font-size: 14px; line-height: 1.55;
      word-break: keep-all; overflow-wrap: break-word; white-space: pre-wrap;
    }}
    .fresh-msg.bot {{
      background: #FFFFFF; color: #1E293B; border: 1px solid #E2E8F0;
      box-shadow: 0 1px 3px rgba(0,0,0,0.03); border-top-left-radius: 4px;
    }}
    .fresh-msg.user {{ background: ${{config.primaryColor}}; color: #FFFFFF; align-self: flex-end; border-bottom-right-radius: 4px; }}
    .fresh-cosraw-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; width: 94%; margin-top: 2px; }}
    .fresh-cosraw-btn {{
      background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 10px; padding: 11px 10px;
      font-size: 13px; font-weight: 600; color: #1E293B; cursor: pointer; text-align: center;
      transition: all 0.15s ease; box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }}
    .fresh-cosraw-btn:hover {{ border-color: #0284C7; background: #F0F9FF; color: #0284C7; }}
    .fresh-cosraw-btn.full-span {{ grid-column: 1 / -1; }}
    .fresh-chips-row {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }}
    .fresh-chip {{
      background: #EFF6FF; border: 1px solid #BFDBFE; color: #1D4ED8;
      border-radius: 999px; padding: 6px 12px; font-size: 12px; font-weight: 600; cursor: pointer;
      word-break: keep-all; overflow-wrap: break-word; text-align: left;
    }}
    .fresh-showcase-banner {{
      background: linear-gradient(90deg, #FDF2F8 0%, #FCE7F3 100%);
      border: 1px solid #FBCFE8; border-radius: 12px; padding: 10px 12px; font-size: 12px; color: #831843; width: 94%;
    }}
    .fresh-product-card {{
      background: #FFFFFF; border: 1px solid #E5E7EB; border-left: 4px solid ${{config.primaryColor}};
      border-radius: 10px; padding: 12px; max-width: 88%; align-self: flex-start;
      box-shadow: 0 2px 6px rgba(0,0,0,0.05); font-size: 13px;
    }}
    .fresh-product-card h4 {{ margin: 0 0 4px 0; font-size: 14px; color: #111827; }}
    .fresh-product-card .price {{ font-weight: 700; color: ${{config.primaryColor}}; margin-bottom: 6px; }}
    .fresh-product-card .buy-link {{
      display: inline-block; margin-top: 8px; background: ${{config.primaryColor}}; color: #FFFFFF;
      text-decoration: none; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600;
    }}
    .fresh-contact-bar {{
      background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 7px 14px;
      text-align: center; font-size: 11.5px; color: #64748B;
    }}
    .fresh-contact-bar a {{ color: #4F46E5; text-decoration: underline; }}
    .fresh-widget-footer {{
      padding: 10px 12px 12px; border-top: 1px solid #E2E8F0; background: #FFFFFF;
      display: flex; flex-direction: column; gap: 6px;
    }}
    .fresh-input-row {{ display: flex; gap: 8px; align-items: center; }}
    .fresh-input {{
      flex: 1; border: 1.5px solid #0284C7; border-radius: 999px;
      padding: 10px 16px; font-size: 13.5px; outline: none; color: #1E293B;
    }}
    .fresh-btn-send {{
      width: 40px; height: 40px; border-radius: 50%; background: ${{config.primaryColor}}; color: #ffffff;
      border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0;
      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.12);
    }}
    .fresh-btn-send svg {{ width: 18px; height: 18px; fill: #FFFFFF; margin-left: 2px; }}
    .fresh-upload-btn {{
      background: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 8px; padding: 5px 10px;
      font-size: 11.5px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; color: #475569;
    }}
    .fresh-order-lookup-box {{
      background: linear-gradient(145deg, #FFFDF9 0%, #FFF8EC 100%);
      border: 1.5px solid #E5C17B; border-radius: 14px; padding: 13px 14px;
      width: 100%; box-sizing: border-box;
      box-shadow: 0 4px 14px rgba(180, 83, 9, 0.08);
      display: flex; flex-direction: column; gap: 8px;
    }}
    .fresh-order-box-header {{
      display: flex; justify-content: space-between; align-items: center; gap: 6px;
    }}
    .fresh-order-box-title {{
      font-size: 13.5px; font-weight: 800; color: #1E293B; letter-spacing: -0.2px;
    }}
    .fresh-order-box-badge {{
      font-size: 10.5px; font-weight: 800; color: #92400E;
      background: #FEF3C7; border: 1px solid #FDE68A;
      padding: 2.5px 8px; border-radius: 999px; white-space: nowrap;
    }}
    .fresh-order-box-desc {{
      font-size: 11.5px; color: #64748B; line-height: 1.4;
    }}
    .fresh-order-box-row {{
      display: flex; gap: 6px; align-items: center;
    }}
    .fresh-order-input {{
      flex: 1; height: 36px; border: 1.5px solid #CBD5E1; border-radius: 9px;
      padding: 0 11px; font-size: 12.5px; outline: none; background: #FFFFFF; color: #1E293B;
      box-sizing: border-box;
    }}
    .fresh-order-input:focus {{ border-color: ${{config.primaryColor}}; box-shadow: 0 0 0 2px rgba(2,132,199,0.12); }}
    .fresh-order-btn {{
      height: 36px; padding: 0 13px; border-radius: 9px; border: none;
      background: ${{config.primaryColor}}; color: #FFFFFF;
      font-size: 12.5px; font-weight: 800; cursor: pointer; white-space: nowrap;
    }}
    .fresh-order-quick-row {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 2px;
    }}
    .fresh-order-mini-btn {{
      background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px;
      padding: 6.5px 8px; font-size: 11.5px; font-weight: 700; color: #334155;
      cursor: pointer; text-align: center; transition: all 0.15s ease;
    }}
    .fresh-order-mini-btn:hover {{
      border-color: ${{config.primaryColor}}; color: ${{config.primaryColor}}; background: #F8FAFC;
    }}
  `;
  document.head.appendChild(style);

  // Build Launcher
  const launcher = document.createElement("div");
  launcher.className = "fresh-widget-launcher shape-" + config.launcherShape;

  if (config.launcherShape === "cosbot_badge") {{
    launcher.innerHTML = `
      <div class="fresh-cosbot-ring"><div class="fresh-cosbot-inner">${{iconGraphicHtml}}</div></div>
      <div class="fresh-cosbot-label">${{config.botLabel}}</div>
    `;
  }} else if (config.launcherShape === "pill") {{
    launcher.innerHTML = `<div class="fresh-bot-sq-avatar">${{iconGraphicHtml}}</div><span>${{config.botLabel}}</span>`;
  }} else if (config.launcherShape === "sticker") {{
    launcher.innerHTML = `${{iconGraphicHtml}}<div class="fresh-cosbot-label" style="margin-top:-6px;">${{config.botLabel}}</div>`;
  }} else {{
    launcher.innerHTML = iconGraphicHtml;
  }}

  let bannerHtml = "";
  if (config.isExpired) {{
    bannerHtml = `<div class="fresh-widget-banner expired">⛔ [기간 만료 안내] ${{config.statusMessage}}</div>`;
  }} else if (config.expiryWarning) {{
    bannerHtml = `<div class="fresh-widget-banner">${{config.statusMessage}}</div>`;
  }}

  const initialBodyMessage = config.isExpired
    ? "⛔ <b>[서비스 이용기간 만료 안내]</b><br>무료 체험(또는 구독) 사용기한이 만료되어 AI 상담 및 사진 판독 기능이 일시 중단되었습니다.<br><br>스토어 관리자께서는 챗봇공장 관리자에게 기한 연장을 요청해 주시기 바랍니다."
    : config.welcomeMessage.replace(/\\n/g, "<br>");

  const disabledAttr = config.isExpired ? "disabled" : "";
  const inputPlaceholder = config.isExpired ? "사용기한이 만료되어 입력할 수 없습니다." : config.inputPlaceholder;

  // Build Template-Specific Header/Top & Quick Action Area (10 Commercial Templates)
  let orderLookupBoxHtml = "";
  if (config.commercePlatform && config.commercePlatform !== "none") {{
    orderLookupBoxHtml = `
      <div class="fresh-order-lookup-box">
        <div class="fresh-order-box-header">
          <span class="fresh-order-box-title">📦 실시간 주문 · 배송 · A/S 조회</span>
          <span class="fresh-order-box-badge">${{config.commerceBadge}}</span>
        </div>
        <div class="fresh-order-box-desc">주문번호를 입력하시면 실시간 배송 상태와 반품·교환·A/S 가능 여부를 즉시 확인합니다.</div>
        <div class="fresh-order-box-row">
          <input type="text" id="dyn-order-input" class="fresh-order-input" placeholder="주문번호 입력 (예: ORD-NORMAL)" ${{disabledAttr}} />
          <button type="button" id="dyn-order-btn" class="fresh-order-btn" ${{disabledAttr}}>🔍 조회</button>
        </div>
        <div class="fresh-order-quick-row">
          <button type="button" class="fresh-order-mini-btn" data-order-q="ORD-NORMAL" ${{disabledAttr}}>🚚 내 주문·배송 조회</button>
          <button type="button" class="fresh-order-mini-btn" data-q="📸 사진 판독" ${{disabledAttr}}>📸 파손·불량 A/S 접수</button>
        </div>
      </div>
    `;
  }}

  let topExtraHtml = "";
  let templateQuickAreaHtml = "";
  const btns = config.quickButtons || [];

  if (!config.isExpired && btns.length > 0) {{
    if (config.chatTemplate === "floating_hero") {{
      const gridItems = btns.map((label, idx) => {{
        const spanClass = (idx === btns.length - 1 && btns.length % 2 === 1) ? "full-span" : "";
        return `<button type="button" class="fresh-cosraw-btn ${{spanClass}}" data-q="${{label}}">${{label}}</button>`;
      }}).join("");
      topExtraHtml = `<div class="fresh-hero-floating-card"><b>✨ ${{config.title}} VIP 라운지</b><br><span style="font-size:12px;color:#64748B;">원하시는 빠른 서비스를 선택해 주세요.</span></div>`;
      templateQuickAreaHtml = `<div class="fresh-cosraw-grid">${{gridItems}}</div>`;
    }} else if (config.chatTemplate === "app_icon_matrix") {{
      const matrixItems = btns.map(label => {{
        const emoji = Array.from(label)[0] || "✨";
        const textOnly = label.slice(emoji.length).trim() || label;
        return `<div class="fresh-matrix-item" data-q="${{label}}"><div class="fresh-matrix-circle">${{emoji}}</div><span>${{textOnly}}</span></div>`;
      }}).join("");
      templateQuickAreaHtml = `<div class="fresh-icon-matrix">${{matrixItems}}</div>`;
    }} else if (config.chatTemplate === "tabbed_portal") {{
      topExtraHtml = `
        <div class="fresh-portal-tabs">
          <div class="fresh-portal-tab active">🏠 홈 메뉴</div>
          <div class="fresh-portal-tab">💬 실시간 상담</div>
          <div class="fresh-portal-tab" data-q="📸 사진 판독">📸 A/S 판독</div>
        </div>
      `;
      const gridItems = btns.map((label, idx) => {{
        const spanClass = (idx === btns.length - 1 && btns.length % 2 === 1) ? "full-span" : "";
        return `<button type="button" class="fresh-cosraw-btn ${{spanClass}}" data-q="${{label}}">${{label}}</button>`;
      }}).join("");
      templateQuickAreaHtml = `<div class="fresh-cosraw-grid">${{gridItems}}</div>`;
    }} else if (config.chatTemplate === "step_wizard") {{
      topExtraHtml = `<div class="fresh-step-bar"><span>STEP 1. 상담 유형 선택</span><span>➔</span><span>STEP 2. AI 맞춤 진단</span></div>`;
      const gridItems = btns.map((label, idx) => {{
        const spanClass = (idx === btns.length - 1 && btns.length % 2 === 1) ? "full-span" : "";
        return `<button type="button" class="fresh-cosraw-btn ${{spanClass}}" data-q="${{label}}">${{label}}</button>`;
      }}).join("");
      templateQuickAreaHtml = `<div class="fresh-cosraw-grid">${{gridItems}}</div>`;
    }} else if (config.chatTemplate === "commerce_showcase") {{
      const chipItems = btns.map(label => `<button type="button" class="fresh-chip" data-q="${{label}}">${{label}}</button>`).join("");
      templateQuickAreaHtml = `
        <div class="fresh-showcase-banner">✨ <b>${{config.botName}}</b> 맞춤 추천 & 실시간 인기 카운슬링</div>
        <div class="fresh-chips-row">${{chipItems}}</div>
      `;
    }} else if (config.chatTemplate === "channel_card" || config.chatTemplate === "minimal_clean") {{
      const chipItems = btns.map(label => `<button type="button" class="fresh-chip" data-q="${{label}}">${{label}}</button>`).join("");
      templateQuickAreaHtml = `<div class="fresh-chips-row">${{chipItems}}</div>`;
    }} else {{
      // Default: cosraw_grid, glass_dark, kakao_yellow, luxury_editorial
      const btnItems = btns.map((label, idx) => {{
        const isLastOdd = (idx === btns.length - 1) && (btns.length % 2 === 1);
        const spanClass = isLastOdd ? "full-span" : "";
        return `<button type="button" class="fresh-cosraw-btn ${{spanClass}}" data-q="${{label}}">${{label}}</button>`;
      }}).join("");
      templateQuickAreaHtml = `<div class="fresh-cosraw-grid">${{btnItems}}</div>`;
    }}
  }}

  const chatWindow = document.createElement("div");
  chatWindow.className = "fresh-widget-window tpl-" + config.chatTemplate;
  chatWindow.innerHTML = `
    <div class="fresh-widget-header">
      <div class="fresh-header-left">
        <span class="fresh-brand-pill">${{config.brandBadge}}</span>
        <h3 class="fresh-header-main-title">${{config.headerTitle}}</h3>
      </div>
      <div class="fresh-header-controls">
        <span style="font-size:16px;letter-spacing:1px;">&middot;&middot;&middot;</span>
        <div class="fresh-widget-close" id="dyn-close">&times;</div>
      </div>
    </div>
    ${{bannerHtml}}
    <div class="fresh-widget-body" id="dyn-messages">
      ${{orderLookupBoxHtml}}
      ${{topExtraHtml}}
      <div class="fresh-bot-block">
        <div class="fresh-bot-meta">
          <div class="fresh-bot-sq-avatar">${{iconGraphicHtml}}</div>
          <span class="fresh-bot-meta-name">AI 챗봇 (${{config.botName}})</span>
          <span class="fresh-bot-meta-time">방금 전</span>
        </div>
        <div class="fresh-msg bot">${{initialBodyMessage}}</div>
        ${{templateQuickAreaHtml}}
      </div>
    </div>
    <div class="fresh-contact-bar">
      고객문의 <a href="mailto:${{config.contactEmail}}">${{config.contactEmail}}</a> &middot; ${{config.businessHours}}
    </div>
    <div class="fresh-widget-footer">
      <input type="file" id="dyn-file" accept="image/*" style="display:none;" ${{disabledAttr}} />
      <button class="fresh-upload-btn" id="dyn-upload-btn" ${{disabledAttr}}>${{config.uploadGuide}}</button>
      <div class="fresh-input-row">
        <input type="text" class="fresh-input" id="dyn-input" placeholder="${{inputPlaceholder}}" ${{disabledAttr}} />
        <button class="fresh-btn-send" id="dyn-send" ${{disabledAttr}} title="전송">
          <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
        </button>
      </div>
    </div>
  `;

  document.body.appendChild(launcher);
  document.body.appendChild(chatWindow);

  const messagesContainer = chatWindow.querySelector("#dyn-messages");
  const userInput = chatWindow.querySelector("#dyn-input");
  const sendBtn = chatWindow.querySelector("#dyn-send");
  const fileInput = chatWindow.querySelector("#dyn-file");
  const uploadBtn = chatWindow.querySelector("#dyn-upload-btn");
  const closeBtn = chatWindow.querySelector("#dyn-close");

  launcher.addEventListener("click", () => {{
    chatWindow.style.display = chatWindow.style.display === "flex" ? "none" : "flex";
    if (chatWindow.style.display === "flex" && !config.isExpired) userInput.focus();
  }});
  closeBtn.addEventListener("click", () => {{ chatWindow.style.display = "none"; }});

  chatWindow.querySelectorAll("[data-q]").forEach(btn => {{
    btn.addEventListener("click", () => {{
      const qText = btn.getAttribute("data-q");
      if (qText.includes("사진") || qText.includes("판독")) {{
        fileInput.click();
      }} else if (qText.includes("다른 질문")) {{
        userInput.focus();
      }} else {{
        userInput.value = qText;
        sendMessage();
      }}
    }});
  }});

  const orderInput = chatWindow.querySelector("#dyn-order-input");
  const orderBtn = chatWindow.querySelector("#dyn-order-btn");
  function runOrderBoxLookup(overrideOrderNo) {{
    if (config.isExpired) return;
    const val = (overrideOrderNo || (orderInput ? orderInput.value.trim() : "")).trim();
    if (!val) {{
      if (orderInput) {{
        orderInput.focus();
        orderInput.style.borderColor = "#EA580C";
        setTimeout(() => {{ orderInput.style.borderColor = ""; }}, 1400);
      }}
      return;
    }}
    if (orderInput) orderInput.value = "";
    userInput.value = "주문/배송 조회 요청 (" + val + ")";
    sendMessage();
  }}
  if (orderBtn) {{
    orderBtn.addEventListener("click", () => runOrderBoxLookup());
  }}
  if (orderInput) {{
    orderInput.addEventListener("keydown", (e) => {{
      if (e.key === "Enter") runOrderBoxLookup();
    }});
  }}
  chatWindow.querySelectorAll("[data-order-q]").forEach(btn => {{
    btn.addEventListener("click", () => {{
      const sampleOrd = btn.getAttribute("data-order-q") || "ORD-NORMAL";
      runOrderBoxLookup(sampleOrd);
    }});
  }});

  function appendMessage(text, sender) {{
    if (sender === "bot") {{
      const block = document.createElement("div");
      block.className = "fresh-bot-block";
      block.innerHTML = `
        <div class="fresh-bot-meta">
          <div class="fresh-bot-sq-avatar">${{iconGraphicHtml}}</div>
          <span class="fresh-bot-meta-name">AI 챗봇 (${{config.botName}})</span>
          <span class="fresh-bot-meta-time">방금 전</span>
        </div>
      `;
      const msg = document.createElement("div");
      msg.className = "fresh-msg bot";
      msg.innerHTML = text.replace(/\\n/g, "<br>");
      block.appendChild(msg);
      messagesContainer.appendChild(block);
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
      return msg;
    }} else {{
      const msg = document.createElement("div");
      msg.className = "fresh-msg user";
      msg.innerHTML = text.replace(/\\n/g, "<br>");
      messagesContainer.appendChild(msg);
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
      return msg;
    }}
  }}

  function appendProductCards(cards) {{
    if (!cards || !cards.length) return;
    cards.forEach(c => {{
      const cardEl = document.createElement("div");
      cardEl.className = "fresh-product-card";
      const priceHtml = c.price ? `<div class="price">${{c.price.toLocaleString()}}원</div>` : "";
      const linkHtml = c.purchase_url ? `<a class="buy-link" href="${{c.purchase_url}}" target="_blank">🛒 상품 상세 / 바로 구매하기</a>` : "";
      cardEl.innerHTML = `
        <h4>✨ [맞춤 추천] ${{c.title}}</h4>
        ${{priceHtml}}
        <div>${{c.summary}}</div>
        ${{linkHtml}}
      `;
      messagesContainer.appendChild(cardEl);
    }});
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }}

  async function sendMessage() {{
    if (config.isExpired) return;
    const text = userInput.value.trim();
    if (!text) return;
    userInput.value = "";
    appendMessage(text, "user");

    const botMsg = appendMessage("답변을 준비 중입니다...", "bot");
    botMsg.innerHTML = "";

    try {{
      const response = await fetch(config.apiBase + "/api/chat/stream", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          session_id: sessionId,
          mall_id: config.mallId,
          message: text,
          customer_id: "guest"
        }}),
      }});

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullText = "";

      while (true) {{
        const {{ done, value }} = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split("\\n");
        for (const line of lines) {{
          if (line.startsWith("data: ")) {{
            const raw = line.slice(6).trim();
            if (raw === "[DONE]") continue;
            try {{
              const data = JSON.parse(raw);
              if (data.token) {{
                fullText += data.token;
                botMsg.innerHTML = fullText.replace(/\\n/g, "<br>");
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
              }}
              if (data.recommended_products) {{
                appendProductCards(data.recommended_products);
              }}
            }} catch (e) {{}}
          }}
        }}
      }}
    }} catch (err) {{
      botMsg.innerText = "연결 오류가 발생했습니다. 다시 시도해 주세요.";
    }}
  }}

  sendBtn.addEventListener("click", sendMessage);
  userInput.addEventListener("keydown", (e) => {{
    if (e.key === "Enter") sendMessage();
  }});

  uploadBtn.addEventListener("click", () => {{
    if (!config.isExpired) fileInput.click();
  }});
  fileInput.addEventListener("change", async (e) => {{
    if (config.isExpired) return;
    const file = e.target.files[0];
    if (!file) return;

    appendMessage("[A/S 사진 제출] " + file.name + " 진단 중...", "user");
    const analyzingMsg = appendMessage("지능형 Vision AI가 고장/손상 상태를 진단하고 있습니다...", "bot");

    try {{
      const claimResp = await fetch(config.apiBase + "/api/claims", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          mall_id: config.mallId,
          order_id: "ORD-NORMAL",
          customer_id: "guest",
          claim_type: "as_diagnosis",
          description: "A/S 및 품질 진단 요청",
        }}),
      }});
      const claimData = await claimResp.json();

      const formData = new FormData();
      formData.append("file", file);
      const uploadResp = await fetch(config.apiBase + "/api/claims/" + claimData.claim_id + "/images", {{
        method: "POST",
        body: formData,
      }});
      const result = await uploadResp.json();
      analyzingMsg.parentElement.remove();

      appendMessage("<b>[진단 결과: " + result.decision + "]</b><br>" + result.customer_message, "bot");
    }} catch (err) {{
      analyzingMsg.innerText = "진단 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
    }}
  }});
}})();
"""
    return Response(
        content=js_content,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate, max-age=0"},
    )
