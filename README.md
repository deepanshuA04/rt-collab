# rt-collab — Real-Time Collaborative Presence & Document Service

A WebSocket gateway for real-time collaborative document editing: authenticated
connections, Redis Pub/Sub fan-out across horizontally scaled instances, CRDT-based
document sync, and a 3NF MySQL schema for durable storage with presence offloaded to
Redis. Third in a series of portfolio projects (after `desk-agent` and `task-engine`);
same working agreement — every number below is measured on stated hardware, including
targets that were missed and why, not copied from a spec.

**Status: milestone 3 of 10 (WebSocket gateway core).** This README will be
filled in with real measurements as each milestone lands; see the checklist below.

## Architecture — where the CRDT merge actually happens

Yjs is a JavaScript library, and the CRDT merge does **not** happen in this Python
service. The design:

- The browser holds a Yjs `Y.Doc` and performs all CRDT merging locally.
- Clients send encoded Yjs updates (opaque binary blobs) to the gateway over
  WebSocket.
- The FastAPI gateway authenticates the connection, relays those bytes to other
  subscribers via Redis Pub/Sub, and persists them to MySQL. **It never parses or
  interprets document content.**
- Redis Pub/Sub fans updates out to clients connected to *other* gateway instances,
  so the deployment can scale horizontally with stateless gateway processes.
- MySQL stores document metadata, an append-only log of updates, and periodic
  snapshots (compacted from the log).

This makes the gateway a relay + durability layer, not a merge engine. That is a
deliberate, defensible boundary, not a limitation to hide.

For automated testing (load harness, compaction losslessness, propagation latency),
this repo uses [`pycrdt`](https://github.com/y-crdt/pycrdt) — a Python binding for the
same Rust `yrs` CRDT engine Yjs itself is built on — to generate real, wire-compatible
`Y.Doc` updates without needing a browser or Node.js fleet. The gateway still never
imports it; only the test/load-harness code plays the role of a Yjs client.

## WebSocket gateway: auth and backpressure

- **Auth on the handshake, not after.** `POST /auth/token` exchanges a `client_id`
  for a signed, timed token (there's no user/password store in this project —
  that endpoint stands in for "already authenticated with a real IdP, exchanging
  for a gateway session token"). `/ws/{document_id}?token=...` verifies it
  *before* accepting the WebSocket upgrade; an invalid or missing token gets the
  handshake refused outright (HTTP 403), never an accepted-then-closed socket.
- **Bounded send queue, disconnect on overflow.** Each connection has a capped
  outbound queue (`RT_WS_SEND_QUEUE_MAXSIZE`, default 32). If a client can't keep
  up and it fills, the gateway disconnects that client rather than dropping the
  message and continuing. A silently dropped update would leave that client
  permanently behind with no signal anything was missed; a disconnect instead
  drives it through reconnect + state-vector resync (milestone 5), which is
  self-healing by construction. A slow client's full queue never blocks delivery
  to anyone else.
- **Same-instance relay for now.** Milestone 3 fans updates out to other clients
  on the same document connected to the *same* gateway process. Redis Pub/Sub
  (milestone 4) extends this across instances without changing this layer.

## Stack

Python 3.12 (FastAPI + WebSockets) · Redis (Pub/Sub + TTL keys) · MySQL 8 · Yjs (CRDT,
client-side) · Docker Compose · [uv](https://docs.astral.sh/uv/)

## Local development

```bash
uv sync --frozen
uv run pytest
uv run ruff check .
uv run rt-collab   # starts the gateway on :8000
```

```bash
docker compose up --build   # redis + mysql + gateway
curl http://localhost:8000/healthz
```

Copy `.env.example` to `.env` to override defaults for local runs.

## Milestones

- [x] 1. Scaffold + CI skeleton (Windows + Linux) + Docker Compose (redis, mysql, gateway)
- [x] 2. Schema + versioned atomic migrations + FK/3NF verification
- [x] 3. WebSocket gateway: handshake auth, connection registry, bounded send queues
- [ ] 4. Redis Pub/Sub fan-out + multi-instance cross-delivery test
- [ ] 5. Presence via TTL keys + heartbeat; client reconnect with backoff + state-vector resync
- [ ] 6. Yjs update relay + persistence (append-only log) + client harness holding a Y.Doc
- [ ] 7. Snapshot/compaction with a losslessness test
- [ ] 8. Baseline measurement run: connection count, aggregate msg/sec, propagation p50/p95/p99
- [ ] 9. DB-read workload measurement: with vs without Redis presence, on a documented profile
- [ ] 10. Broker-restart resilience test + full test pass + measured numbers below

## Measured results

_Not yet available — see milestones 8-10. Numbers will be reported with hardware,
load profile, and any missed targets stated plainly, run on GitHub Actions runners
(this dev machine's Docker Desktop/WSL2 backend is pending setup)._
