"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from rt_collab.config import settings

logger = logging.getLogger("rt_collab")


def create_app() -> FastAPI:
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(title="rt-collab gateway", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness probe: process is up and serving requests."""
        return {"status": "ok", "instance_id": settings.instance_id}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        """Readiness probe. Will start checking Redis/MySQL connectivity once
        those clients are wired in (milestones 2-4)."""
        return {"status": "ok"}

    return app


app = create_app()
