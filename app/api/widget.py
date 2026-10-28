from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.application.store_service import store_service
from app.infrastructure.database.session import get_db

router = APIRouter(prefix="/api/widget", tags=["Widget"])


@router.get("/script")
async def get_dynamic_widget_script(
    mall_id: str = Query("demo_mall", description="Store Mall ID"),
    session: AsyncSession = Depends(get_db),
):
    """Serve a dynamically customized JavaScript widget tailored to the specific store's industry, brand, and trial status."""
    store = await store_service.get_store_by_mall_id(session, mall_id)

    title = store.store_name if store else "스마트 AI 고객센터"
    industry = store.industry if store else "general"
    theme_color = store.theme_color if store else "#2E7D32"
    welcome_msg = (
        store.welcome_message.replace("\n", "\\n")
        if store and store.welcome_message
        else "안녕하세요! AI 고객센터입니다. 무엇을 도와드릴까요?"
    )

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

    js_content = f"""
(function () {{
  "use strict";

  const config = {{
    mallId: "{mall_id}",
    title: "{title}",
    industry: "{industry}",
    primaryColor: "{theme_color}",
    welcomeMessage: "{welcome_msg}",
    uploadGuide: "{upload_guide}",
    isExpired: {is_expired_js},
    expiryWarning: {expiry_warning_js},
    remainingDays: {remaining_days_js},
    statusMessage: "{safe_status_msg}",
    apiBase: window.location.origin
  }};

  let sessionId = localStorage.getItem("claim_chat_session_" + config.mallId) || "";

  // Inject Styles
  const style = document.createElement("style");
  style.innerHTML = `
    .fresh-widget-launcher {{
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: ${{config.primaryColor}};
      box-shadow: 0 4px 14px rgba(0,0,0,0.25);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 999999;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }}
    .fresh-widget-launcher:hover {{
      transform: scale(1.06);
      box-shadow: 0 6px 20px rgba(0,0,0,0.3);
    }}
    .fresh-widget-launcher svg {{
      width: 32px;
      height: 32px;
      fill: #ffffff;
    }}
    .fresh-widget-window {{
      position: fixed;
      bottom: 96px;
      right: 24px;
      width: 390px;
      height: 620px;
      max-width: calc(100vw - 32px);
      max-height: calc(100vh - 120px);
      background: #ffffff;
      border-radius: 16px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.18);
      display: none;
      flex-direction: column;
      z-index: 999999;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .fresh-widget-header {{
      background: ${{config.primaryColor}};
      color: #ffffff;
      padding: 16px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .fresh-widget-header h3 {{
      margin: 0;
      font-size: 16px;
      font-weight: 600;
    }}
    .fresh-widget-header p {{
      margin: 2px 0 0;
      font-size: 12px;
      opacity: 0.85;
    }}
    .fresh-widget-close {{
      cursor: pointer;
      font-size: 20px;
      line-height: 1;
      opacity: 0.8;
      transition: opacity 0.2s;
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
      background: #F9FAFB;
    }}
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
      border: 1px solid #E5E7EB;
      align-self: flex-start;
      border-bottom-left-radius: 4px;
    }}
    .fresh-msg.user {{
      background: ${{config.primaryColor}};
      color: #FFFFFF;
      align-self: flex-end;
      border-bottom-right-radius: 4px;
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

  // Build Elements
  const launcher = document.createElement("div");
  launcher.className = "fresh-widget-launcher";
  launcher.innerHTML = `<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/></svg>`;

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
      <div>
        <h3>${{config.title}}</h3>
        <p>A/S 및 스마트 CS 도우미</p>
      </div>
      <div class="fresh-widget-close" id="dyn-close">&times;</div>
    </div>
    ${{bannerHtml}}
    <div class="fresh-widget-body" id="dyn-messages">
      <div class="fresh-msg bot">${{initialBodyMessage}}</div>
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
    const msg = document.createElement("div");
    msg.className = "fresh-msg " + sender;
    msg.innerHTML = text.replace(/\\n/g, "<br>");
    messagesContainer.appendChild(msg);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return msg;
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
        body: JSON.stringify({{ session_id: sessionId, message: text, customer_id: "guest" }}),
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
      analyzingMsg.remove();

      appendMessage("<b>[진단 결과: " + result.decision + "]</b><br>" + result.customer_message, "bot");
    }} catch (err) {{
      analyzingMsg.innerText = "진단 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
    }}
  }});
}})();
"""
    return Response(content=js_content, media_type="application/javascript")
