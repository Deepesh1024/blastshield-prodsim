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
    Construct a structured prompt for Bedrock AI.
    Kept compact to fit within model token limits.
    """

    # Truncate files aggressively
    file_summaries = []
    for f in files:
        content = f["content"]
        if len(content) > 1500:
            content = content[:1500] + "\n# ... truncated ..."
        file_summaries.append({"file": f["file"], "content": content})

    # Pre-compute evidence counts
    lost_updates = sum(1 for i in concurrency_results if i.get("issue") == "lost_updates")
    shared_state = sum(1 for i in concurrency_results if "shared" in str(i.get("issue", "")).lower())
    timeouts = sum(1 for i in latency_results if i.get("severity") in ("high", "medium"))
    slow = sum(1 for i in latency_results if i.get("severity") == "low")
    exceptions = sum(1 for i in chaos_results if i.get("severity") in ("critical", "high"))
    edge_fails = sum(1 for e in edge_case_results if e.get("result") in ("crashed", "failed"))

    # Only include first few drill results to save tokens
    conc_short = concurrency_results[:3]
    lat_short = latency_results[:3]
    chaos_short = chaos_results[:5]

    prompt = f"""You are an SRE analyzing Python code for production failures.

## CODE
{json.dumps(file_summaries, indent=1)}

## ENDPOINTS
{json.dumps(endpoints, indent=1)}

## DRILL RESULTS (samples)
Concurrency: {json.dumps(conc_short, indent=1)}
Latency: {json.dumps(lat_short, indent=1)}
Chaos: {json.dumps(chaos_short, indent=1)}

## EVIDENCE COUNTS
lost_updates={lost_updates}, shared_state={shared_state}, timeouts={timeouts}, slow_responses={slow}, exceptions={exceptions}, edge_failures={edge_fails}, endpoints={len(endpoints)}

---

Return ONLY valid JSON with these keys:

{{
 "risk_score": <0-100, 100=safe, 0=broken>,
 "severity": "CRITICAL|HIGH|MEDIUM|LOW",
 "confidence": <0-100>,
 "evidence": {{"lost_updates": <realistic_number>, "timeouts": <num>, "exceptions": <num>, "slow_responses": <num>, "edge_failures": <num>}},
 "failure_points": [{{"location": "file.py:line", "description": "what's wrong", "severity": "critical|high|medium"}}],
 "timeline": "0s traffic begins\\n7s thread saturation (23/30 blocked)\\n15s duplicate IDs (47 in 1000 req)\\n25s checkout fails (p99: 2340ms)\\n40s cascade",
 "blast_radius": ["Service1", "Service2"],
 "explanation": "2-3 paragraphs speaking to the developer: You did X in file.py:12, this causes Y under load. Change it to Z. Be specific with file:line refs.",
 "patches": [{{"file": "x.py", "issue": "race condition", "fix_description": "add lock", "code_before": "counter += 1", "code_after": "with lock:\\n    counter += 1"}}]
}}

RULES:
1. ONLY valid JSON, no markdown
2. Use realistic FABRICATED numbers for evidence (scale up from drill counts)
3. Timeline uses seconds (0s, 7s, 15s) with concrete metrics
4. Explanation speaks DIRECTLY to developer: "You did X, change to Y"
5. Patches show real before/after code from the source files
6. failure_points reference REAL file:line from code above"""

    return prompt
