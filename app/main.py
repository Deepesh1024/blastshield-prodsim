"""
main.py — FastAPI application factory.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.scan import router as scan_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="BlastShield — Production Failure Simulator",
        description=(
            "Upload Python code or a zip project. "
            "BlastShield simulates concurrency races, latency spikes, chaos failures, "
            "edge-case inputs, and load tests — then uses Amazon Bedrock (Claude 3.5 Sonnet) "
            "to generate a realistic production outage narrative."
        ),
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(scan_router)

    @app.get("/")
    def root():
        return {
            "service": "BlastShield Production Failure Simulator",
            "version": "1.0.0",
            "docs": "/docs",
        }

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
