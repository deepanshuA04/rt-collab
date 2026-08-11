"""The WebSocket endpoint itself: handshake auth, registry lifecycle, and
(for now) same-instance relay of opaque Yjs update bytes between clients on a
document. Redis fan-out layers on top of `broadcast_local` in milestone 4.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from rt_collab.ws.auth import verify_token
from rt_collab.ws.registry import Connection, registry

logger = logging.getLogger("rt_collab.ws")

# Standard WebSocket close codes (RFC 6455 / IANA registry). Starlette only
# exposes a handful as named constants, so the ones we need are spelled out here.
WS_POLICY_VIOLATION = 1008  # auth token missing/invalid/expired
WS_TRY_AGAIN_LATER = 1013  # slow-consumer disconnect; client should reconnect (milestone 5)

router = APIRouter()


@router.websocket("/ws/{document_id}")
async def document_socket(websocket: WebSocket, document_id: str) -> None:
    token = websocket.query_params.get("token")
    client_id = verify_token(token) if token else None
    if client_id is None:
        # close() before accept() makes the ASGI server refuse the handshake
        # outright instead of opening the connection and then closing it.
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    await websocket.accept()
    connection = Connection(websocket=websocket, client_id=client_id, document_id=document_id)
    await registry.add(connection)

    try:
        while True:
            data = await websocket.receive_bytes()
            overflowed = await registry.broadcast_local(document_id, data, exclude=connection)
            for peer in overflowed:
                await _drop_slow_peer(peer)
    except WebSocketDisconnect:
        pass
    finally:
        await registry.remove(connection)


async def _drop_slow_peer(peer: Connection) -> None:
    logger.warning(
        "ws send-queue overflow, disconnecting slow client document=%s client=%s",
        peer.document_id,
        peer.client_id,
    )
    await registry.remove(peer)
    try:
        await peer.websocket.close(code=WS_TRY_AGAIN_LATER)
    except Exception:
        pass  # already gone
