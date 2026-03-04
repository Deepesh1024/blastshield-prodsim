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
  "timeline": "A data-driven load test timeline. Use REAL numbers: at 1 rps show baseline metrics (latency, error rate). At 100 rps show how many threads failed, which functions broke, concrete p99 latencies (e.g. 1200ms). At 1000 rps show exact failure counts, timeout rates, cascading failures. Use numbers like '23/30 threads saw lost updates' or 'p99 latency spiked to 1847ms'. NO fictional timestamps.",
  "propagation": "How a single failure propagates across files and components. Be specific about which functions affect which. Include concrete numbers like 'db.execute_query timeout causes 78% of create_order calls to fail'.",
  "outage_scenario": "A realistic production incident report. Start with the trigger event and load level. Describe cascade with real numbers: error rates, request counts, latency percentiles. Describe what metrics you'd see on a Grafana dashboard. End with root cause and fix. NO fictional clock times like '09:15 AM'.",
  "blast_radius": "List all affected API endpoints and components with impact severity. Use numbers: '6/6 endpoints affected, /create 92% failure rate, /health degraded to 3s response time'.",
  "explanation": "A plain-English teaching note explaining the top 3 reliability risks found, suitable for a junior developer. Reference specific file:line locations.",
  "patches": "Provide unified diff patches for the most critical fixes. Use standard diff format with --- and +++ headers."
}}

CRITICAL INSTRUCTIONS:
1. Return ONLY valid JSON — no markdown fences, no explanatory text before or after.
2. Use CONCRETE NUMBERS throughout — thread counts, error percentages, latency values, request counts. Make them realistic but based on the actual drill findings above.
3. DO NOT use fictional timestamps like "09:15 AM" or "Monday morning". Describe events by load level and sequence.
4. The patches should be actual unified diffs that would fix the most critical issues found.
5. Reference specific function names, file names, and line-level details from the source code.
"""

    return prompt
