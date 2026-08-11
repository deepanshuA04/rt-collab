"""Verifies the migrated schema actually has the foreign keys and cascade behavior
the models declare — not just that the ORM models look right in isolation.
"""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


async def test_expected_tables_exist(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT TABLE_NAME FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE()"
            )
        )
        tables = {row.TABLE_NAME for row in result}

    assert {"documents", "document_updates", "snapshots", "sessions"} <= tables


async def test_foreign_keys_reference_documents(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.text(
                "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
                "WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME = 'documents'"
            )
        )
        fks = {(row.TABLE_NAME, row.COLUMN_NAME) for row in result}

    # Every child table carries a single FK back to documents.id — the normalized
    # link, not a copy of document metadata (title, etc.) on the child rows.
    assert fks == {
        ("document_updates", "document_id"),
        ("snapshots", "document_id"),
        ("sessions", "document_id"),
    }


async def test_cascade_delete_removes_children(engine: AsyncEngine) -> None:
    doc_id = str(uuid.uuid4())

    async with engine.begin() as conn:
        await conn.execute(
            sa.text("INSERT INTO documents (id, title) VALUES (:id, 'cascade-test')"),
            {"id": doc_id},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO document_updates (document_id, update_data) VALUES (:id, :data)"
            ),
            {"id": doc_id, "data": b"\x01\x02\x03"},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO snapshots (document_id, state, up_to_update_id) "
                "VALUES (:id, :data, 0)"
            ),
            {"id": doc_id, "data": b"\x01"},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO sessions (id, document_id, client_id, gateway_instance_id) "
                "VALUES (:sid, :id, 'client-1', 'gateway-a')"
            ),
            {"sid": str(uuid.uuid4()), "id": doc_id},
        )

    async with engine.begin() as conn:
        await conn.execute(sa.text("DELETE FROM documents WHERE id = :id"), {"id": doc_id})

    async with engine.connect() as conn:
        for table in ("document_updates", "snapshots", "sessions"):
            count = (
                await conn.execute(
                    sa.text(f"SELECT COUNT(*) FROM {table} WHERE document_id = :id"),
                    {"id": doc_id},
                )
            ).scalar_one()
            assert count == 0, f"{table} rows survived deleting their parent document"
