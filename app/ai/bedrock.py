"""
bedrock.py — Amazon Bedrock client with retry logic.
Supports:
  - Anthropic Prompt Router (Claude 3 Haiku ↔ Claude 3.5 Sonnet)
  - Amazon Nova Pro as fallback
  - Bearer token (Bedrock API Key) + IAM (boto3) auth
"""
import json
import os
import time
import logging
import urllib.parse
from typing import Any, Optional

import httpx
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Primary: Anthropic Prompt Router (routes between Claude 3 Haiku & 3.5 Sonnet)
ANTHROPIC_ROUTER = "arn:aws:bedrock:us-east-1::default-prompt-router/anthropic.claude:1"
# Fallback: Amazon Nova Pro (no marketplace subscription needed)
NOVA_MODEL = "us.amazon.nova-pro-v1:0"

REGION = os.environ.get("AWS_REGION", "us-east-1")
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0  # seconds

FALLBACK_RESPONSE = {
    "risk_score": 0,
    "severity": "UNKNOWN",
    "confidence": 0,
    "evidence": {
        "lost_updates": {"count": 0, "detail": "AI unavailable"},
        "timeouts": {"count": 0, "detail": "AI unavailable"},
        "exceptions": {"count": 0, "detail": "AI unavailable"},
        "slow_responses": {"count": 0, "detail": "AI unavailable"},
        "edge_failures": {"count": 0, "detail": "AI unavailable"},
    },
    "failure_points": {},
    "timeline": "AI analysis unavailable — drills completed but narrative generation failed.",
    "blast_radius": [],
    "explanation": "AI analysis was not available. Review the drill results for concurrency, latency, and chaos findings. "
                   "Check for shared mutable state, missing error handling, and unguarded I/O calls.",
    "patches": [],
}


def _get_bearer_token() -> Optional[str]:
    return os.environ.get("AWS_BEARER_TOKEN_BEDROCK")


def _extract_text(result: dict) -> str:
    """Extract response text — handles Converse, Nova, and Anthropic formats."""
    # Converse / Nova format: output.message.content[0].text
    output = result.get("output", {})
    if isinstance(output, dict):
        msg = output.get("message", {})
        content = msg.get("content", [])
        if content and isinstance(content[0], dict):
            return content[0].get("text", "")
    # Anthropic format: content[0].text
    content = result.get("content", [])
    if content and isinstance(content[0], dict):
        return content[0].get("text", "")
    return ""


# ── Bearer Token auth (Bedrock API Key) ───────────────────────────────────

def _invoke_with_bearer(prompt: str, token: str, model_id: str) -> Optional[dict]:
    """Invoke Bedrock using API Key bearer-token auth via direct HTTPS Converse API."""
    encoded_model = urllib.parse.quote(model_id, safe="")
    url = f"https://bedrock-runtime.{REGION}.amazonaws.com/model/{encoded_model}/converse"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = json.dumps({
        "messages": [
            {"role": "user", "content": [{"text": prompt}]}
        ],
        "inferenceConfig": {
            "maxTokens": 4096,
            "temperature": 0.3,
        },
    })

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(url, headers=headers, content=body)

            if resp.status_code == 200:
                result = resp.json()
                text = _extract_text(result)
                return _parse_bedrock_json(text)

            logger.warning(
                f"Bearer [{model_id[:40]}] attempt {attempt}/{MAX_RETRIES}: "
                f"HTTP {resp.status_code} — {resp.text[:200]}"
            )
        except Exception as e:
            logger.warning(f"Bearer [{model_id[:40]}] attempt {attempt}/{MAX_RETRIES} error: {e}")

        if attempt < MAX_RETRIES:
            time.sleep(min(INITIAL_BACKOFF * (2 ** (attempt - 1)), 0.5))

    return None


# ── Standard IAM auth (boto3 Converse API) ────────────────────────────────

