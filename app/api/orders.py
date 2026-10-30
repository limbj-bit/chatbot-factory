from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.commerce_service import commerce_service
from app.application.order_service import OrderService
from app.core.security import encryption_available
from app.infrastructure.database.session import get_db
from app.schemas.order import OrderItemSchema, OrderResponse

router = APIRouter(prefix="/api/orders", tags=["Orders"])
order_service = OrderService()

# Customer-facing generic message (no internal details)
_LOOKUP_UNAVAILABLE = "주문 조회가 일시 점검 중입니다. 잠시 후 다시 시도해 주세요."


def _redirect_uri(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/orders/oauth/callback"


@router.get("/oauth/cafe24/start", include_in_schema=False)
async def cafe24_oauth_start(
    request: Request,
    mall_id: str = Query(..., description="Our store mall_id (not the Cafe24 mall id)"),
    session: AsyncSession = Depends(get_db),
):
    """Redirect owner to Cafe24 OAuth (read_order + write_order for AS cancel/return)."""
    if not encryption_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="암호화 키(ENCRYPTION_KEY)가 설정되지 않아 카페24 연동을 시작할 수 없습니다.",
        )

    conn = await commerce_service.get_connection(session, mall_id)
    if conn is None or not conn.client_id or not conn.cafe24_mall_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="카페24 API 키가 저장되지 않았습니다. 먼저 쇼룸에서 Client ID/Secret을 입력해 주세요.",
        )

    state = await commerce_service.create_oauth_state(mall_id)
    redirect_uri = _redirect_uri(request)
    # write_order required for cancel / return / exchange; re-auth if app scope was read-only
    scope = "mall.read_order,mall.write_order"
    from urllib.parse import quote

    authorize_url = (
        f"https://{conn.cafe24_mall_id}.cafe24api.com/api/v2/oauth/authorize"
        f"?response_type=code&client_id={conn.client_id}"
        f"&state={state}&redirect_uri={quote(redirect_uri, safe='')}"
        f"&scope={quote(scope, safe=',')}"
    )
    return RedirectResponse(authorize_url)


@router.get("/oauth/callback", include_in_schema=False)
async def cafe24_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_db),
):
    """Receive the authorization code, exchange it for tokens, and store them encrypted."""
    if not code or not state:
        return HTMLResponse("<h3>카페24 권한 허용이 취소되었거나 코드가 없습니다.</h3>", status_code=400)

    mall_id = await commerce_service.consume_oauth_state(state)
    if not mall_id:
        return HTMLResponse("<h3>잘못되었거나 만료된 요청입니다. 다시 시도해 주세요.</h3>", status_code=400)

    conn = await commerce_service.get_connection(session, mall_id)
    if conn is None:
        return HTMLResponse("<h3>연동 정보를 찾을 수 없습니다. 쇼룸에서 다시 설정해 주세요.</h3>", status_code=404)

    ok = await commerce_service.exchange_code_for_tokens(session, conn, code, _redirect_uri(request))
    if not ok:
        return HTMLResponse("<h3>카페24 토큰 발급에 실패했습니다. 잠시 후 다시 시도해 주세요.</h3>", status_code=502)

    store_label = conn.cafe24_mall_id or mall_id
    return HTMLResponse(
        f"""
        <html><head><meta charset='utf-8'><title>카페24 연동 완료</title></head>
        <body style='font-family:sans-serif;text-align:center;padding:60px 20px;'>
          <h2 style='color:#16A34A;'>✅ {store_label} 카페24 연동 완료</h2>
          <p>이제 챗봇 조회 박스에 실제 주문번호를 넣으면<br>진짜 배송 상태 · 상품명 · 운송장 번호가 바로 나옵니다.</p>
          <p style='color:#64748B;font-size:13px;'>이 창을 닫고 챗봇으로 돌아가세요.</p>
        </body></html>
        """
    )


@router.get("/lookup", response_model=OrderResponse)
async def lookup_order_endpoint(
    mall_id: str = Query(..., description="Store mall_id with a live Cafe24 connection"),
    order_id: str = Query(..., description="Cafe24 order number (e.g. 20261028-0000012)"),
    session: AsyncSession = Depends(get_db),
):
    """Live order lookup via the mall's own Cafe24 token. Never returns PII."""
    order, err = await commerce_service.lookup_order(session, mall_id, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=err or _LOOKUP_UNAVAILABLE)

    return OrderResponse(
        order_id=order.order_id,
        customer_id=order.customer_id,
        status=order.status.value,
        total_amount=order.total_amount,
        channel=order.channel.value,
        delivered_at=order.delivered_at.isoformat() if order.delivered_at else None,
        carrier_name=order.carrier_name,
        shipping_code=order.shipping_code,
        items=[
            OrderItemSchema(
                item_id=it.item_id,
                product_name=it.product_name,
                quantity=it.quantity,
                unit_price=it.unit_price,
                total_price=it.total_price,
            )
            for it in order.items
        ],
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order_endpoint(order_id: str):
    order = await order_service.get_order_details(order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found",
        )

    return OrderResponse(
        order_id=order.order_id,
        customer_id=order.customer_id,
        status=order.status.value,
        total_amount=order.total_amount,
        channel=order.channel.value,
        delivered_at=order.delivered_at.isoformat() if order.delivered_at else None,
        carrier_name=order.carrier_name,
        shipping_code=order.shipping_code,
        items=[
            OrderItemSchema(
                item_id=it.item_id,
                product_name=it.product_name,
                quantity=it.quantity,
                unit_price=it.unit_price,
                total_price=it.total_price,
            )
            for it in order.items
        ],
    )
