# -*- coding: utf-8 -*-
"""Safe insert of first-screen bubble editor after welcomeMessage field-card."""
from pathlib import Path
import re

p = Path(__file__).resolve().parents[1] / "static" / "index.html"
t = p.read_text(encoding="utf-8")
assert 'id="welcomeMessage"' in t, "welcomeMessage missing — abort"
if 'id="firstScreenEditor"' in t:
    print("already installed")
    raise SystemExit(0)

BLOCK = """
        <div class="field-card" id="firstScreenEditor" style="grid-column: 1 / -1; border:1.5px solid #0EA5E9; background:#F0F9FF;">
          <div class="field-title"><span>⑦ 첫 화면 말풍선 · 빠른 질문 · 등장 시간</span><span class="field-tag">직접편집</span></div>
          <div class="field-desc">업종 기본 문구를 목록으로 보여 둔 뒤 수정·삭제·추가합니다. 채팅창을 열면 말풍선이 설정한 간격으로 순서대로 나옵니다.</div>
          <label style="display:block;font-size:12px;font-weight:700;color:#0369A1;margin:10px 0 6px;">봇 말풍선 (순서대로)</label>
          <div id="welcomeBubblesList" style="display:flex;flex-direction:column;gap:8px;"></div>
          <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;">
            <button type="button" class="pos-btn" onclick="addWelcomeBubbleRow()">+ 말풍선 추가</button>
            <button type="button" class="pos-btn" onclick="seedWelcomeBubblesFromIndustry()" style="color:#0369A1;">업종 기본으로 채우기</button>
          </div>
          <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:14px;">
            <div>
              <label style="display:block;font-size:12px;font-weight:700;color:#0369A1;margin-bottom:4px;">첫 말풍선 전 지연 (ms)</label>
              <input type="number" id="bubbleFirstDelayMs" min="0" max="10000" step="50" value="0" oninput="triggerInstantPreview()" style="width:120px;" />
            </div>
            <div>
              <label style="display:block;font-size:12px;font-weight:700;color:#0369A1;margin-bottom:4px;">말풍선 간격 (ms)</label>
              <input type="number" id="bubbleGapMs" min="0" max="10000" step="50" value="450" oninput="triggerInstantPreview()" style="width:120px;" />
            </div>
          </div>
          <label style="display:block;font-size:12px;font-weight:700;color:#0369A1;margin:16px 0 6px;">빠른 질문 (기본 문구 → 수정·삭제·추가)</label>
          <div id="quickButtonsList" style="display:flex;flex-direction:column;gap:8px;"></div>
          <div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;">
            <button type="button" class="pos-btn" onclick="addQuickButtonRow()">+ 질문 추가</button>
            <button type="button" class="pos-btn" onclick="seedQuickButtonsFromIndustry()" style="color:#0369A1;">업종 기본으로 채우기</button>
          </div>
        </div>
"""

# Insert after the field-card that contains welcomeMessage textarea
wm = t.find('id="welcomeMessage"')
assert wm > 0
# find end of that field-card: after </textarea> the next </div> closes field-card
ta_end = t.find("</textarea>", wm)
assert ta_end > 0
card_end = t.find("</div>", ta_end)
assert card_end > 0
insert_at = card_end + len("</div>")
t = t[:insert_at] + "\n" + BLOCK + t[insert_at:]
print("HTML block inserted")

# Ensure quickButtonsInput still exists (hidden sync target). If only one text input, leave it;
# also write into hidden if missing after our block.
if 'id="quickButtonsInput"' not in t:
    t = t.replace(
        'id="quickButtonsList"',
        'id="quickButtonsList"',
        1,
    )
    t = t.replace(
        '</div>\n        </div>\n\n      <!-- 2',
        '<input type="hidden" id="quickButtonsInput" value="" />\n        </div>\n\n      <!-- 2',
        1,
    )
    # fallback append hidden near list
    if 'id="quickButtonsInput"' not in t:
        t = t.replace(
            '<div id="quickButtonsList"',
            '<input type="hidden" id="quickButtonsInput" value="" />\n          <div id="quickButtonsList"',
            1,
        )
        print("added hidden quickButtonsInput")

