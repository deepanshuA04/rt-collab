"""readyz's happy path needs a real MySQL to report status: ok, so it lives here
rather than in the unit suite (see tests/test_health.py for the shape-only check)."""

import pytest
from fastapi.testclient import TestClient

from rt_collab.app import app

pytestmark = pytest.mark.integration


def test_readyz_ok_when_mysql_reachable() -> None:
    with TestClient(app) as client:
        response = client.get("/readyz")
    body = response.json()
    assert response.status_code == 200
    assert body == {"status": "ok", "checks": {"mysql": True}}
