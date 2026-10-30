"""Mall-scoped staff inbox: store employees (not SaaS admin) handle AS handoffs."""
from __future__ import annotations

import hashlib
import html

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.notification_service import notification_service
from app.core.config import settings
from app.infrastructure.database.session import get_db

router = APIRouter(tags=["StaffInbox"])


def staff_inbox_token(mall_id: str) -> str:
    raw = f"{mall_id}:{settings.ADMIN_API_KEY}:staff-inbox-v1"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _assert_staff_key(mall_id: str, key: str) -> None:
    if not key or key != staff_inbox_token(mall_id):
        raise HTTPException(status_code=403, detail="Invalid staff inbox key")


@router.get("/api/staff/{mall_id}/inbox")
async def list_staff_inbox(
    mall_id: str,
    key: str = Query(..., description="Store staff access key"),
    session: AsyncSession = Depends(get_db),
):
    _assert_staff_key(mall_id, key)
    alerts = await notification_service.list_alerts(session, mall_id)
    # Prefer AS handoffs first
    as_alerts = [a for a in alerts if a.get("alert_type") in ("as_handoff", "claim_escalation")]
    return {
        "mall_id": mall_id,
        "items": as_alerts or alerts,
        "inbox_url": f"/staff/{mall_id}/inbox?key={key}",
    }


@router.get("/staff/{mall_id}/inbox", response_class=HTMLResponse, include_in_schema=False)
async def staff_inbox_page(
    mall_id: str,
    key: str = Query(...),
    session: AsyncSession = Depends(get_db),
):
    _assert_staff_key(mall_id, key)
    alerts = await notification_service.list_alerts(session, mall_id)
    rows = []
    for a in alerts[:50]:
        payload = a.get("payload") or {}
        msg = html.escape(str(payload.get("text") or ""))
        created = html.escape(str(a.get("created_at") or ""))
        typ = html.escape(str(a.get("alert_type") or ""))
        status = html.escape(str(a.get("delivery_status") or ""))
        rows.append(
            f"<tr><td>{created}</td><td>{typ}</td><td><pre>{msg}</pre></td><td>{status}</td></tr>"
        )
    body_rows = "\n".join(rows) or "<tr><td colspan='4'>대기 중인 AS 알림이 없습니다.</td></tr>"
    safe_mall = html.escape(mall_id)
    page = f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{safe_mall} 직원 AS 인박스</title>
<style>
body{{font-family:sans-serif;margin:24px;background:#fafafa;color:#111}}
h1{{font-size:20px}} table{{border-collapse:collapse;width:100%;background:#fff}}
th,td{{border:1px solid #ddd;padding:8px;vertical-align:top;font-size:13px}}
th{{background:#f3f4f6;text-align:left}} pre{{white-space:pre-wrap;margin:0;font-family:inherit}}
.note{{color:#666;font-size:12px;margin:8px 0 16px}}
</style></head><body>
<h1>상점 직원 AS 인박스 — {safe_mall}</h1>
<p class="note">챗봇이 넘긴 상담·반품 건입니다. 텔레그램/메일 알림과 같은 기록입니다.</p>
<table>
<thead><tr><th>시각</th><th>유형</th><th>내용</th><th>알림상태</th></tr></thead>
<tbody>
{body_rows}
</tbody></table>
</body></html>"""
    return HTMLResponse(page)
