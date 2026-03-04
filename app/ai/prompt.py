"""
prompt.py — Build the structured Bedrock prompt for Claude 3.5 Sonnet.
"""
import json
from typing import Any


def build_bedrock_prompt(
    files: list[dict],
    endpoints: list[dict],
    concurrency_results: list[dict],
    latency_results: list[dict],
    chaos_results: list[dict],
    edge_case_results: list[dict],
    curl_results: list[dict],
) -> str:
    """
    Construct a single structured prompt containing all simulation data.
    Claude must return JSON only with the required keys.
    """

    # Truncate file contents to avoid exceeding token limits
    file_summaries = []
    for f in files:
        content = f["content"]
        if len(content) > 3000:
            content = content[:3000] + "\n# ... truncated ..."
        file_summaries.append({"file": f["file"], "content": content})

    prompt = f"""You are an expert Site Reliability Engineer (SRE) analyzing a Python web application for production failure risks.

Below is the complete analysis data from our Production Failure Simulator. Your job is to synthesize all findings into a realistic production failure narrative.

## SOURCE CODE FILES
```json
{json.dumps(file_summaries, indent=2)}
```

## DETECTED API ENDPOINTS
```json
{json.dumps(endpoints, indent=2)}
```

## CONCURRENCY DRILL RESULTS
{json.dumps(concurrency_results, indent=2)}

## LATENCY DRILL RESULTS
{json.dumps(latency_results, indent=2)}

## CHAOS DRILL RESULTS
{json.dumps(chaos_results, indent=2)}

## EDGE CASE TEST RESULTS
{json.dumps(edge_case_results[:20], indent=2)}

## CURL-STYLE LOAD TEST RESULTS
{json.dumps(curl_results, indent=2)}

---

Based on ALL the above data, produce a JSON response with EXACTLY these keys:

{{
  "timeline": "A realistic timeline showing how the system degrades: 1 rps → 100 rps → 1k rps. Describe what breaks at each stage.",
  "propagation": "How a single failure propagates across files and components. Be specific about which functions affect which.",
  "outage_scenario": "A realistic 3-paragraph production outage story. Include timestamps, team reactions, and resolution steps.",
  "blast_radius": "List all affected API endpoints and components. Explain the cascading impact.",
  "explanation": "A plain-English teaching note explaining the top 3 reliability risks found, suitable for a junior developer.",
  "patches": "Provide unified diff patches for the most critical fixes. Use standard diff format with --- and +++ headers."
}}

CRITICAL INSTRUCTIONS:
1. Return ONLY valid JSON — no markdown fences, no explanatory text before or after.
2. Make the outage_scenario feel real and dramatic — like a PagerDuty incident.
3. The patches should be actual unified diffs that would fix the most critical issues found.
4. Reference specific function names, file names, and line-level details from the source code.
5. The timeline should show realistic RPS thresholds where each failure kicks in.
"""

    return prompt
