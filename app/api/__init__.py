from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.claims import router as claims_router
from app.api.health import router as health_router
from app.api.orders import router as orders_router

__all__ = ["admin_router", "chat_router", "claims_router", "health_router", "orders_router"]
