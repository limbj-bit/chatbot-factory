from typing import Dict
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.store_service import store_service
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/api/widget", tags=["Widget"])


# High-craft Flaticon-inspired multi-color vector illustrations (Zero copyright issues, crisp at any size)
FLATICON_PRESET_SVGS: Dict[str, str] = {
    # 1. COSRAWFREE '코스봇' 스타일: 안테나 로봇 + 우측 상단 하늘색 말풍선 점(...)
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
      <circle cx="44.5" cy="16.5" r="1.3" fill="#FFFFFF"/>
      <circle cx="48" cy="16.5" r="1.3" fill="#FFFFFF"/>
      <circle cx="51.5" cy="16.5" r="1.3" fill="#FFFFFF"/>
    </svg>""",
    # 2. 뷰티 스파클 요정 로봇 (파스텔 핑크 + 반짝이 왕관/하트)
    "flaticon_beauty_fairy": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M23 17L26 11L30 15L34 11L37 17H23Z" fill="#FBBF24"/>
      <rect x="16" y="17" width="28" height="26" rx="12" fill="#FFF1F2" stroke="#F472B6" stroke-width="2.5"/>
      <rect x="20" y="22" width="20" height="14" rx="6" fill="#831843"/>
      <circle cx="25.5" cy="28.5" r="2.4" fill="#F9A8D4"/>
      <circle cx="34.5" cy="28.5" r="2.4" fill="#F9A8D4"/>
      <circle cx="22.5" cy="31.5" r="1.6" fill="#FB7185"/>
      <circle cx="37.5" cy="31.5" r="1.6" fill="#FB7185"/>
      <path d="M27 32.5C28 33.8 32 33.8 33 32.5" stroke="#F9A8D4" stroke-width="2" stroke-linecap="round"/>
      <path d="M48 11L49.5 14.5L53 16L49.5 17.5L48 21L46.5 17.5L43 16L46.5 14.5L48 11Z" fill="#FDE047"/>
    </svg>""",
    # 3. 헤드셋 쓴 친절한 고객센터 상담원 (Flaticon 베스트셀러 CS 에이전트)
    "flaticon_cs_agent": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M16 28C16 19.1634 23.1634 12 32 12C40.8366 12 48 19.1634 48 28" stroke="#38BDF8" stroke-width="3.5" stroke-linecap="round"/>
      <rect x="13" y="25" width="5" height="11" rx="2.5" fill="#0284C7"/>
      <rect x="46" y="25" width="5" height="11" rx="2.5" fill="#0284C7"/>
      <circle cx="32" cy="29" r="12" fill="#FDE68A"/>
      <path d="M20 26C20 19.5 25.5 16 32 16C38.5 16 44 19.5 44 26C41 23 36 22 32 22C28 22 23 23 20 26Z" fill="#475569"/>
      <circle cx="28" cy="29" r="1.8" fill="#1E293B"/>
      <circle cx="36" cy="29" r="1.8" fill="#1E293B"/>
      <path d="M28.5 34C30 35.5 34 35.5 35.5 34" stroke="#E11D48" stroke-width="2" stroke-linecap="round"/>
      <path d="M47 34C47 38 41 40 35 40" stroke="#0284C7" stroke-width="2" stroke-linecap="round"/>
      <circle cx="34" cy="40" r="2" fill="#0284C7"/>
    </svg>""",
    # 4. 말풍선 속 윙크하는 챗봇 (Flaticon Chat Bubble Bot)
    "flaticon_bubble_bot": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M14 26C14 17.7157 21.1634 11 30 11H34C42.8366 11 50 17.7157 50 26C50 34.2843 42.8366 41 34 41H24L16 46V38.5C14.7 36.2 14 31.2 14 26Z" fill="#FFFFFF" stroke="#34D399" stroke-width="2.5"/>
      <circle cx="26" cy="25" r="2.6" fill="#059669"/>
      <path d="M35 25L39 23.5M35 25L39 26.5" stroke="#059669" stroke-width="2.2" stroke-linecap="round"/>
      <path d="M27 31C28.8 33 35.2 33 37 31" stroke="#10B981" stroke-width="2.2" stroke-linecap="round"/>
    </svg>""",
    # 5. 스마트 AI 브레인 스파클 아이콘
    "flaticon_smart_ai": """<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M32 10L36.5 23.5L50 28L36.5 32.5L32 46L27.5 32.5L14 28L27.5 23.5L32 10Z" fill="#60A5FA" stroke="#EFF6FF" stroke-width="2"/>
      <path d="M46 11L47.5 15.5L52 17L47.5 18.5L46 23L44.5 18.5L40 17L44.5 15.5L46 11Z" fill="#FBBF24"/>
    </svg>""",
}


