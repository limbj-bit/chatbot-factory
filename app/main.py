from contextlib import asynccontextmanager
import os
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import httpx
from app.api import (
    admin_router,
    chat_router,
    claims_router,
    health_router,
    orders_router,
    staff_inbox_router,
    stores_router,
    widget_router,
)
from app.core.config import settings
from app.core.logging import correlation_id_ctx, logger
from app.infrastructure.database.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    await init_db()
    logger.info("Database initialized successfully.")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description="Fresh Food E-commerce AI CS + Photo Claim Analysis + Return/Refund Automation Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS Middleware (Allow all origins for multi-tenant embeddable widget in production)
cors_origins = ["*"] if settings.APP_ENV == "production" else settings.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    token = correlation_id_ctx.set(cid)
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response
    finally:
        correlation_id_ctx.reset(token)


# Include API Routers
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(claims_router)
app.include_router(orders_router)
app.include_router(admin_router)
app.include_router(stores_router)
app.include_router(widget_router)
app.include_router(staff_inbox_router)

# Mount static files for embeddable widget and demo page
static_dir = os.path.abspath("static")
if not os.path.exists(static_dir):
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_root_showroom():
    return FileResponse(
        os.path.join(static_dir, "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate, max-age=0"},
    )


@app.get("/showroom", include_in_schema=False)
async def serve_customer_showroom():
    return FileResponse(
        os.path.join(static_dir, "index.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate, max-age=0"},
    )


@app.get("/admin", include_in_schema=False)
async def serve_master_admin_console():
    return FileResponse(os.path.join(static_dir, "admin.html"))


@app.get("/api/system/schema-status", tags=["System"])
async def get_schema_status():
    """Diagnose stores.brand_logo_url drift and self-heal lightweight ALTERs."""
    from sqlalchemy import text
    from app.infrastructure.database.session import apply_lightweight_migrations, async_session_factory

    out: dict = {
        "deploy_marker": "schema-heal-v1",
        "ok": False,
        "stores_columns": None,
        "probe_error": None,
        "migrate_ran": False,
    }
    async with async_session_factory() as session:
        try:
            try:
                rows = (await session.execute(text("PRAGMA table_info(stores)"))).fetchall()
                out["stores_columns"] = [r[1] for r in rows]
            except Exception:
                rows = (
                    await session.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'stores'"
                        )
                    )
                ).fetchall()
                out["stores_columns"] = [r[0] for r in rows]

            await session.execute(text("SELECT brand_logo_url FROM stores LIMIT 1"))
            out["ok"] = True
        except Exception as e:
            out["probe_error"] = f"{type(e).__name__}: {e}"
            try:
                await session.rollback()
            except Exception:
                pass
            await apply_lightweight_migrations()
            out["migrate_ran"] = True
            try:
                await session.execute(text("SELECT brand_logo_url FROM stores LIMIT 1"))
                out["ok"] = True
                out["probe_error_after_migrate"] = None
                try:
                    rows = (await session.execute(text("PRAGMA table_info(stores)"))).fetchall()
                    out["stores_columns"] = [r[1] for r in rows]
                except Exception:
                    pass
            except Exception as e2:
                out["probe_error_after_migrate"] = f"{type(e2).__name__}: {e2}"
    return out


@app.get("/api/system/server-info", tags=["System"])
async def get_server_integration_info(request: Request):
    """Return the server's permanent static outbound IPs (for Coupang Wing IP whitelist) and base callback URLs."""
    static_ips = settings.STATIC_OUTBOUND_IPS.strip()
    detected_ip = ""
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("https://api.ipify.org?format=json")
            if resp.status_code == 200:
                detected_ip = resp.json().get("ip", "")
    except Exception:
        detected_ip = ""

    def _ip_in_static_ranges(ip: str) -> bool:
        import ipaddress

        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for part in static_ips.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                if addr in ipaddress.ip_network(part, strict=False):
                    return True
            except ValueError:
                continue
        return False

    if detected_ip and not _ip_in_static_ranges(detected_ip):
        outbound_ip = f"{static_ips}, {detected_ip}" if static_ips else detected_ip
    else:
        outbound_ip = static_ips or detected_ip or "74.220.49.0/24, 74.220.57.0/24"

    base_url = str(request.base_url).rstrip("/")
    return {
        "outbound_ip": outbound_ip,
        "static_outbound_ips": static_ips,
        "base_url": base_url,
        "oauth_redirect_uri": f"{base_url}/api/orders/oauth/callback",
        "order_webhook_url": f"{base_url}/api/orders/webhook",
    }


@app.get("/chat/{mall_id}", response_class=HTMLResponse, include_in_schema=False)
async def serve_direct_store_chat_page(mall_id: str):
    """Standalone mobile/desktop full-view AI chat landing page for SmartStore, Coupang, Instagram, and QR codes."""
    safe_mall = mall_id.replace('"', "").replace("<", "").replace(">", "")
    html_page = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>24시간 AI 고객상담 & 사진 판독 센터</title>
  <link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    body {{
      margin: 0; padding: 24px; font-family: "Pretendard", sans-serif;
      background: radial-gradient(circle at 20% 0%, #FFFFFF 0%, #FDFBF7 55%, #F7F3EA 100%);
      color: #1E293B; display: flex; flex-direction: column; align-items: center; min-height: 100vh;
    }}
    .welcome-card {{
      max-width: 520px; width: 100%; background: #FFFFFF; border: 1.5px solid #F2DFB6;
      border-radius: 20px; padding: 22px 24px; text-align: center;
      box-shadow: 0 14px 36px rgba(180, 150, 95, 0.12); margin-bottom: 16px;
    }}
    .welcome-card h2 {{ margin: 0 0 8px; font-size: 20px; color: #1E293B; }}
    .welcome-card p {{ margin: 0; font-size: 13.5px; color: #64748B; line-height: 1.55; }}
    /* Automatically center and expand widget on standalone link */
    .fresh-widget-window {{
      display: flex !important;
      position: fixed !important;
      bottom: 24px !important;
      right: 50% !important;
      transform: translateX(50%) !important;
      width: min(440px, calc(100vw - 24px)) !important;
      height: min(680px, calc(100vh - 150px)) !important;
    }}
    .fresh-widget-launcher {{ display: none !important; }}
  </style>
</head>
<body>
  <div class="welcome-card">
    <h2>✨ 24시간 AI 스마트 상담 & 사진 판독 센터</h2>
    <p>네이버 스마트스토어 · 쿠팡 · 공식몰 통합 상담창입니다.<br>아래 채팅창에 궁금한 점을 입력하시거나 <b>📷 상품 사진</b>을 올려주세요!</p>
  </div>
  <script src="/api/widget/script?mall_id={safe_mall}" async></script>
</body>
</html>"""
    return HTMLResponse(content=html_page)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
