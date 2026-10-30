from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.claims import router as claims_router
from app.api.health import router as health_router
from app.api.orders import router as orders_router
from app.api.staff_inbox import router as staff_inbox_router
from app.api.stores import router as stores_router
from app.api.widget import router as widget_router

__all__ = [
    "admin_router",
    "chat_router",
    "claims_router",
    "health_router",
    "orders_router",
    "staff_inbox_router",
    "stores_router",
    "widget_router",
]