@router.get("/script")
async def get_dynamic_widget_script(
    request: Request,
    mall_id: str = Query("demo_mall", description="Store Mall ID"),
    session: AsyncSession = Depends(get_db),
):
    """Serve a dynamically customized JavaScript widget tailored to the specific store's industry, brand, trial status, Flaticon bot avatar, and domain whitelist."""
    store = await store_service.get_store_by_mall_id(session, mall_id)

    # 4th Enhancement: Domain Whitelist Validation
    origin_or_referer = request.headers.get("origin") or request.headers.get("referer")
    if not store_service.is_domain_allowed(store, origin_or_referer):
        blocked_js = f'console.warn("[ChatbotFactory] Unauthorized domain for mall_id={mall_id}. Allowed domains: {store.allowed_domains if store else ""}");'
        return Response(content=blocked_js, media_type="application/javascript")

    title = store.store_name if store else "스마트 AI 고객센터"
    industry = store.industry if store else "general"
    theme_color = store.theme_color if store else "#0284C7"
    welcome_msg = (
        store.welcome_message.replace("\n", "\\n")
        if store and store.welcome_message
        else "안녕하세요! AI 고객센터입니다. 무엇을 도와드릴까요?"
    )

    bot_icon_style = (store.bot_icon_style if store and store.bot_icon_style else "flaticon_cute_robot")
    launcher_shape = (store.launcher_shape if store and store.launcher_shape else "cosbot_badge")
    bot_label = (store.bot_label if store and store.bot_label else "코스봇 상담")
    bot_avatar_url = (store.bot_avatar_url if store and store.bot_avatar_url else "")

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

    js_content = f"""
(function () {{
  "use strict";

  const config = {{
    mallId: "{mall_id}",
    title: "{title}",
    industry: "{industry}",
    primaryColor: "{theme_color}",
    botIconStyle: "{bot_icon_style}",
    launcherShape: "{launcher_shape}",
    botLabel: "{safe_label}",
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

  // Inject Styles (Including COSRAWFREE '코스봇 상담' double-ring badge & Flaticon floating animation)
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
    .fresh-widget-launcher:hover {{
      filter: brightness(1.06);
      transform: scale(1.05);
    }}
    /* Shape 1: COSRAWFREE '코스봇 상담' 스타일 (이중 네이비 원형 링 + 하단 캡슐 라벨) */
    .fresh-widget-launcher.shape-cosbot_badge {{
      width: 78px;
      height: 84px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: flex-start;
    }}
    .fresh-cosbot-ring {{
      width: 68px;
      height: 68px;
      border-radius: 50%;
      padding: 3.5px;
      background: linear-gradient(145deg, #E0F2FE 0%, #38BDF8 50%, ${{config.primaryColor}} 100%);
      box-shadow: 0 8px 22px rgba(15, 23, 42, 0.28), inset 0 1px 2px rgba(255,255,255,0.8);
      display: flex;
      align-items: center;
      justify-content: center;
      box-sizing: border-box;
    }}
    .fresh-cosbot-inner {{
      width: 100%;
      height: 100%;
      border-radius: 50%;
      background: radial-gradient(circle at 30% 25%, #1E293B 0%, #0F172A 85%);
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }}
    .fresh-cosbot-inner svg {{
      width: 50px;
      height: 50px;
    }}
    .fresh-cosbot-label {{
      margin-top: -13px;
      background: linear-gradient(90deg, #0284C7 0%, ${{config.primaryColor}} 100%);
      color: #FFFFFF;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: -0.3px;
      padding: 3px 10px;
      border-radius: 999px;
      border: 1.5px solid #E0F2FE;
      box-shadow: 0 3px 8px rgba(2, 132, 199, 0.35);
      white-space: nowrap;
      z-index: 2;
    }}
    /* Shape 2: Flaticon 투명 스티커형 (배경 없이 캐릭터만 둥둥) */
    .fresh-widget-launcher.shape-sticker {{
      width: 72px;
      height: 72px;
      background: transparent;
      display: flex;
      flex-direction: column;
      align-items: center;
      filter: drop-shadow(0 6px 14px rgba(0,0,0,0.22));
    }}
    .fresh-widget-launcher.shape-sticker svg {{ width: 64px; height: 64px; }}
    /* Shape 3: 심플 원형 */
    .fresh-widget-launcher.shape-circle {{
      width: 64px;
      height: 64px;
      border-radius: 50%;
      background: ${{config.primaryColor}};
      box-shadow: 0 6px 18px rgba(0,0,0,0.25);
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .fresh-widget-launcher.shape-circle svg {{ width: 44px; height: 44px; }}
    /* Shape 4: 가로 캡슐형 (캐릭터 + 텍스트 옆으로 나란히) */
    .fresh-widget-launcher.shape-pill {{
      background: #0F172A;
      border: 2px solid ${{config.primaryColor}};
      border-radius: 999px;
      padding: 6px 16px 6px 10px;
      display: flex;
      align-items: center;
      gap: 8px;
      box-shadow: 0 6px 20px rgba(0,0,0,0.25);
      color: #FFFFFF;
      font-size: 13px;
      font-weight: 700;
    }}
    .fresh-widget-launcher.shape-pill svg {{ width: 38px; height: 38px; }}
    .fresh-bot-avatar-img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      border-radius: 50%;
    }}
    .fresh-widget-window {{
      position: fixed;
      bottom: 116px;
      right: 24px;
      width: 390px;
      height: 620px;
      max-width: calc(100vw - 32px);
      max-height: calc(100vh - 140px);
      background: #ffffff;
      border-radius: 16px;
      box-shadow: 0 12px 32px rgba(15, 23, 42, 0.22);
      display: none;
      flex-direction: column;
      z-index: 999999;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .fresh-widget-header {{
      background: linear-gradient(135deg, #0F172A 0%, ${{config.primaryColor}} 100%);
      color: #ffffff;
      padding: 14px 18px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .fresh-header-left {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}
    .fresh-header-avatar {{
      width: 38px;
      height: 38px;
      border-radius: 50%;
      background: #0F172A;
      border: 1.5px solid #38BDF8;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      flex-shrink: 0;
    }}
    .fresh-header-avatar svg {{ width: 32px; height: 32px; }}
    .fresh-widget-header h3 {{
      margin: 0;
      font-size: 15px;
      font-weight: 700;
    }}
    .fresh-widget-header p {{
      margin: 2px 0 0;
      font-size: 11.5px;
      opacity: 0.88;
    }}
    .fresh-widget-close {{
      cursor: pointer;
      font-size: 22px;
      line-height: 1;
      opacity: 0.85;
    }}
    .fresh-widget-close:hover {{ opacity: 1; }}
    .fresh-widget-banner {{
      padding: 10px 14px;
      font-size: 12px;
      font-weight: 600;
      line-height: 1.4;
      border-bottom: 1px solid #FDE68A;
      background: #FFFBEB;
      color: #92400E;
    }}
    .fresh-widget-banner.expired {{
      background: #FEF2F2;
      border-bottom-color: #FECACA;
      color: #991B1B;
    }}
    .fresh-widget-body {{
      flex: 1;
      padding: 16px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: #F8FAFC;
    }}
    .fresh-bot-row {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
      max-width: 90%;
    }}
    .fresh-bot-mini-avatar {{
      width: 30px;
      height: 30px;
      border-radius: 50%;
      background: #0F172A;
      border: 1px solid #CBD5E1;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      flex-shrink: 0;
      margin-top: 2px;
    }}
    .fresh-bot-mini-avatar svg {{ width: 25px; height: 25px; }}
    .fresh-msg {{
      max-width: 82%;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 14px;
      line-height: 1.45;
      word-break: break-word;
    }}
    .fresh-msg.bot {{
      background: #FFFFFF;
      color: #1F2937;
      border: 1px solid #E2E8F0;
      align-self: flex-start;
      border-top-left-radius: 4px;
      max-width: 100%;
    }}
    .fresh-msg.user {{
      background: ${{config.primaryColor}};
      color: #FFFFFF;
      align-self: flex-end;
      border-bottom-right-radius: 4px;
    }}
    .fresh-product-card {{
      background: #FFFFFF;
      border: 1px solid #E5E7EB;
      border-left: 4px solid ${{config.primaryColor}};
      border-radius: 10px;
      padding: 12px;
      max-width: 85%;
      align-self: flex-start;
      margin-left: 38px;
      box-shadow: 0 2px 6px rgba(0,0,0,0.05);
      font-size: 13px;
    }}
    .fresh-product-card h4 {{
      margin: 0 0 4px 0;
      font-size: 14px;
      color: #111827;
    }}
    .fresh-product-card .price {{
      font-weight: 700;
      color: ${{config.primaryColor}};
      margin-bottom: 6px;
    }}
    .fresh-product-card .buy-link {{
      display: inline-block;
      margin-top: 8px;
      background: ${{config.primaryColor}};
      color: #FFFFFF;
      text-decoration: none;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }}
    .fresh-widget-footer {{
      padding: 12px;
      border-top: 1px solid #E5E7EB;
      background: #FFFFFF;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .fresh-input-row {{
      display: flex;
      gap: 8px;
      align-items: center;
    }}
    .fresh-input {{
      flex: 1;
      border: 1px solid #D1D5DB;
      border-radius: 20px;
      padding: 8px 14px;
      font-size: 14px;
      outline: none;
    }}
    .fresh-input:focus {{ border-color: ${{config.primaryColor}}; }}
    .fresh-input:disabled {{ background: #F3F4F6; cursor: not-allowed; }}
    .fresh-btn-send {{
      background: ${{config.primaryColor}};
      color: #ffffff;
      border: none;
      border-radius: 20px;
      padding: 8px 14px;
      font-weight: 600;
      cursor: pointer;
    }}
    .fresh-btn-send:disabled {{ background: #9CA3AF; cursor: not-allowed; }}
    .fresh-upload-btn {{
      background: #F3F4F6;
      border: 1px dashed #9CA3AF;
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 12px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      color: #4B5563;
    }}
    .fresh-upload-btn:hover {{ background: #E5E7EB; }}
    .fresh-upload-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
  `;
  document.head.appendChild(style);

  // Build Launcher according to launcherShape
  const launcher = document.createElement("div");
  launcher.className = "fresh-widget-launcher shape-" + config.launcherShape;

  if (config.launcherShape === "cosbot_badge") {{
    launcher.innerHTML = `
      <div class="fresh-cosbot-ring">
        <div class="fresh-cosbot-inner">${{iconGraphicHtml}}</div>
      </div>
      <div class="fresh-cosbot-label">${{config.botLabel}}</div>
    `;
  }} else if (config.launcherShape === "pill") {{
    launcher.innerHTML = `
      <div class="fresh-header-avatar">${{iconGraphicHtml}}</div>
      <span>${{config.botLabel}}</span>
    `;
  }} else if (config.launcherShape === "sticker") {{
    launcher.innerHTML = `
      ${{iconGraphicHtml}}
      <div class="fresh-cosbot-label" style="margin-top:-6px;">${{config.botLabel}}</div>
    `;
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
  const inputPlaceholder = config.isExpired ? "사용기한이 만료되어 입력할 수 없습니다." : "문의사항 또는 주문번호 입력...";

  const chatWindow = document.createElement("div");
  chatWindow.className = "fresh-widget-window";
  chatWindow.innerHTML = `
    <div class="fresh-widget-header">
      <div class="fresh-header-left">
        <div class="fresh-header-avatar">${{iconGraphicHtml}}</div>
        <div>
          <h3>${{config.title}}</h3>
          <p>${{config.botLabel}} · AI 카운슬러 & 스마트 A/S</p>
        </div>
      </div>
      <div class="fresh-widget-close" id="dyn-close">&times;</div>
    </div>
    ${{bannerHtml}}
    <div class="fresh-widget-body" id="dyn-messages">
      <div class="fresh-bot-row">
        <div class="fresh-bot-mini-avatar">${{iconGraphicHtml}}</div>
        <div class="fresh-msg bot">${{initialBodyMessage}}</div>
      </div>
    </div>
    <div class="fresh-widget-footer">
      <input type="file" id="dyn-file" accept="image/*" style="display:none;" ${{disabledAttr}} />
      <button class="fresh-upload-btn" id="dyn-upload-btn" ${{disabledAttr}}>${{config.uploadGuide}}</button>
      <div class="fresh-input-row">
        <input type="text" class="fresh-input" id="dyn-input" placeholder="${{inputPlaceholder}}" ${{disabledAttr}} />
        <button class="fresh-btn-send" id="dyn-send" ${{disabledAttr}}>전송</button>
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

  function appendMessage(text, sender) {{
    if (sender === "bot") {{
      const row = document.createElement("div");
      row.className = "fresh-bot-row";
      const avatar = document.createElement("div");
      avatar.className = "fresh-bot-mini-avatar";
      avatar.innerHTML = iconGraphicHtml;
      const msg = document.createElement("div");
      msg.className = "fresh-msg bot";
      msg.innerHTML = text.replace(/\\n/g, "<br>");
      row.appendChild(avatar);
      row.appendChild(msg);
      messagesContainer.appendChild(row);
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
