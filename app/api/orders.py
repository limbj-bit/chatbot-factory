from fastapi import APIRouter, HTTPException, status
from app.application.order_service import OrderService
from app.schemas.order import OrderItemSchema, OrderResponse

router = APIRouter(prefix="/api/orders", tags=["Orders"])
order_service = OrderService()


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
