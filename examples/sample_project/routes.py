"""
File 3: routes.py — API routes with intentional reliability gaps.
"""
from fastapi import APIRouter

router = APIRouter()

inventory = {"widget": 100, "gadget": 50}
order_log = []


@router.post("/create")
def create_order(data: dict):
    item = data["item"]  # no KeyError guard
    qty = data["quantity"]  # no type check
    if inventory.get(item, 0) >= qty:
        inventory[item] -= qty  # race condition: not atomic
        order_log.append(data)
        return {"status": "created", "remaining": inventory[item]}
    return {"status": "out_of_stock"}


@router.get("/orders")
def list_orders():
    return {"orders": order_log, "count": len(order_log)}


@router.get("/inventory/{item}")
def get_inventory(item: str):
    return {"item": item, "stock": inventory[item]}  # KeyError if item not found


@router.delete("/orders/{order_id}")
def delete_order(order_id: int):
    if order_id < len(order_log):
        removed = order_log.pop(order_id)  # index shift bug
        return {"status": "deleted", "order": removed}
    return {"status": "not_found"}

# Documented code

# Documented code
