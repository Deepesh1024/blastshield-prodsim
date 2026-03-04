"""
groq_analyzer.py — AI error analysis using Groq API on EC2.
Analyzes runtime logs and returns root cause + fix suggestions.
"""
import json
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

FALLBACK_ANALYSIS = {
    "probable_root_cause": "Unable to determine — AI analysis unavailable.",
    "fix_suggestion": "Review the runtime logs and error messages above.",
    "severity": "unknown",
}


def analyze_with_groq(logs: str, errors: list) -> dict:
    """
    Send runtime logs + errors to Groq for AI analysis.
    Returns structured analysis or fallback.
    """
    if not GROQ_API_KEY:
        logger.warning("Groq API key not set — skipping AI analysis")
        return FALLBACK_ANALYSIS

    prompt = f"""You are a senior SRE analyzing a Python application failure.

## Runtime Errors
{json.dumps(errors, indent=2) if errors else "No explicit errors."}

## Execution Logs
{logs[:3000] if logs else "No logs captured."}

## Task
Analyze the failure and respond with ONLY this JSON:
{{
  "probable_root_cause": "one-line root cause",
  "fix_suggestion": "specific code fix or configuration change",
  "severity": "critical|high|medium|low"
}}"""

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                content=json.dumps({
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 512,
                    "temperature": 0.2,
                }),
            )

        if resp.status_code == 200:
            text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            try:
                # Try direct parse
                parsed = json.loads(text.strip())
                return parsed
            except json.JSONDecodeError:
                # Try extracting JSON from text
                start = text.find("{")
                end = text.rfind("}") + 1
                if start != -1 and end > start:
                    parsed = json.loads(text[start:end])
                    return parsed
                return FALLBACK_ANALYSIS

        logger.warning(f"Groq returned HTTP {resp.status_code}")
        return FALLBACK_ANALYSIS

    except Exception as e:
        logger.warning(f"Groq analysis failed: {e}")
        return FALLBACK_ANALYSIS
