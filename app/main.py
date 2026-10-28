from contextlib import asynccontextmanager
import os
import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api import (
    admin_router,
    chat_router,
    claims_router,
    health_router,
    orders_router,
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

# Mount static files for embeddable widget and demo page
static_dir = os.path.abspath("static")
if not os.path.exists(static_dir):
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_root_showroom():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/showroom", include_in_schema=False)
async def serve_customer_showroom():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/admin", include_in_schema=False)
async def serve_master_admin_console():
    return FileResponse(os.path.join(static_dir, "admin.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
