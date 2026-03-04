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
  "timeline": "A realistic load test timeline with REAL timestamps (e.g. 09:00, 09:05, 09:12). At each timestamp, describe what load level was applied and what happened. Generate realistic but fabricated test counts (e.g. '847/1000 requests succeeded'), latency percentiles (e.g. 'p99 jumped from 45ms to 1847ms'), thread failure rates, and error counts. Base the TYPES of failures on the drill results above, but invent concrete numbers.",
  "propagation": "How a single failure propagates across files and components. Be specific about which functions affect which. Include fabricated but realistic numbers like 'db.execute_query timeout causes 78% of create_order calls to fail within 30 seconds'.",
  "outage_scenario": "A realistic production incident report with REAL timestamps. Use a realistic incident timeline (e.g. '09:15 - alert fires', '09:18 - SRE team paged', '09:25 - root cause identified'). Include fabricated but realistic metrics: error rates, request counts, latency percentiles, thread counts. Describe Grafana dashboard observations. End with root cause and fix.",
  "blast_radius": "List all affected API endpoints and components with impact severity. Use fabricated numbers: '6/6 endpoints affected, /create 92% failure rate at peak, /health p99 degraded to 3200ms'.",
  "explanation": "A plain-English teaching note explaining the top 3 reliability risks found, suitable for a junior developer. Reference specific file:line locations.",
  "patches": "Provide unified diff patches for the most critical fixes. Use standard diff format with --- and +++ headers."
}}

CRITICAL INSTRUCTIONS:
1. Return ONLY valid JSON — no markdown fences, no explanatory text before or after.
2. Use REAL timestamps for the incident timeline and load test progression.
3. Generate REALISTIC but FABRICATED numbers for test counts, latencies, error rates, and thread failures. Base the failure TYPES on the actual drill findings, but invent convincing metrics.
4. The patches should be actual unified diffs that would fix the most critical issues found.
5. Reference specific function names, file names, and line-level details from the source code.
"""

    return prompt
