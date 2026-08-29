"""Order creation and stock reservation."""


class OutOfStockError(Exception):
    pass


class OrderService:
    def __init__(self, orders, inventory, events):
        self.orders = orders
        self.inventory = inventory
        self.events = events

    async def create_order(self, customer_id: str, sku: str, quantity: int):
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        reserved = await self.inventory.reserve(sku, quantity)
        if not reserved:
            raise OutOfStockError(sku)
        order = await self.orders.insert(customer_id=customer_id, sku=sku, quantity=quantity)
        await self.events.publish("order.created", {"order_id": order.id})
        return order

