"""
handler.py — AWS Lambda entry point via Mangum.
Works with API Gateway HTTP API by stripping the stage/function prefix.
"""
from mangum import Mangum
from app.main import app

# Create the Mangum handler
# api_gateway_base_path strips the prefix so FastAPI sees clean routes
_mangum = Mangum(app, lifespan="off")


def handler(event, context):
    """Lambda handler with API Gateway path prefix stripping."""
    raw_path = event.get("rawPath", "/")

    # Strip API Gateway prefix: /default/blastshield-agent-api/scan -> /scan
    # Handle both with and without trailing function name
    segments = raw_path.split("/")
    # segments: ['', 'default', 'blastshield-agent-api', 'scan']
    # We want to keep only the actual route part
    if len(segments) >= 3:
        # Find the function name segment and strip everything up to it
        for i, seg in enumerate(segments):
            if seg == "blastshield-agent-api":
                clean_path = "/" + "/".join(segments[i + 1:]) if i + 1 < len(segments) else "/"
                # Remove trailing slash if it's not the root
                if clean_path != "/" and clean_path.endswith("/"):
                    clean_path = clean_path.rstrip("/")
                event["rawPath"] = clean_path
                # Also fix requestContext
                rc = event.get("requestContext", {})
                http_info = rc.get("http", {})
                if "path" in http_info:
                    http_info["path"] = clean_path
                break

    return _mangum(event, context)

# Documented code
