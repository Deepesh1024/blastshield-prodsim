"""
curl_runner.py — Simulated concurrent endpoint load tests.
No real HTTP — uses asyncio coroutines to simulate 20-40 concurrent "requests".
"""
import asyncio
import random
import time
from typing import Any


async def _simulate_request(
    endpoint: dict, request_id: int
) -> dict:
    """Simulate a single request to an endpoint with random outcomes."""
    start = time.monotonic()
    # Simulate variable processing time (5-200ms)
    delay = random.uniform(0.005, 0.2)
    await asyncio.sleep(min(delay, 0.05))  # cap actual sleep for Lambda

    simulated_ms = delay * 1000
    elapsed = (time.monotonic() - start) * 1000

    # Determine outcome based on simulated conditions
    roll = random.random()
    if roll < 0.12:
        status = "failed"
        detail = f"HTTP 500 — internal server error on request #{request_id}"
        status_code = 500
    elif roll < 0.20:
        status = "timed_out"
        detail = f"Request #{request_id} exceeded 2000ms timeout (simulated {simulated_ms:.0f}ms)"
        status_code = 504
    elif roll < 0.28:
        status = "inconsistent"
        detail = f"Request #{request_id} returned unexpected response shape"
        status_code = 200
    else:
        status = "passed"
        detail = f"Request #{request_id} completed in {simulated_ms:.0f}ms"
        status_code = 200

    return {
        "request_id": request_id,
        "status": status,
        "status_code": status_code,
        "simulated_latency_ms": round(simulated_ms, 1),
        "detail": detail,
    }


async def _run_endpoint_load(endpoint: dict) -> dict:
    """Run 20-40 concurrent simulated requests for a single endpoint."""
    num_requests = random.randint(20, 40)
    tasks = [
        _simulate_request(endpoint, i) for i in range(num_requests)
    ]
    results = await asyncio.gather(*tasks)

    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")
    timed_out = sum(1 for r in results if r["status"] == "timed_out")
    inconsistent = sum(1 for r in results if r["status"] == "inconsistent")

    latencies = [r["simulated_latency_ms"] for r in results]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    return {
        "endpoint": endpoint["path"],
        "method": endpoint["method"],
        "function": endpoint["function"],
        "total_requests": num_requests,
        "passed": passed,
        "failed": failed,
        "timed_out": timed_out,
        "inconsistent": inconsistent,
        "avg_latency_ms": round(avg_latency, 1),
        "p99_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0, 1),
        "success_rate": f"{(passed / num_requests) * 100:.1f}%",
        "verdict": "healthy" if failed + timed_out == 0 else "degraded" if (failed + timed_out) < num_requests * 0.3 else "critical",
    }


def run_curl_tests(endpoints: list[dict]) -> list[dict]:
    """
    Simulate concurrent load tests for all detected endpoints.
    Safe to call from sync context — creates its own event loop if needed.
    """
    if not endpoints:
        return [{
            "endpoint": "N/A",
            "method": "N/A",
            "total_requests": 0,
            "verdict": "skipped",
            "detail": "No endpoints detected for load testing.",
        }]

    async def _run_all():
        tasks = [_run_endpoint_load(ep) for ep in endpoints]
        return await asyncio.gather(*tasks)

    try:
        loop = asyncio.get_running_loop()
        # If we're inside an async context, schedule on the existing loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            results = pool.submit(lambda: asyncio.run(_run_all())).result(timeout=5)
    except RuntimeError:
        # No running loop — we can use asyncio.run directly
        results = asyncio.run(_run_all())

    return list(results)
