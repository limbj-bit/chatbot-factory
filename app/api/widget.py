import json
from typing import Dict, List
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.store_service import INDUSTRY_DEFAULTS, store_service
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/api/widget", tags=["Widget"])


# 16 Commercial-Grade Multi-Color Flaticon-Style Vector Illustrations
FLATICON_PRESET_SVGS: Dict[str, str] = {
    # 1. 코스봇 안테나 로봇 (COSRAWFREE Signature)
    "flaticon_cute_robot": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <line x1="30" y1="9" x2="30" y2="17" stroke="#60A5FA" stroke-width="3" stroke-linecap="round"/>
      <circle cx="30" cy="8" r="4" fill="#38BDF8"/>
      <rect x="13" y="25" width="4" height="12" rx="2" fill="#38BDF8"/>
      <rect x="43" y="25" width="4" height="12" rx="2" fill="#38BDF8"/>
      <rect x="16" y="17" width="28" height="26" rx="10" fill="#FFFFFF" stroke="#60A5FA" stroke-width="2.5"/>
      <rect x="20" y="22" width="20" height="14" rx="6" fill="#0F172A"/>
      <circle cx="25.5" cy="28.5" r="2.5" fill="#38BDF8"/>
      <circle cx="34.5" cy="28.5" r="2.5" fill="#38BDF8"/>
      <path d="M26.5 33C27.5 34.2 32.5 34.2 33.5 33" stroke="#38BDF8" stroke-width="2" stroke-linecap="round"/>
      <rect x="40" y="11" width="16" height="11" rx="5.5" fill="#0284C7"/>
      <circle cx="44.5" cy="16.5" r="1.3" fill="#FFFFFF"/><circle cx="48" cy="16.5" r="1.3" fill="#FFFFFF"/><circle cx="51.5" cy="16.5" r="1.3" fill="#FFFFFF"/>
    </svg>""",
    # 2. 뷰티 스파클 요정봇 (Beauty Fairy)
    "flaticon_beauty_fairy": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M23 17L26 11L30 15L34 11L37 17H23Z" fill="#FBBF24"/>
      <rect x="16" y="17" width="28" height="26" rx="12" fill="#FFF1F2" stroke="#F472B6" stroke-width="2.5"/>
      <rect x="20" y="22" width="20" height="14" rx="6" fill="#831843"/>
      <circle cx="25.5" cy="28.5" r="2.4" fill="#F9A8D4"/><circle cx="34.5" cy="28.5" r="2.4" fill="#F9A8D4"/>
      <circle cx="22.5" cy="31.5" r="1.6" fill="#FB7185"/><circle cx="37.5" cy="31.5" r="1.6" fill="#FB7185"/>
      <path d="M27 32.5C28 33.8 32 33.8 33 32.5" stroke="#F9A8D4" stroke-width="2" stroke-linecap="round"/>
      <path d="M48 11L49.5 14.5L53 16L49.5 17.5L48 21L46.5 17.5L43 16L46.5 14.5L48 11Z" fill="#FDE047"/>
    </svg>""",
    # 3. 헤드셋 CS 여성 매니저
    "flaticon_cs_agent": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M16 28C16 19.1634 23.1634 12 32 12C40.8366 12 48 19.1634 48 28" stroke="#38BDF8" stroke-width="3.5" stroke-linecap="round"/>
      <rect x="13" y="25" width="5" height="11" rx="2.5" fill="#0284C7"/><rect x="46" y="25" width="5" height="11" rx="2.5" fill="#0284C7"/>
      <circle cx="32" cy="29" r="12" fill="#FDE68A"/>
      <path d="M20 26C20 19.5 25.5 16 32 16C38.5 16 44 19.5 44 26C41 23 36 22 32 22C28 22 23 23 20 26Z" fill="#475569"/>
      <circle cx="28" cy="29" r="1.8" fill="#1E293B"/><circle cx="36" cy="29" r="1.8" fill="#1E293B"/>
      <path d="M28.5 34C30 35.5 34 35.5 35.5 34" stroke="#E11D48" stroke-width="2" stroke-linecap="round"/>
      <path d="M47 34C47 38 41 40 35 40" stroke="#0284C7" stroke-width="2" stroke-linecap="round"/>
      <circle cx="34" cy="40" r="2" fill="#0284C7"/>
    </svg>""",
    # 4. 말풍선 윙크봇
    "flaticon_bubble_bot": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M14 26C14 17.7157 21.1634 11 30 11H34C42.8366 11 50 17.7157 50 26C50 34.2843 42.8366 41 34 41H24L16 46V38.5C14.7 36.2 14 31.2 14 26Z" fill="#FFFFFF" stroke="#34D399" stroke-width="2.5"/>
      <circle cx="26" cy="25" r="2.6" fill="#059669"/>
      <path d="M35 25L39 23.5M35 25L39 26.5" stroke="#059669" stroke-width="2.2" stroke-linecap="round"/>
      <path d="M27 31C28.8 33 35.2 33 37 31" stroke="#10B981" stroke-width="2.2" stroke-linecap="round"/>
    </svg>""",
    # 5. 스마트 AI 스파클
    "flaticon_smart_ai": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M32 10L36.5 23.5L50 28L36.5 32.5L32 46L27.5 32.5L14 28L27.5 23.5L32 10Z" fill="#60A5FA" stroke="#EFF6FF" stroke-width="2"/>
      <path d="M46 11L47.5 15.5L52 17L47.5 18.5L46 23L44.5 18.5L40 17L44.5 15.5L46 11Z" fill="#FBBF24"/>
    </svg>""",
    # 6. 더마/원료 연구원 닥터봇 (Doctor / Lab Researcher)
    "flaticon_derma_doctor": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="20" y="10" width="24" height="10" rx="3" fill="#FFFFFF" stroke="#38BDF8" stroke-width="2"/>
      <path d="M32 12V18M29 15H35" stroke="#EF4444" stroke-width="2.5" stroke-linecap="round"/>
      <circle cx="32" cy="30" r="12" fill="#FDE68A"/>
      <rect x="24" y="26" width="7" height="5" rx="1.5" stroke="#0F172A" stroke-width="1.8"/>
      <rect x="33" y="26" width="7" height="5" rx="1.5" stroke="#0F172A" stroke-width="1.8"/>
      <line x1="31" y1="28" x2="33" y2="28" stroke="#0F172A" stroke-width="1.8"/>
      <path d="M29 35C30.5 36.2 33.5 36.2 35 35" stroke="#0F172A" stroke-width="1.8" stroke-linecap="round"/>
      <path d="M18 48C18 42.5 24 40 32 40C40 40 46 42.5 46 48H18Z" fill="#FFFFFF" stroke="#94A3B8" stroke-width="2"/>
    </svg>""",
    # 7. 원료/바이오 플라스크 봇 (Cosmetic Raw Material Lab)
    "flaticon_lab_flask": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M26 14H38M29 14V24L18 42C16.8 44 18.2 46.5 20.6 46.5H43.4C45.8 46.5 47.2 44 46 42L35 24V14" stroke="#38BDF8" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M21 37H43L45.5 41.5C46.5 43.2 45.2 45 43.2 45H20.8C18.8 45 17.5 43.2 18.5 41.5L21 37Z" fill="#34D399"/>
      <circle cx="29" cy="32" r="2" fill="#A7F3D0"/><circle cx="35" cy="29" r="1.5" fill="#A7F3D0"/>
      <circle cx="28" cy="41" r="1.8" fill="#064E3B"/><circle cx="36" cy="41" r="1.8" fill="#064E3B"/>
    </svg>""",
    # 8. 스킨케어 수분 세럼 드롭 (Water Drop Bot)
    "flaticon_serum_drop": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M32 11C32 11 17 28 17 38C17 46.2843 23.7157 53 32 53C40.2843 53 47 46.2843 47 38C47 28 32 11 32 11Z" fill="#38BDF8" stroke="#BAE6FD" stroke-width="2.5"/>
      <circle cx="27" cy="36" r="2.2" fill="#FFFFFF"/><circle cx="37" cy="36" r="2.2" fill="#FFFFFF"/>
      <path d="M28.5 41.5C30 43 34 43 35.5 41.5" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round"/>
      <ellipse cx="24" cy="29" rx="2" ry="4" transform="rotate(25 24 29)" fill="#E0F2FE"/>
    </svg>""",
    # 9. 럭셔리 골드 크라운 봇 (VIP Luxury Brand)
    "flaticon_luxury_crown": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M14 42L18 22L27 31L32 18L37 31L46 22L50 42H14Z" fill="#FBBF24" stroke="#FEF08A" stroke-width="2" stroke-linejoin="round"/>
      <rect x="14" y="44" width="36" height="4" rx="2" fill="#D97706"/>
      <circle cx="18" cy="19" r="2.5" fill="#FDE047"/><circle cx="32" cy="15" r="3" fill="#FDE047"/><circle cx="46" cy="19" r="2.5" fill="#FDE047"/>
      <circle cx="27" cy="36" r="1.8" fill="#78350F"/><circle cx="37" cy="36" r="1.8" fill="#78350F"/>
    </svg>""",
    # 10. 사이버 네온 로봇 (Cyber Tech Bot)
    "flaticon_cyber_bot": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <polygon points="32,10 50,20 50,42 32,52 14,42 14,20" fill="#1E1B4B" stroke="#A855F7" stroke-width="2.5"/>
      <rect x="20" y="25" width="24" height="10" rx="5" fill="#090D16" stroke="#22D3EE" stroke-width="2"/>
      <circle cx="27" cy="30" r="2.2" fill="#22D3EE"/><circle cx="37" cy="30" r="2.2" fill="#F43F5E"/>
      <line x1="26" y1="40" x2="38" y2="40" stroke="#A855F7" stroke-width="2.5" stroke-linecap="round"/>
    </svg>""",
    # 11. 친근한 강아지 마스코트 봇 (Friendly Pet/Mascot)
    "flaticon_cute_puppy": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="16" cy="28" rx="5" ry="10" transform="rotate(-15 16 28)" fill="#D97706"/>
      <ellipse cx="48" cy="28" rx="5" ry="10" transform="rotate(15 48 28)" fill="#D97706"/>
      <circle cx="32" cy="32" r="14" fill="#FDE68A" stroke="#F59E0B" stroke-width="2"/>
      <circle cx="27" cy="29" r="2.2" fill="#451A03"/><circle cx="37" cy="29" r="2.2" fill="#451A03"/>
      <ellipse cx="32" cy="34" rx="3" ry="2" fill="#451A03"/>
      <path d="M29 38C30.5 39.5 33.5 39.5 35 38" stroke="#451A03" stroke-width="2" stroke-linecap="round"/>
    </svg>""",
    # 12. 귀여운 고양이 집사 봇 (Cat Butler Bot)
    "flaticon_cat_butler": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M18 28L16 14L27 21H37L48 14L46 28" fill="#F8FAFC" stroke="#94A3B8" stroke-width="2"/>
      <circle cx="32" cy="33" r="14" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="2"/>
      <circle cx="26.5" cy="31" r="2.2" fill="#0F172A"/><circle cx="37.5" cy="31" r="2.2" fill="#0F172A"/>
      <polygon points="32,34 30,36.5 34,36.5" fill="#FB7185"/>
      <path d="M28 45L32 42L36 45L32 48L28 45Z" fill="#E11D48"/>
    </svg>""",
    # 13. 쇼핑백 & 선물 컨시어지 (Shopping Concierge)
    "flaticon_shopping_bag": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M24 22V18C24 13.5817 27.5817 10 32 10C36.4183 10 40 13.5817 40 18V22" stroke="#F472B6" stroke-width="3" stroke-linecap="round"/>
      <rect x="16" y="21" width="32" height="28" rx="6" fill="#EC4899" stroke="#FBCFE8" stroke-width="2"/>
      <circle cx="27" cy="33" r="2.3" fill="#FFFFFF"/><circle cx="37" cy="33" r="2.3" fill="#FFFFFF"/>
      <path d="M28.5 38.5C30 40 34 40 35.5 38.5" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round"/>
    </svg>""",
    # 14. 프레시 오가닉 사과/새싹 봇 (Fresh Organic Bot)
    "flaticon_fresh_leaf": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M32 12C35 8 41 9 41 13C41 17 35 17 32 15" fill="#4ADE80"/>
      <circle cx="32" cy="33" r="15" fill="#22C55E" stroke="#BBF7D0" stroke-width="2"/>
      <circle cx="27" cy="31" r="2.3" fill="#FFFFFF"/><circle cx="37" cy="31" r="2.3" fill="#FFFFFF"/>
      <path d="M28 37C30 39 34 39 36 37" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round"/>
    </svg>""",
    # 15. 안심 보증 실드 가디언 봇 (Trust Shield A/S Bot)
    "flaticon_shield_as": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M32 11L48 17V30C48 41.5 41 49.5 32 53C23 49.5 16 41.5 16 30V17L32 11Z" fill="#2563EB" stroke="#93C5FD" stroke-width="2.5"/>
      <path d="M25 32L30 37L40 26" stroke="#FFFFFF" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>""",
    # 16. 카카오톡 감성 옐로우 톡봇 (Yellow Talk Bot)
    "flaticon_yellow_talk": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="32" cy="30" rx="18" ry="15" fill="#FACC15" stroke="#FEF08A" stroke-width="2"/>
      <path d="M22 42L16 48L27 44" fill="#FACC15"/>
      <circle cx="26.5" cy="29" r="2.3" fill="#3B1E1E"/><circle cx="37.5" cy="29" r="2.3" fill="#3B1E1E"/>
      <path d="M29 34.5C30.5 36 33.5 36 35 34.5" stroke="#3B1E1E" stroke-width="2.2" stroke-linecap="round"/>
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
    session: AsyncSession = Depends(get_db),
):
    """Serve a dynamically customized JavaScript widget with 10 Commercial Chat Window Templates & 16 Flaticon Avatars."""
    store = await store_service.get_store_by_mall_id(session, mall_id)

    origin_or_referer = request.headers.get("origin") or request.headers.get("referer")
    if not store_service.is_domain_allowed(store, origin_or_referer):
        blocked_js = f'console.warn("[ChatbotFactory] Unauthorized domain for mall_id={mall_id}. Allowed domains: {store.allowed_domains if store else ""}");'
        return Response(content=blocked_js, media_type="application/javascript")

    title = preview_store_name or (store.store_name if store else "코스라프리")
    industry = preview_industry or (store.industry if store else "general")
    ind_defaults = INDUSTRY_DEFAULTS.get(industry, INDUSTRY_DEFAULTS["general"])
    theme_color = store.theme_color if store else ind_defaults.get("theme_color", "#0284C7")
    bot_name = preview_bot_name or (store.bot_name if store and store.bot_name else ind_defaults.get("bot_name", "코스봇"))
    brand_badge = preview_badge or (store.brand_badge if store and store.brand_badge else title[:8])
    header_title = (store.header_title if store and store.header_title else "고객상담센터")
    chat_template = preview_template or (store.chat_template if store and store.chat_template else "cosraw_grid")
    contact_email = (store.contact_email if store and store.contact_email else ind_defaults.get("contact_email", "contact@cosrawfree.com"))
    business_hours = (store.business_hours if store and store.business_hours else "평일 09:00~18:00")
    input_placeholder = (
        store.input_placeholder
        if store and store.input_placeholder
        else ind_defaults.get("input_placeholder", "궁금한 성분명(예: 레티놀)이나 질문을 입력하세요...")
    )

    quick_buttons: List[str] = []
    if store and store.quick_buttons_json and not preview_industry:
        try:
            quick_buttons = json.loads(store.quick_buttons_json)
        except Exception:
            quick_buttons = []
    if not quick_buttons:
        quick_buttons = ind_defaults.get("quick_buttons", [])

    welcome_msg = (
        store.welcome_message.replace("\n", "\\n")
        if store and store.welcome_message and not preview_store_name and not preview_bot_name
        else f"안녕하세요. {title}의 AI 상담사 <b>'{bot_name}'</b> 입니다. 🧪\\n어떤 원료나 서비스가 궁금하신가요?"
    )

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

    upload_guide = "📷 손상 상품 사진 업로드 접수"
    if industry == "electronics":
        upload_guide = "🔧 고장/파손 부위 사진 및 A/S 진단 요청"
    elif industry == "fashion":
        upload_guide = "👗 원단 오염/봉제 불량 사진 교환 접수"
    elif industry == "beauty":
        upload_guide = "💄 용기 누유/파손 및 트러블 사진 진단 접수"

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
    isExpired: {is_expired_js},
    expiryWarning: {expiry_warning_js},
    remainingDays: {remaining_days_js},
    statusMessage: "{safe_status_msg}",
    apiBase: window.location.origin
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
      bottom: 24px;
      right: 24px;
      cursor: pointer;
      z-index: 999999;
      user-select: none;
      font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", Roboto, sans-serif;
      animation: cosbotFloat 3.2s ease-in-out infinite;
      transition: filter 0.2s ease, transform 0.2s ease;
    }}
    .fresh-widget-launcher:hover {{ filter: brightness(1.06); transform: scale(1.05); }}
    .fresh-widget-launcher.shape-cosbot_badge {{
      width: 78px; height: 84px; display: flex; flex-direction: column; align-items: center; justify-content: flex-start;
    }}
    .fresh-cosbot-ring {{
      width: 68px; height: 68px; border-radius: 50%; padding: 3.5px;
      background: linear-gradient(145deg, #E0F2FE 0%, #38BDF8 50%, ${{config.primaryColor}} 100%);
      box-shadow: 0 8px 22px rgba(15, 23, 42, 0.28), inset 0 1px 2px rgba(255,255,255,0.8);
      display: flex; align-items: center; justify-content: center; box-sizing: border-box;
    }}
    .fresh-cosbot-inner {{
      width: 100%; height: 100%; border-radius: 50%;
      background: radial-gradient(circle at 30% 25%, #1E293B 0%, #0F172A 85%);
      display: flex; align-items: center; justify-content: center; overflow: hidden;
    }}
    .fresh-cosbot-inner svg {{ width: 50px; height: 50px; }}
    .fresh-cosbot-label {{
      margin-top: -13px;
      background: linear-gradient(90deg, #0284C7 0%, ${{config.primaryColor}} 100%);
      color: #FFFFFF; font-size: 11px; font-weight: 700; letter-spacing: -0.3px;
      padding: 3px 10px; border-radius: 999px; border: 1.5px solid #E0F2FE;
      box-shadow: 0 3px 8px rgba(2, 132, 199, 0.35); white-space: nowrap; z-index: 2;
    }}
    .fresh-widget-launcher.shape-sticker {{
      width: 72px; height: 72px; background: transparent; display: flex; flex-direction: column; align-items: center;
      filter: drop-shadow(0 6px 14px rgba(0,0,0,0.22));
    }}
    .fresh-widget-launcher.shape-sticker svg {{ width: 64px; height: 64px; }}
    .fresh-widget-launcher.shape-circle {{
      width: 64px; height: 64px; border-radius: 50%; background: ${{config.primaryColor}};
      box-shadow: 0 6px 18px rgba(0,0,0,0.25); display: flex; align-items: center; justify-content: center;
    }}
    .fresh-widget-launcher.shape-circle svg {{ width: 44px; height: 44px; }}
    .fresh-widget-launcher.shape-pill {{
      background: #0F172A; border: 2px solid ${{config.primaryColor}}; border-radius: 999px;
      padding: 6px 16px 6px 10px; display: flex; align-items: center; gap: 8px;
      box-shadow: 0 6px 20px rgba(0,0,0,0.25); color: #FFFFFF; font-size: 13px; font-weight: 700;
    }}
    .fresh-widget-launcher.shape-pill svg {{ width: 38px; height: 38px; }}
    .fresh-bot-avatar-img {{ width: 100%; height: 100%; object-fit: cover; border-radius: 50%; }}

    /* Base Chat Window */
    .fresh-widget-window {{
      position: fixed; bottom: 116px; right: 24px; width: 400px; height: 660px;
      max-width: calc(100vw - 32px); max-height: calc(100vh - 140px);
      background: #ffffff; border-radius: 18px;
      box-shadow: 0 14px 36px rgba(15, 23, 42, 0.24);
      display: none; flex-direction: column; z-index: 999999; overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", Roboto, sans-serif;
    }}
    .fresh-widget-header {{
      background: #0F172A; color: #ffffff; padding: 15px 18px;
      display: flex; justify-content: space-between; align-items: center;
    }}
    .fresh-header-left {{ display: flex; align-items: center; gap: 10px; }}
    .fresh-brand-pill {{
      background: #0284C7; color: #FFFFFF; font-size: 12px; font-weight: 700;
      padding: 4px 10px; border-radius: 6px; letter-spacing: -0.2px;
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
      background: linear-gradient(135deg, #0F172A 0%, ${{config.primaryColor}} 100%);
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
      width: 26px; height: 26px; border-radius: 8px; background: #0F172A;
      display: flex; align-items: center; justify-content: center; overflow: hidden;
    }}
    .fresh-bot-sq-avatar svg {{ width: 22px; height: 22px; }}
    .fresh-bot-meta-name {{ font-size: 12.5px; font-weight: 700; color: #1E293B; }}
    .fresh-bot-meta-time {{ font-size: 11.5px; color: #94A3B8; }}
    .fresh-msg {{
      max-width: 88%; padding: 13px 16px; border-radius: 14px; font-size: 14px; line-height: 1.55; word-break: break-word;
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
      width: 40px; height: 40px; border-radius: 50%; background: #0F172A; color: #ffffff;
      border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; flex-shrink: 0;
    }}
    .fresh-btn-send svg {{ width: 18px; height: 18px; fill: #FFFFFF; margin-left: 2px; }}
    .fresh-upload-btn {{
      background: #F8FAFC; border: 1px dashed #CBD5E1; border-radius: 8px; padding: 5px 10px;
      font-size: 11.5px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; color: #475569;
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
    return Response(content=js_content, media_type="application/javascript")
