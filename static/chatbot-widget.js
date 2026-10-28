(function () {
  "use strict";

  // Widget Configuration
  const config = window.FreshClaimWidgetConfig || {
    apiBase: "",
    title: "신선식품 AI 고객센터",
    subtitle: "AI 상담 및 사진 클레임 접수",
    primaryColor: "#2E7D32",
  };

  let sessionId = localStorage.getItem("claim_chat_session_id") || "";
  let activeClaimId = null;

  // Inject CSS Styles
  const style = document.createElement("style");
  style.innerHTML = `
    .fresh-widget-launcher {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: ${config.primaryColor};
      box-shadow: 0 4px 14px rgba(0,0,0,0.25);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 999999;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .fresh-widget-launcher:hover {
      transform: scale(1.06);
      box-shadow: 0 6px 20px rgba(0,0,0,0.3);
    }
    .fresh-widget-launcher svg {
      width: 32px;
      height: 32px;
      fill: #ffffff;
    }
    .fresh-widget-window {
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
    }
    .fresh-widget-header {
      background: ${config.primaryColor};
      color: #ffffff;
      padding: 16px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .fresh-widget-header h3 {
      margin: 0;
      font-size: 16px;
      font-weight: 600;
    }
    .fresh-widget-header p {
      margin: 2px 0 0;
      font-size: 12px;
      opacity: 0.85;
    }
    .fresh-widget-close {
      cursor: pointer;
      font-size: 20px;
      line-height: 1;
      opacity: 0.8;
      transition: opacity 0.2s;
    }
    .fresh-widget-close:hover { opacity: 1; }
    .fresh-widget-body {
      flex: 1;
      padding: 16px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: #F9FAFB;
    }
    .fresh-msg {
      max-width: 82%;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 14px;
      line-height: 1.45;
      word-break: break-word;
    }
    .fresh-msg.bot {
      background: #FFFFFF;
      color: #1F2937;
      border: 1px solid #E5E7EB;
      align-self: flex-start;
      border-bottom-left-radius: 4px;
    }
    .fresh-msg.user {
      background: ${config.primaryColor};
      color: #FFFFFF;
      align-self: flex-end;
      border-bottom-right-radius: 4px;
    }
    .fresh-claim-card {
      background: #FFFFFF;
      border: 1px solid #E5E7EB;
      border-left: 4px solid ${config.primaryColor};
      border-radius: 8px;
      padding: 12px;
      font-size: 13px;
      box-shadow: 0 2px 6px rgba(0,0,0,0.05);
    }
    .fresh-claim-card .title { font-weight: 600; margin-bottom: 6px; }
    .fresh-claim-card .badge {
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      margin-bottom: 6px;
    }
    .badge-approved { background: #DCFCE7; color: #166534; }
    .badge-review { background: #FEF3C7; color: #92400E; }
    .badge-retake { background: #FEE2E2; color: #991B1B; }
    .fresh-widget-footer {
      padding: 12px;
      border-top: 1px solid #E5E7EB;
      background: #FFFFFF;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .fresh-input-row {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .fresh-input {
      flex: 1;
      border: 1px solid #D1D5DB;
      border-radius: 20px;
      padding: 8px 14px;
      font-size: 14px;
      outline: none;
    }
    .fresh-input:focus { border-color: ${config.primaryColor}; }
    .fresh-btn-send {
      background: ${config.primaryColor};
      color: #ffffff;
      border: none;
      border-radius: 20px;
      padding: 8px 14px;
      font-weight: 600;
      cursor: pointer;
    }
    .fresh-upload-btn {
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
    }
    .fresh-upload-btn:hover { background: #E5E7EB; }
  `;
  document.head.appendChild(style);

  // Build DOM Structure
  const launcher = document.createElement("div");
  launcher.className = "fresh-widget-launcher";
  launcher.innerHTML = `<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/></svg>`;

  const chatWindow = document.createElement("div");
  chatWindow.className = "fresh-widget-window";
  chatWindow.innerHTML = `
    <div class="fresh-widget-header">
      <div>
        <h3>${config.title}</h3>
        <p>${config.subtitle}</p>
      </div>
      <div class="fresh-widget-close" id="fresh-close">&times;</div>
    </div>
    <div class="fresh-widget-body" id="fresh-messages">
      <div class="fresh-msg bot">
        안녕하세요! 신선식품 AI 고객센터입니다. 🍎<br>
        배송 조회, 상품 보관법, 또는 상품 파손/변질 클레임 사진 접수를 도와드립니다.
      </div>
    </div>
    <div class="fresh-widget-footer">
      <input type="file" id="fresh-file-input" accept="image/jpeg,image/png,image/webp" style="display:none;" />
      <button class="fresh-upload-btn" id="fresh-upload-trigger">
        📷 손상 상품 사진 업로드 접수
      </button>
      <div class="fresh-input-row">
        <input type="text" class="fresh-input" id="fresh-user-input" placeholder="메시지 또는 주문번호(ORD-...) 입력" />
        <button class="fresh-btn-send" id="fresh-send-btn">전송</button>
      </div>
    </div>
  `;

  document.body.appendChild(launcher);
  document.body.appendChild(chatWindow);

  const messagesContainer = chatWindow.querySelector("#fresh-messages");
  const userInput = chatWindow.querySelector("#fresh-user-input");
  const sendBtn = chatWindow.querySelector("#fresh-send-btn");
  const fileInput = chatWindow.querySelector("#fresh-file-input");
  const uploadTrigger = chatWindow.querySelector("#fresh-upload-trigger");
  const closeBtn = chatWindow.querySelector("#fresh-close");

  // Toggle Window
  launcher.addEventListener("click", () => {
    chatWindow.style.display = chatWindow.style.display === "flex" ? "none" : "flex";
    if (chatWindow.style.display === "flex") userInput.focus();
  });
  closeBtn.addEventListener("click", () => { chatWindow.style.display = "none"; });

  function appendMessage(text, sender) {
    const msg = document.createElement("div");
    msg.className = `fresh-msg ${sender}`;
    msg.innerHTML = text.replace(/\n/g, "<br>");
    messagesContainer.appendChild(msg);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    return msg;
  }

  // Handle Text Send via SSE Streaming
  async function sendMessage() {
    const text = userInput.value.trim();
    if (!text) return;
    userInput.value = "";
    appendMessage(text, "user");

    const botMsg = appendMessage("답변을 준비 중입니다...", "bot");
    botMsg.innerHTML = "";

    try {
      const response = await fetch(`${config.apiBase}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonToString({ session_id: sessionId, message: text, customer_id: "guest" }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split("\n");
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const raw = line.slice(6).trim();
            if (raw === "[DONE]") continue;
            try {
              const data = JSON.parse(raw);
              if (data.token) {
                fullText += data.token;
                botMsg.innerHTML = fullText.replace(/\n/g, "<br>");
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
              }
            } catch (e) {}
          }
        }
      }
    } catch (err) {
      botMsg.innerText = "연결 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.";
    }
  }

  // Handle Photo Claim Upload
  uploadTrigger.addEventListener("click", () => {
    fileInput.click();
  });

  fileInput.addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    appendMessage(`[사진 업로드] ${file.name} 분석 중...`, "user");
    const analyzingMsg = appendMessage("Vision AI가 상품 손상 상태를 정밀 계측하고 있습니다. 잠시만 기다려 주세요...", "bot");

    try {
      // 1. Create Claim (using demo order if not initiated)
      const claimResp = await fetch(`${config.apiBase}/api/claims`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: jsonToString({
          order_id: "ORD-NORMAL",
          customer_id: "guest",
          claim_type: "fresh_defect",
          description: "사진 기반 품질 클레임 접수",
        }),
      });
      const claimData = await claimResp.json();
      activeClaimId = claimData.claim_id;

      // 2. Upload Image
      const formData = new FormData();
      formData.append("file", file);

      const uploadResp = await fetch(`${config.apiBase}/api/claims/${activeClaimId}/images`, {
        method: "POST",
        body: formData,
      });

      const result = await uploadResp.json();
      analyzingMsg.remove();

      // Render Card
      const card = document.createElement("div");
      card.className = "fresh-claim-card";
      let badgeClass = "badge-approved";
      if (result.decision === "MANUAL_REVIEW") badgeClass = "badge-review";
      if (result.decision === "RETAKE_IMAGE") badgeClass = "badge-retake";

      card.innerHTML = `
        <div class="badge ${badgeClass}">${result.decision}</div>
        <div class="title">판독 결과: 손상률 ${result.observation.damage_ratio || 0}% (${result.observation.defect_type || '식별'})</div>
        <p>${result.customer_message}</p>
        <div style="font-size: 11px; color: #6B7280; margin-top: 6px;">
          접수번호: ${result.claim_id.slice(0, 8)}... | 환불 예정액: ${result.refund_amount.toLocaleString()}원
        </div>
      `;
      messagesContainer.appendChild(card);
      messagesContainer.scrollTop = messagesContainer.scrollHeight;

    } catch (err) {
      analyzingMsg.innerText = "사진 분석 중 오류가 발생했습니다. 다시 시도해 주세요.";
    }
  });

  sendBtn.addEventListener("click", sendMessage);
  userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendMessage();
  });

  function jsonToString(obj) {
    return JSON.stringify(obj);
  }
})();
