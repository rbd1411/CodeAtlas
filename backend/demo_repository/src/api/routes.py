"""TinyShop HTTP routes."""

from src.orders.service import OrderService, OutOfStockError


async def create_order_route(request, order_service: OrderService):
    payload = await request.json()
    try:
        order = await order_service.create_order(
            customer_id=request.state.claims.subject,
            sku=payload["sku"],
            quantity=payload["quantity"],
        )
    except OutOfStockError:
        return {"status": 409, "error": "out_of_stock"}
    return {"status": 201, "order_id": order.id}

