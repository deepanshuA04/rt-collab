from fastapi.testclient import TestClient

from rt_collab.app import app


def test_healthz() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "instance_id" in body


def test_readyz_reports_dependency_checks() -> None:
    """No live MySQL in the unit-test environment, so this only checks the
    endpoint's shape and that a failed dependency check yields 503, not the
    happy path — that's covered against a real database by the integration
    suite (tests/integration)."""
    with TestClient(app) as client:
        response = client.get("/readyz")
    body = response.json()
    assert response.status_code in (200, 503)
    assert response.status_code == (200 if body["status"] == "ok" else 503)
    assert "mysql" in body["checks"]
