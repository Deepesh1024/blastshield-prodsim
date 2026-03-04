"""
ec2_client.py — Send execution requests to the EC2 Sandbox Server.
"""
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

EC2_SANDBOX_URL = os.environ.get("EC2_SANDBOX_URL", "http://localhost:9000")

FALLBACK_RESULT = {
    "deployment_status": "skipped",
    "runtime_errors": [],
    "logs": "EC2 sandbox unavailable — skipped runtime validation.",
    "endpoint_results": {},
    "container_exit_code": -1,
}


def send_to_sandbox(
    scan_id: str,
    s3_bucket: str,
    s3_key: str,
    timeout: int = 10,
    sandbox_url: str = None,
) -> dict:
    """
    POST execution request to EC2 sandbox server.
    Returns runtime results or fallback on failure.
    """
    url = (sandbox_url or EC2_SANDBOX_URL).rstrip("/") + "/run-sandbox"
    payload = {
        "scan_id": scan_id,
        "s3_bucket": s3_bucket,
        "s3_key": s3_key,
        "timeout": timeout,
    }

    try:
        with httpx.Client(timeout=max(timeout + 10, 25)) as client:
            resp = client.post(url, json=payload)

        if resp.status_code == 200:
            result = resp.json()
            logger.info(f"✅ Sandbox returned: status={result.get('deployment_status')}")
            return result

        logger.warning(f"Sandbox returned HTTP {resp.status_code}: {resp.text[:200]}")
        return FALLBACK_RESULT

    except httpx.TimeoutException:
        logger.warning(f"Sandbox call timed out after {timeout + 10}s")
        return {**FALLBACK_RESULT, "deployment_status": "timeout"}
    except httpx.ConnectError:
        logger.warning(f"Cannot connect to sandbox at {url}")
        return FALLBACK_RESULT
    except Exception as e:
        logger.warning(f"Sandbox call failed: {e}")
        return FALLBACK_RESULT
