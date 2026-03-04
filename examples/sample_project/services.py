"""
File 5: services.py — External service calls with no retry logic.
"""
import time
import random


def send_notification(user_email: str, message: str):
    """Send email notification — no retry, no timeout guard."""
    time.sleep(random.uniform(0.1, 2.0))  # simulate network call
    if random.random() < 0.3:
        raise ConnectionError(f"SMTP server unreachable for {user_email}")
    return {"sent": True, "to": user_email}


def fetch_pricing(item: str):
    """Fetch price from external pricing service — no cache, no fallback."""
    time.sleep(random.uniform(0.05, 1.5))
    if random.random() < 0.2:
        raise TimeoutError("Pricing service timeout")
    prices = {"widget": 9.99, "gadget": 24.99}
    return prices.get(item, 0.0)


def process_payment(amount: float, card_token: str):
    """Process payment — no idempotency key, no retry."""
    if amount <= 0:
        raise ValueError("Invalid payment amount")
    time.sleep(random.uniform(0.1, 0.5))
    if random.random() < 0.15:
        raise RuntimeError("Payment gateway returned HTTP 500")
    return {"status": "charged", "amount": amount}
