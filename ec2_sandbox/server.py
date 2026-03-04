"""
server.py — EC2 Sandbox Server for BlastShield.
Receives scan requests from Lambda, runs code in Docker, returns results.

Usage:
    pip install -r requirements.txt
    python server.py
"""
import json
import logging
import os
import shutil
import tempfile
import uuid
import zipfile

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from docker_runner import run_in_docker
from groq_analyzer import analyze_with_groq

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="BlastShield Sandbox Server", version="2.0")

WORKSPACE_ROOT = "/tmp/blastshield"


class SandboxRequest(BaseModel):
    scan_id: str
    s3_bucket: str
    s3_key: str
    timeout: int = 10


@app.get("/health")
def health():
    return {"status": "ok", "service": "sandbox"}


@app.post("/run-sandbox")
async def run_sandbox(req: SandboxRequest):
    """Download project from S3, run in Docker, return results."""
    workspace = os.path.join(WORKSPACE_ROOT, req.scan_id)

    try:
        # ── Step 1: Download from S3 ──────────────────────────
        os.makedirs(workspace, exist_ok=True)
        zip_path = os.path.join(workspace, "project.zip")

        logger.info(f"Downloading s3://{req.s3_bucket}/{req.s3_key}")
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        s3.download_file(req.s3_bucket, req.s3_key, zip_path)

        # ── Step 2: Unzip ─────────────────────────────────────
        project_dir = os.path.join(workspace, "project")
        os.makedirs(project_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(project_dir)
        logger.info(f"Extracted to {project_dir}")

        # ── Step 3: Run in Docker ─────────────────────────────
        docker_result = run_in_docker(
            project_dir=project_dir,
            timeout=req.timeout,
        )

        # ── Step 4: Groq AI analysis (optional) ───────────────
        groq_analysis = None
        if docker_result.get("runtime_errors") or docker_result.get("container_exit_code", 0) != 0:
            groq_analysis = analyze_with_groq(
                logs=docker_result.get("logs", ""),
                errors=docker_result.get("runtime_errors", []),
            )

        # ── Step 5: Build response ────────────────────────────
        result = {
            "deployment_status": docker_result.get("deployment_status", "unknown"),
            "runtime_errors": docker_result.get("runtime_errors", []),
            "logs": docker_result.get("logs", ""),
            "endpoint_results": docker_result.get("endpoint_results", {}),
            "container_exit_code": docker_result.get("container_exit_code", -1),
        }

        if groq_analysis:
            result["groq_analysis"] = groq_analysis

        return JSONResponse(content=result)

    except ClientError as e:
        logger.error(f"S3 download failed: {e}")
        return JSONResponse(content={
            "deployment_status": "s3_error",
            "runtime_errors": [str(e)],
            "logs": "",
            "endpoint_results": {},
            "container_exit_code": -1,
        })
    except Exception as e:
        logger.exception(f"Sandbox error: {e}")
        return JSONResponse(content={
            "deployment_status": "failure",
            "runtime_errors": [str(e)],
            "logs": "",
            "endpoint_results": {},
            "container_exit_code": -1,
        })
    finally:
        # Cleanup workspace
        if os.path.exists(workspace):
            shutil.rmtree(workspace, ignore_errors=True)
            logger.info(f"Cleaned up {workspace}")


if __name__ == "__main__":
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=9000)
