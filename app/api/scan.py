"""
scan.py — POST /scan endpoint. Orchestrates the full simulation pipeline.
"""
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.extract import (
    extract_files_from_code,
    extract_files_from_zip,
    detect_endpoints,
)
from app.core.drills import (
    run_concurrency_drill,
    run_latency_drill,
    run_chaos_drill,
)
from app.core.edge_cases import run_edge_cases
from app.core.curl_runner import run_curl_tests
from app.ai.bedrock import invoke_bedrock, FALLBACK_RESPONSE
from app.ai.prompt import build_bedrock_prompt

logger = logging.getLogger(__name__)
router = APIRouter()

# Maximum execution budget (seconds)
MAX_EXECUTION_TIME = 3.5


def _compute_overall_score(
    drills: dict,
    edge_cases: list[dict],
    curl_results: list[dict],
) -> int:
    """
    Compute a 0-100 reliability score.
    Higher = more reliable. Deductions for each issue found.
    """
    score = 100

    # Deduct for concurrency issues
    for issue in drills.get("concurrency", []):
        if issue.get("severity") == "high":
            score -= 15
        elif issue.get("severity") == "medium":
            score -= 8
        else:
            score -= 3

    # Deduct for latency issues
    for issue in drills.get("latency", []):
        if issue.get("severity") == "high":
            score -= 10
        else:
            score -= 3

    # Deduct for chaos issues
    for issue in drills.get("chaos", []):
        if issue.get("severity") == "critical":
            score -= 12
        elif issue.get("severity") == "high":
            score -= 8
        else:
            score -= 3

    # Deduct for edge case failures
    for ec in edge_cases:
        if ec.get("result") == "crashed":
            score -= 5
        elif ec.get("result") == "failed":
            score -= 2

    # Deduct for curl test failures
    for cr in curl_results:
        if cr.get("verdict") == "critical":
            score -= 10
        elif cr.get("verdict") == "degraded":
            score -= 5

    return max(0, min(100, score))


async def _extract_input(request: Request) -> tuple:
    """
    Flexibly extract code or zip file from the request.
    Supports: JSON body, form-urlencoded, multipart/form-data.
    """
    content_type = request.headers.get("content-type", "")

    # 1. JSON body: {"code": "..."}
    if "application/json" in content_type:
        body = await request.json()
        code = body.get("code")
        if code:
            return "code", code
        raise HTTPException(400, "JSON body must contain a 'code' field.")

    # 2. Multipart form-data (file upload or code field)
    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload and hasattr(upload, "filename") and upload.filename:
            if not upload.filename.endswith(".zip"):
                raise HTTPException(400, "Only .zip files are supported.")
            zip_bytes = await upload.read()
            return "zip", zip_bytes
        code = form.get("code")
        if code:
            return "code", str(code)
        raise HTTPException(400, "Multipart form must contain 'file' (zip) or 'code' field.")

    # 3. Form-urlencoded: code=...
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        code = form.get("code")
        if code:
            return "code", str(code)
        raise HTTPException(400, "Form must contain a 'code' field.")

    raise HTTPException(400, "Unsupported content type. Use JSON, form-urlencoded, or multipart/form-data.")


@router.post("/scan")
async def scan(request: Request):
    """
    Production Failure Simulator endpoint.
    Accepts raw Python code OR a .zip file upload.
    Returns full simulation results including Bedrock AI analysis.
    """
    start_time = time.monotonic()

    try:
        # ── Step 1: Extract files ──────────────────────────────
        input_type, input_data = await _extract_input(request)
        if input_type == "zip":
            files = extract_files_from_zip(input_data)
            if not files:
                raise HTTPException(400, "No .py files found in the zip archive.")
        else:
            files = extract_files_from_code(input_data)

        # ── Step 2: Detect endpoints ───────────────────────────
        endpoints = detect_endpoints(files)

        # ── Step 3: Run drills ─────────────────────────────────
        concurrency = run_concurrency_drill(files)
        latency = run_latency_drill(files)
        chaos = run_chaos_drill(files)

        drills = {
            "concurrency": concurrency,
            "latency": latency,
            "chaos": chaos,
        }

        # ── Step 4: Edge case tests ────────────────────────────
        edge_cases = run_edge_cases(endpoints) if endpoints else []

        # ── Step 5: Curl-style load tests ──────────────────────
        curl_results = run_curl_tests(endpoints)

        # ── Step 6: Overall score ──────────────────────────────
        overall_score = _compute_overall_score(drills, edge_cases, curl_results)

        # ── Step 7: Bedrock AI call ────────────────────────────
        elapsed = time.monotonic() - start_time
        if elapsed < MAX_EXECUTION_TIME:
            prompt = build_bedrock_prompt(
                files, endpoints, concurrency, latency, chaos,
                edge_cases, curl_results,
            )
            bedrock_story = invoke_bedrock(prompt)
        else:
            logger.warning(f"Skipping Bedrock — {elapsed:.1f}s elapsed, budget exceeded.")
            bedrock_story = FALLBACK_RESPONSE

        # ── Build response ─────────────────────────────────────
        return JSONResponse(content={
            "overall_score": overall_score,
            "files": [{"file": f["file"], "lines": len(f["content"].splitlines())} for f in files],
            "endpoints": endpoints,
            "drills": drills,
            "edge_cases": edge_cases,
            "curl_results": curl_results,
            "bedrock_story": bedrock_story,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Scan failed — returning fallback response.")
        return JSONResponse(
            status_code=200,
            content={
                "overall_score": 0,
                "files": [],
                "endpoints": [],
                "drills": {"concurrency": [], "latency": [], "chaos": []},
                "edge_cases": [],
                "curl_results": [],
                "bedrock_story": FALLBACK_RESPONSE,
                "error": str(e),
            },
        )
