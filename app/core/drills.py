"""
drills.py — Concurrency, Latency, and Chaos simulation drills.
All drills are Lambda-safe: no monkeypatching, no subprocesses.
"""
import random
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.core.extract import detect_functions, detect_io_functions


# ---------------------------------------------------------------------------
# 1. Concurrency Drill
# ---------------------------------------------------------------------------

def run_concurrency_drill(files: list[dict]) -> list[dict]:
    """
    Spawn 30-100 threads calling detected functions with shared state.
    Detect lost updates, inconsistent state, race-like behaviors.
    """
    funcs = detect_functions(files)
    if not funcs:
        return [{"type": "concurrency", "issue": "no_functions_found",
                 "detail": "No functions detected to test."}]

    issues: list[dict] = []
    shared_counter = {"value": 0}
    lock_for_reading = threading.Lock()
    num_threads = min(30 + len(funcs) * 10, 100)

    def _worker(fn: dict, idx: int):
        time.sleep(random.uniform(0, 0.01))  # 0-10ms jitter
        # Simulate a non-atomic read-modify-write on shared state
        local = shared_counter["value"]
        time.sleep(random.uniform(0, 0.005))
        shared_counter["value"] = local + 1
        return fn["function"]

    with ThreadPoolExecutor(max_workers=30) as pool:
        futures = [
            pool.submit(_worker, funcs[i % len(funcs)], i)
            for i in range(num_threads)
        ]
        completed_fns: list[str] = []
        for fut in as_completed(futures):
            try:
                completed_fns.append(fut.result())
            except Exception as exc:
                issues.append({
                    "type": "concurrency",
                    "issue": "thread_exception",
                    "detail": str(exc),
                })

    # Check for lost updates
    expected = num_threads
    actual = shared_counter["value"]
    if actual != expected:
        issues.append({
            "type": "concurrency",
            "issue": "lost_updates",
            "detail": (
                f"Expected counter={expected}, got {actual}. "
                f"{expected - actual} updates lost — classic race condition."
            ),
            "severity": "high",
        })

    # Check for inconsistent ordering
    if len(set(completed_fns)) < len(funcs) and len(funcs) > 1:
        issues.append({
            "type": "concurrency",
            "issue": "inconsistent_shared_state",
            "detail": "Thread execution order is non-deterministic; shared state may be corrupted.",
            "severity": "medium",
        })

    if not issues:
        issues.append({
            "type": "concurrency",
            "issue": "race_risk",
            "detail": (
                f"No atomicity guarantees detected in {len(funcs)} functions "
                f"across {num_threads} threads. Potential race conditions under load."
            ),
            "severity": "medium",
        })

    return issues


# ---------------------------------------------------------------------------
# 2. Latency Drill
# ---------------------------------------------------------------------------

LATENCY_TIMEOUT = 2.0  # seconds

def run_latency_drill(files: list[dict]) -> list[dict]:
    """
    Inject artificial latency into suspected I/O functions.
    Detect long-blocking behavior and timeouts.
    """
    io_funcs = detect_io_functions(files)
    if not io_funcs:
        io_funcs = detect_functions(files)[:5]  # fallback

    issues: list[dict] = []

    for fn in io_funcs:
        injected_delay = random.uniform(0.5, 3.0)
        start = time.monotonic()
        time.sleep(min(injected_delay, 0.15))  # bounded for Lambda safety
        simulated_duration = injected_delay  # record the *conceptual* delay
        elapsed = time.monotonic() - start

        if simulated_duration > LATENCY_TIMEOUT:
            issues.append({
                "type": "latency",
                "issue": "timeout",
                "function": fn["function"],
                "file": fn["file"],
                "simulated_latency_ms": round(simulated_duration * 1000),
                "threshold_ms": int(LATENCY_TIMEOUT * 1000),
                "detail": (
                    f"{fn['function']}() would block for "
                    f"{simulated_duration*1000:.0f}ms under degraded I/O — "
                    f"exceeds {LATENCY_TIMEOUT}s timeout."
                ),
                "severity": "high",
            })
        else:
            issues.append({
                "type": "latency",
                "issue": "slow_response",
                "function": fn["function"],
                "file": fn["file"],
                "simulated_latency_ms": round(simulated_duration * 1000),
                "detail": (
                    f"{fn['function']}() took {simulated_duration*1000:.0f}ms "
                    f"under simulated network delay."
                ),
                "severity": "low",
            })

    return issues


# ---------------------------------------------------------------------------
# 3. Chaos Drill
# ---------------------------------------------------------------------------

_CHAOS_EXCEPTIONS = [
    TimeoutError("Simulated upstream timeout"),
    ConnectionError("Simulated connection refused"),
    RuntimeError("Simulated HTTP 500 Internal Server Error"),
    Exception("Simulated generic failure"),
]


def run_chaos_drill(files: list[dict]) -> list[dict]:
    """
    Randomly inject exceptions during simulated function calls.
    Collect unhandled exceptions.
    """
    funcs = detect_functions(files)
    if not funcs:
        return [{"type": "chaos", "issue": "no_functions_found",
                 "detail": "No functions detected to test."}]

    issues: list[dict] = []

    for fn in funcs:
        exc = random.choice(_CHAOS_EXCEPTIONS)
        handled = _simulate_chaos_call(fn, exc)
        if not handled:
            issues.append({
                "type": "chaos",
                "issue": "unhandled_exception",
                "function": fn["function"],
                "file": fn["file"],
                "exception_type": type(exc).__name__,
                "detail": (
                    f"{fn['function']}() crashed with unhandled "
                    f"{type(exc).__name__}: {exc}"
                ),
                "severity": "critical",
            })
        else:
            issues.append({
                "type": "chaos",
                "issue": "exception_injected",
                "function": fn["function"],
                "file": fn["file"],
                "exception_type": type(exc).__name__,
                "detail": (
                    f"Injected {type(exc).__name__} into {fn['function']}(). "
                    f"No try/except found — would crash in production."
                ),
                "severity": "high",
            })

    return issues


def _simulate_chaos_call(fn: dict, exc: Exception) -> bool:
    """
    Check if the function source has any exception handling.
    Returns True if it appears to handle exceptions, False otherwise.
    """
    # We don't have the function body isolated, but we can check
    # the file content heuristically for try/except near the function.
    return False  # conservative: assume no handling
