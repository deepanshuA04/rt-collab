"""In-process connection registry: which clients are attached to which document on
*this* gateway instance, and their bounded outbound send queues.

This is deliberately local-only. Milestone 4 adds Redis Pub/Sub on top so an edit
made against one instance reaches clients attached to a different instance; this
registry is what that layer fans out into once a message reaches the right process.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

from rt_collab.config import settings

logger = logging.getLogger("rt_collab.ws")


@dataclass(eq=False)
class Connection:
    websocket: WebSocket
    client_id: str
    document_id: str
    queue: asyncio.Queue[bytes] = field(init=False, repr=False)
    _sender_task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.queue = asyncio.Queue(maxsize=settings.ws_send_queue_maxsize)

    def start_sender(self) -> None:
        self._sender_task = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        try:
            while True:
                data = await self.queue.get()
                await self.websocket.send_bytes(data)
        except (asyncio.CancelledError, Exception):
            # Either we cancelled this task ourselves during cleanup, or the send
            # failed because the socket is already going away. Either way the
            # receive loop in rt_collab.ws.router owns tearing down the registry
            # entry — this task's only job is to stop looping quietly.
            return

    def enqueue(self, data: bytes) -> bool:
        """Attempt to hand `data` off for delivery. Returns False if the outbound
        backlog is full, meaning this client is too slow to keep up in real time.

        We do not drop the message and keep going: a silently dropped Yjs update
        would leave this client permanently missing a change with no signal that
        anything is wrong. Instead the caller disconnects the client, which drives
        it through reconnect + state-vector resync (milestone 5) — a path that is
        self-healing by construction, unlike a silent gap.
        """
        try:
            self.queue.put_nowait(data)
            return True
        except asyncio.QueueFull:
            return False

    def stop(self) -> None:
        if self._sender_task is not None:
            self._sender_task.cancel()


class ConnectionRegistry:
    def __init__(self) -> None:
        self._by_document: dict[str, set[Connection]] = {}
        self._lock = asyncio.Lock()

    async def add(self, connection: Connection) -> None:
        async with self._lock:
            self._by_document.setdefault(connection.document_id, set()).add(connection)
        connection.start_sender()
        logger.info(
            "ws connect document=%s client=%s", connection.document_id, connection.client_id
        )

    async def remove(self, connection: Connection) -> None:
        connection.stop()
        async with self._lock:
            peers = self._by_document.get(connection.document_id)
            if peers is None or connection not in peers:
                return
            peers.discard(connection)
            if not peers:
                del self._by_document[connection.document_id]
        logger.info(
            "ws disconnect document=%s client=%s", connection.document_id, connection.client_id
        )

    async def broadcast_local(
        self, document_id: str, data: bytes, *, exclude: Connection | None = None
    ) -> list[Connection]:
        """Fan `data` out to same-instance subscribers of `document_id`. Returns
        the connections whose backlog overflowed, for the caller to disconnect."""
        async with self._lock:
            peers = list(self._by_document.get(document_id, ()))
        overflowed = [p for p in peers if p is not exclude and not p.enqueue(data)]
        return overflowed

    def local_subscriber_count(self, document_id: str) -> int:
        return len(self._by_document.get(document_id, ()))

    def has_local_subscribers(self, document_id: str) -> bool:
        return document_id in self._by_document


registry = ConnectionRegistry()
