from fastapi.testclient import TestClient

from rt_collab.app import app
from rt_collab.ws.auth import verify_token


def test_create_token_issues_a_token_that_verifies() -> None:
    with TestClient(app) as client:
        response = client.post("/auth/token", json={"client_id": "alice"})
    assert response.status_code == 200
    token = response.json()["token"]
    assert verify_token(token) == "alice"


def test_create_token_rejects_empty_client_id() -> None:
    with TestClient(app) as client:
        response = client.post("/auth/token", json={"client_id": ""})
    assert response.status_code == 422