def _invoke_with_boto3(prompt: str, model_id: str) -> Optional[dict]:
    """Invoke Bedrock using boto3 Converse API (works with all models + routers)."""
    try:
        client = boto3.client("bedrock-runtime", region_name=REGION)
    except Exception as e:
        logger.warning(f"Failed to create Bedrock client: {e}")
        return None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.converse(
                modelId=model_id,
                messages=[
                    {"role": "user", "content": [{"text": prompt}]}
                ],
                inferenceConfig={
                    "maxTokens": 4096,
                    "temperature": 0.3,
                },
            )
            text = _extract_text(response)
            return _parse_bedrock_json(text)

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            logger.warning(
                f"Boto3 [{model_id[:40]}] attempt {attempt}/{MAX_RETRIES} failed: {error_code} — {e}"
            )
        except Exception as e:
            logger.warning(f"Boto3 [{model_id[:40]}] attempt {attempt}/{MAX_RETRIES} error: {e}")

        if attempt < MAX_RETRIES:
            time.sleep(min(INITIAL_BACKOFF * (2 ** (attempt - 1)), 0.5))

    return None

# ── Groq fallback (OpenAI-compatible API) ──────────────────────────────────

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _invoke_with_groq(prompt: str) -> Optional[dict]:
    """Invoke Groq's OpenAI-compatible API as a final fallback."""
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.3,
    })

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(GROQ_URL, headers=headers, content=body)

            if resp.status_code == 200:
                result = resp.json()
                text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                return _parse_bedrock_json(text)

            logger.warning(
                f"Groq attempt {attempt}/{MAX_RETRIES}: HTTP {resp.status_code} — {resp.text[:200]}"
            )
        except Exception as e:
            logger.warning(f"Groq attempt {attempt}/{MAX_RETRIES} error: {e}")

        if attempt < MAX_RETRIES:
            time.sleep(min(INITIAL_BACKOFF * (2 ** (attempt - 1)), 0.5))

    return None


# ── Public API ─────────────────────────────────────────────────────────────

def invoke_bedrock(prompt: str) -> dict:
    """
    Try models in priority order:
      1. Amazon Nova Pro (Bedrock) — bearer then boto3
      2. Anthropic Prompt Router (Bedrock) — bearer then boto3
      3. Groq (openai/gpt-oss-120b) — direct API
      4. Static fallback
    """
    token = _get_bearer_token()
    # Nova Pro first (proven working), Anthropic Router as upgrade path
    models = [NOVA_MODEL, ANTHROPIC_ROUTER]

    for model_id in models:
        model_short = model_id.split("/")[-1] if "/" in model_id else model_id
        logger.info(f"Trying model: {model_short}")

        # Try bearer token first
        if token:
            result = _invoke_with_bearer(prompt, token, model_id)
            if result is not None:
                logger.info(f"✅ Success via bearer token: {model_short}")
                return result

        # Try boto3 IAM
        result = _invoke_with_boto3(prompt, model_id)
        if result is not None:
            logger.info(f"✅ Success via boto3: {model_short}")
            return result

        logger.warning(f"❌ {model_short} failed — trying next model.")

    # Final fallback: Groq
    logger.info("Trying Groq (openai/gpt-oss-120b) as final fallback...")
    result = _invoke_with_groq(prompt)
    if result is not None:
        logger.info("✅ Success via Groq.")
        return result

    logger.error("All models exhausted — returning static fallback.")
    return FALLBACK_RESPONSE


def _parse_bedrock_json(text: str) -> dict:
    """Parse Claude/Nova response as JSON. Extracts JSON from mixed text."""
    text = text.strip()

    # Strip markdown code fences
    if "```" in text:
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # Try direct parse first
    try:
        parsed = json.loads(text)
        return _validate_keys(parsed)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the text (brace matching)
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:i + 1])
                        return _validate_keys(parsed)
                    except json.JSONDecodeError:
                        break

    logger.warning("Failed to parse Bedrock response as JSON.")
    return FALLBACK_RESPONSE


def _validate_keys(parsed: dict) -> dict:
    """Ensure all required keys exist, filling from fallback if needed."""
    required = ["risk_score", "severity", "confidence", "evidence",
                 "failure_points", "timeline", "blast_radius",
                 "explanation", "patches"]
    for key in required:
        if key not in parsed:
            parsed[key] = FALLBACK_RESPONSE.get(key, "")
    return parsed

