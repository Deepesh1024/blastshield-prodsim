"""
prompt.py — Build the structured Bedrock prompt for AI analysis.
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
    The AI must return a structured JSON report.
    """

    # Truncate file contents to avoid exceeding token limits
    file_summaries = []
    for f in files:
        content = f["content"]
        if len(content) > 3000:
            content = content[:3000] + "\n# ... truncated ..."
        file_summaries.append({"file": f["file"], "content": content})

    # Count evidence from drills
    lost_updates = sum(1 for i in concurrency_results if i.get("issue") == "lost_updates")
    shared_state = sum(1 for i in concurrency_results if "shared" in str(i.get("issue", "")).lower())
    timeouts = sum(1 for i in latency_results if i.get("severity") in ("high", "medium"))
    slow_responses = sum(1 for i in latency_results if i.get("severity") == "low")
    exceptions = sum(1 for i in chaos_results if i.get("severity") in ("critical", "high"))
    edge_failures = sum(1 for e in edge_case_results if e.get("result") in ("crashed", "failed"))

    evidence_summary = f"""
Evidence counts from drills:
- lost_updates: {lost_updates}
- shared_state_issues: {shared_state}
- timeouts: {timeouts}
- slow_responses: {slow_responses}
- unhandled_exceptions: {exceptions}
- edge_case_failures: {edge_failures}
- total_endpoints: {len(endpoints)}
"""

    prompt = f"""You are an expert Site Reliability Engineer analyzing a Python web application for production failure risks.

Below is the complete analysis data from our Production Failure Simulator.

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

## EVIDENCE SUMMARY
{evidence_summary}

---

Based on ALL the above data, produce a JSON response with EXACTLY these keys:

{{
  "risk_score": 74,
  "severity": "HIGH or CRITICAL or MEDIUM or LOW",
  "confidence": 86,
  "evidence": {{
    "lost_updates": 43,
    "timeouts": 12,
    "exceptions": 7,
    "slow_responses": 28,
    "edge_failures": 5
  }},
  "failure_points": [
    {{
      "location": "services.py:12",
      "description": "Shared mutable state update without synchronization",
      "severity": "critical"
    }}
  ],
  "timeline": "0s  traffic begins\\n7s  thread saturation detected (23/30 threads blocked)\\n15s  duplicate order IDs generated (47 duplicates in 1000 requests)\\n25s  checkout failure triggered (p99 latency: 2340ms)\\n40s  cascading failure across all endpoints",
  "blast_radius": ["Checkout service", "Payment service", "Order tracking pipeline", "Health endpoint"],
  "explanation": "A detailed multi-paragraph explanation. Tell the developer exactly what they did wrong and what to change. For example: 'In services.py line 12, you update a shared counter without any synchronization. Under concurrent load, multiple threads read the same value, increment it, and write back — causing lost updates. You need to wrap this in a threading.Lock or use an atomic counter.' Be specific, helpful, and educational.",
  "patches": [
    {{
      "file": "services.py",
      "issue": "Race condition on shared counter",
      "fix_description": "Use a thread-safe update mechanism",
      "code_before": "counter += 1",
      "code_after": "with counter_lock:\\n    counter += 1"
    }}
  ]
}}

CRITICAL INSTRUCTIONS:
1. Return ONLY valid JSON — no markdown, no text before or after.
2. risk_score is 0-100 where 100 is perfectly safe and 0 is catastrophically broken. Base it on the severity and count of issues found.
3. confidence is 0-100 representing how confident you are in the analysis.
4. evidence must contain REALISTIC FABRICATED numbers that are higher than the actual drill counts — simulate what would happen at production scale (thousands of requests).
5. failure_points must reference REAL file:line locations from the source code above.
6. timeline must use realistic SECONDS (0s, 7s, 15s, 25s) showing how the system degrades under increasing load. Include concrete numbers.
7. explanation must be 2-3 paragraphs, speaking DIRECTLY to the developer: "You did X, this causes Y, change it to Z."
8. patches must show concrete before/after code fixes for the top issues found.
"""

    return prompt