JS = r'''
    window.INDUSTRY_QUICK_DEFAULTS = window.INDUSTRY_QUICK_DEFAULTS || {
      beauty: ["✨ 피부타입별 맞춤 상품 추천", "🌿 전성분 & 임산부 안전 성분", "📸 파손·불량 사진 진단", "💬 트러블 접수 & 반품 문의", "❓ 다른 질문하기"],
      fashion: ["📐 체형별 사이즈 추천받기", "🔄 무료 사이즈 맞교환 신청", "📸 불량/오염 사진 판독 접수", "📦 주문 / 배송 현황 조회", "💬 그 외 다른 질문하기"],
      fresh_food: ["🍎 식품 보관법 & 섭취 안내", "📸 변질/파손 사진 환불 접수", "📦 주문 / 실시간 배송 조회", "🛡️ 48시간 100% 품질보상제", "💬 그 외 다른 질문하기"],
      electronics: ["⚡ 전원/작동 불량 자가진단", "🔧 고장/파손 사진 A/S 판독", "📦 주문 / 배송 현황 조회", "🛡️ 1년 무상 보증 규정 안내", "💬 그 외 다른 질문하기"],
      general: ["📦 주문 / 배송 조회", "🔄 교환/반품 문의", "💬 다른 질문하기"]
    };
    function getWelcomeBubblesFromList() {
      const root = document.getElementById("welcomeBubblesList");
      if (!root) return [];
      return Array.from(root.querySelectorAll("textarea.wb-row")).map(el => (el.value || "").trim()).filter(Boolean).slice(0, 8);
    }
    function syncWelcomeHidden() {
      const wm = document.getElementById("welcomeMessage");
      if (!wm) return;
      const parts = getWelcomeBubblesFromList();
      if (parts.length) { wm.value = parts.join("\n\n"); wm.dataset.manual = "1"; }
    }
    function renderWelcomeBubblesList(items) {
      const root = document.getElementById("welcomeBubblesList");
      if (!root) return;
      const list = (items && items.length) ? items.slice(0, 8) : [""];
      root.innerHTML = "";
      list.forEach((text, idx) => {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;gap:8px;align-items:flex-start;";
        const ta = document.createElement("textarea");
        ta.className = "wb-row";
        ta.rows = 2;
        ta.style.cssText = "flex:1;font-size:13px;";
        ta.value = text || "";
        ta.placeholder = "봇 말풍선 문구";
        ta.oninput = function() { syncWelcomeHidden(); triggerInstantPreview(); };
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "pos-btn";
        btn.style.color = "#B91C1C";
        btn.textContent = "삭제";
        btn.onclick = function() { removeWelcomeBubbleRow(idx); };
        row.appendChild(ta);
        row.appendChild(btn);
        root.appendChild(row);
      });
      syncWelcomeHidden();
    }
    function addWelcomeBubbleRow() {
      const cur = Array.from(document.querySelectorAll("#welcomeBubblesList textarea.wb-row")).map(el => el.value);
      if (cur.length >= 8) { alert("말풍선은 최대 8개입니다."); return; }
      cur.push("");
      renderWelcomeBubblesList(cur);
      triggerInstantPreview();
    }
    function removeWelcomeBubbleRow(idx) {
      const cur = Array.from(document.querySelectorAll("#welcomeBubblesList textarea.wb-row")).map(el => el.value);
      cur.splice(idx, 1);
      renderWelcomeBubblesList(cur.length ? cur : [""]);
      triggerInstantPreview();
    }
    function seedWelcomeBubblesFromIndustry() {
      const sel = (typeof getSelectedIndustryValue === "function") ? getSelectedIndustryValue() : (document.getElementById("industry")?.value || "general");
      let msg = (typeof INDUSTRY_WELCOME !== "undefined" && INDUSTRY_WELCOME[sel]) ? INDUSTRY_WELCOME[sel] : (document.getElementById("welcomeMessage")?.value || "");
      const bn = document.getElementById("botName")?.value.trim();
      if (bn && msg && msg.indexOf("AI 상담사입니다") >= 0) {
        msg = msg.replace("AI 상담사입니다", "AI 상담사(" + bn + ")입니다");
      }
      const parts = String(msg || "").split(/\n\n+/).map(s => s.trim()).filter(Boolean);
      renderWelcomeBubblesList(parts.length ? parts : ["안녕하세요!"]);
      triggerInstantPreview();
    }
    function getQuickButtonsFromList() {
      const root = document.getElementById("quickButtonsList");
      if (!root) return [];
      return Array.from(root.querySelectorAll("input.qb-row-input")).map(el => (el.value || "").trim()).filter(Boolean).slice(0, 8);
    }
    function syncQuickButtonsHidden() {
      const hidden = document.getElementById("quickButtonsInput");
      if (hidden) hidden.value = getQuickButtonsFromList().join(", ");
    }
    function renderQuickButtonsList(items) {
      const root = document.getElementById("quickButtonsList");
      if (!root) return;
      const list = (items && items.length) ? items.slice(0, 8) : [];
      root.innerHTML = "";
      list.forEach((text, idx) => {
        const row = document.createElement("div");
        row.style.cssText = "display:flex;gap:8px;align-items:center;";
        const inp = document.createElement("input");
        inp.type = "text";
        inp.className = "qb-row-input";
        inp.style.flex = "1";
        inp.value = text || "";
        inp.oninput = function() { syncQuickButtonsHidden(); triggerInstantPreview(); };
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "pos-btn";
        btn.style.color = "#B91C1C";
        btn.textContent = "삭제";
        btn.onclick = function() { removeQuickButtonRow(idx); };
        row.appendChild(inp);
        row.appendChild(btn);
        root.appendChild(row);
      });
      syncQuickButtonsHidden();
    }
    function addQuickButtonRow() {
      const cur = Array.from(document.querySelectorAll("#quickButtonsList input.qb-row-input")).map(el => el.value);
      if (cur.length >= 8) { alert("빠른 질문은 최대 8개입니다."); return; }
      cur.push("");
      renderQuickButtonsList(cur);
      triggerInstantPreview();
    }
    function removeQuickButtonRow(idx) {
      const cur = Array.from(document.querySelectorAll("#quickButtonsList input.qb-row-input")).map(el => el.value);
      cur.splice(idx, 1);
      renderQuickButtonsList(cur);
      triggerInstantPreview();
    }
    function seedQuickButtonsFromIndustry() {
      const industry = (typeof getSelectedIndustryValue === "function") ? getSelectedIndustryValue() : "general";
      const map = window.INDUSTRY_QUICK_DEFAULTS || {};
      renderQuickButtonsList(map[industry] || map.general || []);
      triggerInstantPreview();
    }

'''

