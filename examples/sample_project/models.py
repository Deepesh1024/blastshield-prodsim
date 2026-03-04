"""
File 2: models.py — Data models (no Pydantic validation on purpose).
"""


class Order:
    def __init__(self, item: str, quantity: int, price: float):
        self.item = item
        self.quantity = quantity
        self.price = price
        self.total = quantity * price  # no validation!


class User:
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email
