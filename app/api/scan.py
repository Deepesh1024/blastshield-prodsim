"""
scan.py — POST /scan endpoint. Orchestrates the full simulation pipeline.
V2: Adds scan_id, S3 upload, EC2 sandbox execution, and merged results.
"""
import io
import json
import logging
import time
import uuid
import zipfile
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
from app.core.s3_storage import upload_artifact
from app.core.ec2_client import send_to_sandbox, FALLBACK_RESULT
from app.core.call_graph import build_interaction_map
from app.ai.bedrock import invoke_bedrock, FALLBACK_RESPONSE
from app.ai.prompt import build_bedrock_prompt

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_EXECUTION_TIME = 25  # budget raised for EC2 round-trip


def _compute_overall_score(
    drills: dict,
    edge_cases: list[dict],
    curl_results: list[dict],
    deployment: dict,
) -> int:
    """
    Compute 0-100 reliability score.
    Higher = more reliable. Deductions for each issue found.
    """
    score = 100

    # Deduct for concurrency issues
    for issue in drills.get("concurrency", []):
        sev = issue.get("severity", "low")
        score -= {"high": 15, "medium": 8}.get(sev, 3)

    # Deduct for latency issues
    for issue in drills.get("latency", []):
        score -= 10 if issue.get("severity") == "high" else 3

    # Deduct for chaos issues
    for issue in drills.get("chaos", []):
        sev = issue.get("severity", "low")
        score -= {"critical": 12, "high": 8}.get(sev, 3)

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

    # Deduct for deployment/runtime failures
    if deployment.get("deployment_status") == "failure":
        score -= 20
    if deployment.get("runtime_errors"):
        score -= min(len(deployment["runtime_errors"]) * 5, 25)

    return max(0, min(100, score))


def _files_to_zip_bytes(files: list[dict]) -> bytes:
    """Convert extracted files list to a zip archive in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.writestr(f["file"], f["content"])
    return buf.getvalue()


async def _extract_input(request: Request) -> tuple:
    """
    Flexibly extract code or zip file from the request.
    Supports: JSON body, form-urlencoded, multipart/form-data.
    Now also extracts optional 'scenario' dictionary.
    """
    content_type = request.headers.get("content-type", "")
    scenario = None

    # 1. JSON body: {"code": "...", "scenario": {...}}
    if "application/json" in content_type:
        body = await request.json()
        code = body.get("code")
        scenario = body.get("scenario")
        if code:
            return "code", code, scenario
        raise HTTPException(400, "JSON body must contain a 'code' field.")

    # 2. Multipart form-data (file upload or code field)
    if "multipart/form-data" in content_type:
        form = await request.form()
        
        # Scenario from form field (likely stringified JSON)
        scenario_raw = form.get("scenario")
        if scenario_raw:
            try:
                scenario = json.loads(str(scenario_raw))
            except:
                pass

        upload = form.get("file")
        if upload and hasattr(upload, "filename") and upload.filename:
            if not upload.filename.endswith(".zip"):
                raise HTTPException(400, "Only .zip files are supported.")
            zip_bytes = await upload.read()
            return "zip", zip_bytes, scenario
        code = form.get("code")
        if code:
            return "code", str(code), scenario
        raise HTTPException(400, "Multipart form must contain 'file' (zip) or 'code' field.")

    # 3. Form-urlencoded: code=...
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        code = form.get("code")
        if code:
            return "code", str(code), None
        raise HTTPException(400, "Form must contain a 'code' field.")

    raise HTTPException(400, "Unsupported content type. Use JSON, form-urlencoded, or multipart/form-data.")


@router.post("/scan")
async def scan(request: Request):
    """
    Production Failure Simulator endpoint.
    V2: Full pipeline with S3 upload, EC2 sandbox execution, and AI analysis.
    """
    start_time = time.monotonic()
    scan_id = str(uuid.uuid4())

    try:
        # ── Step 1: Extract files ──────────────────────────────
        input_type, input_data, scenario = await _extract_input(request)
        if input_type == "zip":
            files = extract_files_from_zip(input_data)
            zip_bytes = input_data  # already a zip
            if not files:
                raise HTTPException(400, "No .py files found in the zip archive.")
        else:
            files = extract_files_from_code(input_data)
            zip_bytes = _files_to_zip_bytes(files)

        # ── Step 2: Upload to S3 ──────────────────────────────
        s3_result = upload_artifact(scan_id, zip_bytes)
        s3_info = s3_result or {"bucket": "unavailable", "key": "unavailable"}

        # ── Step 3: Detect endpoints ──────────────────────────
        endpoints = detect_endpoints(files)

        # ── Step 4: Run local drills ──────────────────────────
        concurrency = run_concurrency_drill(files, scenario=scenario)
        latency = run_latency_drill(files, scenario=scenario)
        chaos = run_chaos_drill(files, scenario=scenario)

        drills = {
            "concurrency": concurrency,
            "latency": latency,
            "chaos": chaos,
        }

        # ── Step 5: Edge case tests ───────────────────────────
        edge_cases = run_edge_cases(endpoints) if endpoints else []

        # ── Step 6: Curl-style load tests ─────────────────────
        curl_results = run_curl_tests(endpoints)

        # ── Step 7: EC2 sandbox execution ─────────────────────
        if s3_result:
            deployment = send_to_sandbox(
                scan_id=scan_id,
                s3_bucket=s3_info["bucket"],
                s3_key=s3_info["key"],
                timeout=10,
            )
        else:
            deployment = {**FALLBACK_RESULT, "deployment_status": "s3_unavailable"}

        # ── Step 8: Overall score ─────────────────────────────
        overall_score = _compute_overall_score(drills, edge_cases, curl_results, deployment)

        # ── Step 9: Bedrock AI analysis ───────────────────────
        elapsed = time.monotonic() - start_time
        if elapsed < MAX_EXECUTION_TIME:
            prompt = build_bedrock_prompt(
                files, endpoints, concurrency, latency, chaos,
                edge_cases, curl_results,
                scenario=scenario,
            )
            bedrock_story = invoke_bedrock(prompt)
        else:
            logger.warning(f"Skipping Bedrock — {elapsed:.1f}s elapsed.")
            bedrock_story = FALLBACK_RESPONSE

        # ── Step 10: Service Interaction Map ───────────────────
        interaction_map = build_interaction_map(
            files, bedrock_story.get("failure_points")
        )

        # ── Build response ────────────────────────────────────
        return JSONResponse(content={
            "scan_id": scan_id,
            "overall_score": overall_score,
            "simulation_results": {
                "files": [{"file": f["file"], "lines": len(f["content"].splitlines())} for f in files],
                "endpoints": endpoints,
                "drills": drills,
                "edge_cases": edge_cases,
                "curl_results": curl_results,
            },
            "interaction_map": interaction_map,
            "deployment_validation": deployment,
            "ai_analysis": bedrock_story,
            "s3_artifact": s3_info,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Scan failed — returning fallback response.")
        return JSONResponse(
            status_code=200,
            content={
                "scan_id": scan_id,
                "overall_score": 0,
                "simulation_results": {
                    "files": [],
                    "endpoints": [],
                    "drills": {"concurrency": [], "latency": [], "chaos": []},
                    "edge_cases": [],
                    "curl_results": [],
                },
                "deployment_validation": FALLBACK_RESULT,
                "ai_analysis": FALLBACK_RESPONSE,
                "error": str(e),
            },
        )

# Documented code

# Documented code
