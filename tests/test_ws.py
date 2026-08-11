"""WebSocket gateway tests.

Two styles here, deliberately:
- Tests that exercise the real ASGI stack via TestClient (auth rejection, basic
  relay) — good for proving the handshake and routing wiring actually works.
- Tests that drive rt_collab.ws.registry directly with fake WebSocket doubles
  (queue-overflow, cross-document isolation) — TestClient's in-memory transport
  has no real backpressure, so a "producer floods, consumer never reads" scenario
  can't reliably reproduce overflow through it; testing the registry/queue logic
  directly is both deterministic and closer to what's actually being verified.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from rt_collab.app import app
from rt_collab.config import settings
from rt_collab.ws.auth import issue_token
from rt_collab.ws.registry import Connection, registry
from rt_collab.ws.router import WS_POLICY_VIOLATION, WS_TRY_AGAIN_LATER, _drop_slow_peer


class _RecordingWebSocket:
    """Accepts sends instantly and records them — a well-behaved fast client."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed_with: int | None = None

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


class _StuckWebSocket:
    """Simulates a client whose connection stopped draining: the first send
    blocks forever, the way a real full OS socket send-buffer would. This makes
    the connection's own bounded queue the only thing capping memory growth."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed_with: int | None = None

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)
        await asyncio.Event().wait()

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# --- handshake auth -----------------------------------------------------


def test_missing_token_rejected_before_upgrade(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/doc-1"):
            pass
    assert exc_info.value.code == WS_POLICY_VIOLATION


def test_invalid_token_rejected_before_upgrade(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/doc-1?token=not-a-real-token"):
            pass
    assert exc_info.value.code == WS_POLICY_VIOLATION


def test_valid_token_connects(client: TestClient) -> None:
    token = issue_token("alice")
    with client.websocket_connect(f"/ws/doc-1?token={token}"):
        pass  # accepted, no exception


# --- relay, end to end ----------------------------------------------------


def test_relays_between_two_clients_on_same_document(client: TestClient) -> None:
    token_a = issue_token("alice")
    token_b = issue_token("bob")
    with (
        client.websocket_connect(f"/ws/doc-1?token={token_a}") as ws_a,
        client.websocket_connect(f"/ws/doc-1?token={token_b}") as ws_b,
    ):
        ws_a.send_bytes(b"hello from alice")
        assert ws_b.receive_bytes() == b"hello from alice"


def test_sender_does_not_receive_its_own_broadcast(client: TestClient) -> None:
    token_a = issue_token("alice")
    token_b = issue_token("bob")
    with (
        client.websocket_connect(f"/ws/doc-1?token={token_a}") as ws_a,
        client.websocket_connect(f"/ws/doc-1?token={token_b}") as ws_b,
    ):
        ws_a.send_bytes(b"update-1")
        ws_b.receive_bytes()

        ws_b.send_bytes(b"ping-only-for-a")
        # If alice's own message had echoed back to her, this would return
        # "update-1" (or hang, or arrive out of order) instead of bob's reply.
        assert ws_a.receive_bytes() == b"ping-only-for-a"


# --- registry / queue behavior, driven directly ---------------------------


async def test_broadcast_local_does_not_cross_documents() -> None:
    conn1 = Connection(websocket=_RecordingWebSocket(), client_id="a", document_id="doc-1")
    conn2 = Connection(websocket=_RecordingWebSocket(), client_id="b", document_id="doc-2")
    await registry.add(conn1)
    await registry.add(conn2)
    try:
        await registry.broadcast_local("doc-1", b"only for doc-1")
        await asyncio.sleep(0.01)
        assert conn1.websocket.sent == [b"only for doc-1"]
        assert conn2.websocket.sent == []
    finally:
        await registry.remove(conn1)
        await registry.remove(conn2)


async def test_connection_backlog_overflows_past_configured_size() -> None:
    conn = Connection(websocket=_StuckWebSocket(), client_id="bob", document_id="doc-1")
    await registry.add(conn)
    try:
        assert conn.enqueue(b"first") is True
        await asyncio.sleep(0.01)  # let the sender task pick "first" up and get stuck on it

        for i in range(settings.ws_send_queue_maxsize):
            assert conn.enqueue(f"msg-{i}".encode()) is True
        assert conn.enqueue(b"one-too-many") is False
    finally:
        await registry.remove(conn)


async def test_drop_slow_peer_closes_with_try_again_later_and_deregisters() -> None:
    ws = _StuckWebSocket()
    conn = Connection(websocket=ws, client_id="bob", document_id="doc-1")
    await registry.add(conn)

    await _drop_slow_peer(conn)

    assert ws.closed_with == WS_TRY_AGAIN_LATER
    assert not registry.has_local_subscribers("doc-1")