if "function getWelcomeBubblesFromList()" not in t:
    marker = "async function createMyTrialStore()"
    if marker not in t:
        raise SystemExit("createMyTrialStore marker missing")
    t = t.replace(marker, JS + "\n    " + marker, 1)
    print("JS helpers inserted")

# preview params
if "preview_welcome_bubbles" not in t:
    old = 'preview_welcome_message: document.getElementById("welcomeMessage").value.trim(),'
    new = (
        'preview_welcome_message: document.getElementById("welcomeMessage").value.trim(),\n'
        '        preview_welcome_bubbles: (typeof getWelcomeBubblesFromList === "function" ? getWelcomeBubblesFromList() : []).join("|||"),\n'
        '        preview_bubble_first_delay_ms: parseInt(document.getElementById("bubbleFirstDelayMs")?.value || "0", 10),\n'
        '        preview_bubble_gap_ms: parseInt(document.getElementById("bubbleGapMs")?.value || "450", 10),'
    )
    if old not in t:
        raise SystemExit("preview welcome needle missing")
    t = t.replace(old, new, 1)
    print("preview params")

# sync before create qbRaw
t = t.replace(
    'const qbRaw = document.getElementById("quickButtonsInput").value.trim();\n      const quick_buttons = qbRaw',
    'if (typeof syncWelcomeHidden === "function") syncWelcomeHidden();\n'
    '      if (typeof syncQuickButtonsHidden === "function") syncQuickButtonsHidden();\n'
    '      const qbRaw = document.getElementById("quickButtonsInput").value.trim();\n'
    '      const quick_buttons = qbRaw',
    1,
)

# create payload fields
if "welcome_bubbles:" not in t:
    needle = 'welcome_message: document.getElementById("welcomeMessage").value.trim() || undefined,\n          quick_buttons,'
    repl = (
        'welcome_message: document.getElementById("welcomeMessage").value.trim() || undefined,\n'
        '          welcome_bubbles: (typeof getWelcomeBubblesFromList === "function" ? getWelcomeBubblesFromList() : undefined),\n'
        '          bubble_first_delay_ms: parseInt(document.getElementById("bubbleFirstDelayMs")?.value || "0", 10),\n'
        '          bubble_gap_ms: parseInt(document.getElementById("bubbleGapMs")?.value || "450", 10),\n'
        '          quick_buttons,'
    )
    if needle in t:
        t = t.replace(needle, repl, 1)
        print("create payload")
    else:
        print("WARN create payload needle missing")

