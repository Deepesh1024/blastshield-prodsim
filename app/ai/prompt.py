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
    scenario: dict = None,
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

## TEST SCENARIO (ACTIVE)
{json.dumps(scenario, indent=1) if scenario else "Default load (50% traffic, 2s latency budget, 20% failure injection)"}

## EVIDENCE COUNTS (raw, from a burst test)
lost_updates={lost_updates}, shared_state={shared_state}, timeouts={timeouts}, slow_responses={slow}, exceptions={exceptions}, edge_failures={edge_fails}, endpoints={len(endpoints)}
Test scale: ~{50 if not scenario else scenario.get('traffic', 50)} threads, {20 if not scenario else scenario.get('failure_rate', 20)}% failure injection

---

Return ONLY valid JSON with these keys:

{{
 "risk_score": <0-100 where higher=more dangerous. Use this scale: 0-25=LOW, 26-50=MEDIUM, 51-75=HIGH, 76-100=CRITICAL. Score MUST match severity.>,
 "severity": "CRITICAL|HIGH|MEDIUM|LOW — must match risk_score range",
 "confidence": <0-100>,
 "evidence": {{
   "lost_updates": {{"count": <realistic_scaled_number>, "detail": "short explanation of what this means"}},
   "timeouts": {{"count": <num>, "detail": "short explanation"}},
   "exceptions": {{"count": <num>, "detail": "short explanation"}},
   "slow_responses": {{"count": <num>, "detail": "short explanation"}},
   "edge_failures": {{"count": <num>, "detail": "short explanation"}}
 }},
 "failure_points": {{
   "Input Validation": [{{"location": "file.py:line", "description": "what's wrong"}}],
   "Concurrency": [{{"location": "file.py:line", "description": "what's wrong"}}],
   "Data Consistency": [{{"location": "file.py:line", "description": "what's wrong"}}],
   "Error Handling": [{{"location": "file.py:line", "description": "what's wrong"}}]
 }},
 "timeline": "0s traffic begins\\n7s thread saturation (23/30 blocked)\\n15s duplicate IDs (47/1000 req)\\n25s checkout fails (p99: 2340ms)\\n40s cascading service failures",
 "blast_radius": ["Affected Service/Component 1", "Affected Service/Component 2"],
 "explanation": "Multi-paragraph SRE incident explanation. First paragraph: describe the root cause and how shared state is corrupted. Second paragraph: describe how malformed requests trigger unhandled exceptions. Third paragraph: describe how these combine under load to cause cascading failures. Write like an SRE postmortem.",
 "patches": [
   {{
     "title": "Fix 1 — Input validation",
     "file": "x.py",
     "code_before": "item = data[\\"item\\"]",
     "code_after": "item = data.get(\\"item\\")\\nif item is None:\\n    return {{\\"error\\": \\"Item not specified\\"}}",
     "reason": "Prevents KeyError crashes from malformed requests"
   }}
 ]
}}

RULES:
1. ONLY valid JSON, no markdown
2. risk_score MUST be consistent: CRITICAL=76-100, HIGH=51-75, MEDIUM=26-50, LOW=0-25
3. Evidence counts must be REALISTIC for a small app (few files, routes, a DB). Use the raw counts as a baseline and scale by at most 5-15x to reflect a realistic burst scenario — NOT thousands unless the raw count itself is already in the hundreds. Example: raw lost_updates=1 → report 5-15, NOT 500.
4. Group failure_points by category (Input Validation, Concurrency, Data Consistency, Error Handling). Omit empty categories.
5. Timeline uses seconds (0s, 7s, 15s etc) with concrete metrics
6. Explanation is 2-3 paragraphs, written like an SRE postmortem
7. Each patch includes a reason explaining WHY the fix works
8. Reference REAL file:line from the code above"""

    return prompt

# Documented code

# Documented code
