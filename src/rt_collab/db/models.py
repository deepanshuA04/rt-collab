"""3NF schema for document metadata, the append-only update log, and snapshots.

Presence is intentionally NOT modeled here — it lives entirely in Redis TTL keys
(see rt_collab.presence, added in milestone 5). `sessions` below is a durable
audit record of past WebSocket sessions (when a client connected/disconnected to
which document via which gateway instance); it is written on connect/disconnect,
never polled for "is this client online right now."
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from rt_collab.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled")
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    updates: Mapped[list[DocumentUpdate]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    snapshots: Mapped[list[Snapshot]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )
    sessions: Mapped[list[Session]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class DocumentUpdate(Base):
    """One row per Yjs update received from a client. Append-only: rows are never
    edited, only inserted and later pruned in bulk during compaction (see Snapshot).
    """

    __tablename__ = "document_updates"
    __table_args__ = (Index("ix_document_updates_document_id_id", "document_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    update_data: Mapped[bytes] = mapped_column(LargeBinary(length=2**24 - 1), nullable=False)
    origin_instance_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="updates")


class Snapshot(Base):
    """A compacted Y.encodeStateAsUpdate() snapshot of a document as of a point in
    the update log.

    `up_to_update_id` records the highest document_updates.id folded into `state`
    at compaction time. It is deliberately NOT a foreign key: compaction deletes
    document_updates rows with id <= up_to_update_id in the same transaction that
    inserts this row, so by design the referenced row will no longer exist. It is a
    historical watermark, not a live reference.
    """

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[bytes] = mapped_column(LargeBinary(length=2**24 - 1), nullable=False)
    up_to_update_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="snapshots")


class Session(Base):
    """Durable record of a WebSocket connection session. Written at connect and
    updated at disconnect; this is history, not live presence (that's Redis-only).
    """

    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_document_id", "document_id"),
        Index("ix_sessions_client_id", "client_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    client_id: Mapped[str] = mapped_column(String(128), nullable=False)
    gateway_instance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    document: Mapped[Document] = relationship(back_populates="sessions")