# loadStore
old_wm = """        if (data.welcome_message) {
          const wm = document.getElementById("welcomeMessage");
          if (wm) { wm.value = data.welcome_message; wm.dataset.manual = "1"; }
        }"""
if old_wm in t:
    t = t.replace(
        old_wm,
        old_wm
        + """
        if (typeof renderWelcomeBubblesList === "function") {
          const bbs = (data.welcome_bubbles && data.welcome_bubbles.length)
            ? data.welcome_bubbles
            : String(data.welcome_message || "").split(/\\n\\n+/).map(s => s.trim()).filter(Boolean);
          renderWelcomeBubblesList(bbs.length ? bbs : [data.welcome_message || ""]);
        }
        if (document.getElementById("bubbleFirstDelayMs") && data.bubble_first_delay_ms != null) {
          document.getElementById("bubbleFirstDelayMs").value = data.bubble_first_delay_ms;
        }
        if (document.getElementById("bubbleGapMs") && data.bubble_gap_ms != null) {
          document.getElementById("bubbleGapMs").value = data.bubble_gap_ms;
        }
""",
        1,
    )
    print("loadStore bubbles")

old_qb = """        if (data.quick_buttons && data.quick_buttons.length) {
          setFieldValue("quickButtonsInput", data.quick_buttons.join(", "));
        }"""
if old_qb in t:
    t = t.replace(
        old_qb,
        """        if (data.quick_buttons && data.quick_buttons.length) {
          setFieldValue("quickButtonsInput", data.quick_buttons.join(", "));
          if (typeof renderQuickButtonsList === "function") renderQuickButtonsList(data.quick_buttons);
        } else if (typeof seedQuickButtonsFromIndustry === "function") {
          seedQuickButtonsFromIndustry();
        }""",
        1,
    )
    print("loadStore qb")

# page init near end welcomeMessage getElement
init_anchor = '  const wmEl = document.getElementById("welcomeMessage");\n  const indEl = document.getElementById("industry");'
if init_anchor in t and "seedWelcomeBubblesFromIndustry" not in t[t.rfind("const wmEl = document.getElementById(\"welcomeMessage\")") :]:
    t = t.replace(
        init_anchor,
        """  if (typeof renderWelcomeBubblesList === "function") {
    const wm0 = document.getElementById("welcomeMessage")?.value || "";
    const parts0 = wm0.split(/\\n\\n+/).map(s => s.trim()).filter(Boolean);
    if (parts0.length) renderWelcomeBubblesList(parts0);
    else if (typeof seedWelcomeBubblesFromIndustry === "function") seedWelcomeBubblesFromIndustry();
  }
  if (typeof seedQuickButtonsFromIndustry === "function") {
    const qb0 = (document.getElementById("quickButtonsInput")?.value || "").trim();
    if (qb0 && typeof renderQuickButtonsList === "function") {
      renderQuickButtonsList(qb0.split(",").map(s => s.trim()).filter(Boolean));
    } else {
      seedQuickButtonsFromIndustry();
    }
  }
"""
        + init_anchor,
        1,
    )
    print("page init")

# preview: sync before building params — find first qbRaw in triggerInstantPreview
t = t.replace(
    'const qbRaw = document.getElementById("quickButtonsInput").value.trim();\n      const pos = document.getElementById("widgetPos")',
    'if (typeof syncWelcomeHidden === "function") syncWelcomeHidden();\n'
    '      if (typeof syncQuickButtonsHidden === "function") syncQuickButtonsHidden();\n'
    '      const qbRaw = document.getElementById("quickButtonsInput").value.trim();\n'
    '      const pos = document.getElementById("widgetPos")',
    1,
)

p.write_text(t, encoding="utf-8")
# verify
t2 = p.read_text(encoding="utf-8")
assert 'id="welcomeMessage"' in t2
assert 'id="firstScreenEditor"' in t2
assert 'id="welcomeBubblesList"' in t2
print("OK verified", p)
