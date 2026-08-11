"""Fixtures shared by tests that need a live MySQL/Redis (docker-compose.yml).

These are collected under the `integration` marker and skipped automatically if the
database isn't reachable, so `uv run pytest` still works on a laptop with nothing
running. CI's `integration` job (see .github/workflows/ci.yml) brings the real stack
up first, so they execute for real there.
"""

import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from rt_collab.config import settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def _mysql_reachable() -> bool:
    try:
        import pymysql

        conn = pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            connect_timeout=2,
        )
        conn.close()
        return True
    except Exception:
        return False


collect_ignore_glob: list[str] = [] if _mysql_reachable() else ["*"]


@pytest.fixture(scope="session", autouse=True)
def _migrated_database() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        check=True,
    )


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(settings.mysql_dsn)
    try:
        yield eng
    finally:
        await eng.dispose()
