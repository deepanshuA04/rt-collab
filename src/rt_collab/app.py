"""FastAPI application factory."""

from __future__ import annotations

import logging

import sqlalchemy as sa
from fastapi import FastAPI, Response

from rt_collab.config import settings
from rt_collab.db.engine import get_engine
from rt_collab.routes import router as http_router
from rt_collab.ws import router as ws_router

logger = logging.getLogger("rt_collab")


def create_app() -> FastAPI:
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(title="rt-collab gateway", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness probe: process is up and serving requests."""
        return {"status": "ok", "instance_id": settings.instance_id}

    @app.get("/readyz")
    async def readyz(response: Response) -> dict[str, object]:
        """Readiness probe: can this instance actually reach its dependencies.
        Redis will be added here once the client is wired in (milestone 4/5)."""
        checks: dict[str, bool] = {}
        try:
            async with get_engine().connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
            checks["mysql"] = True
        except Exception:
            logger.exception("readyz: mysql check failed")
            checks["mysql"] = False

        ok = all(checks.values())
        response.status_code = 200 if ok else 503
        return {"status": "ok" if ok else "unavailable", "checks": checks}

    app.include_router(http_router)
    app.include_router(ws_router)

    return app


app = create_app()
