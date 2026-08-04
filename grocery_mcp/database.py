"""Small async PostgreSQL persistence layer with local-memory fallback."""
from __future__ import annotations

import json
import os
from typing import Any

import asyncpg

_pool: asyncpg.Pool | None = None
_schema_ready = False


def database_url() -> str | None:
    value = os.environ.get("DATABASE_URL", "").strip()
    return value or None


async def pool() -> asyncpg.Pool | None:
    global _pool
    if not database_url():
        return None
    if _pool is None:
        _pool = await asyncpg.create_pool(database_url(), min_size=1, max_size=5)
    await ensure_schema()
    return _pool


async def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready or _pool is None:
        return
    async with _pool.acquire() as connection:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS oauth_state (
                kind TEXT NOT NULL,
                key TEXT NOT NULL,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (kind, key)
            );
            CREATE TABLE IF NOT EXISTS grocery_handoffs (
                id UUID PRIMARY KEY,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS grocery_templates (
                id UUID PRIMARY KEY,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
    _schema_ready = True


async def put_state(kind: str, key: str, payload: dict[str, Any]) -> None:
    connection_pool = await pool()
    if connection_pool is None:
        return
    await connection_pool.execute(
        """
        INSERT INTO oauth_state (kind, key, payload)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (kind, key)
        DO UPDATE SET payload = EXCLUDED.payload, updated_at = NOW()
        """,
        kind,
        key,
        json.dumps(payload),
    )


async def get_state(kind: str, key: str) -> dict[str, Any] | None:
    connection_pool = await pool()
    if connection_pool is None:
        return None
    value = await connection_pool.fetchval(
        "SELECT payload FROM oauth_state WHERE kind = $1 AND key = $2",
        kind,
        key,
    )
    return dict(value) if value is not None else None


async def delete_state(kind: str, key: str) -> None:
    connection_pool = await pool()
    if connection_pool is not None:
        await connection_pool.execute(
            "DELETE FROM oauth_state WHERE kind = $1 AND key = $2",
            kind,
            key,
        )


async def save_handoff(handoff_id: str, payload: dict[str, Any]) -> None:
    connection_pool = await pool()
    if connection_pool is None:
        return
    await connection_pool.execute(
        """
        INSERT INTO grocery_handoffs (id, payload)
        VALUES ($1::uuid, $2::jsonb)
        ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload
        """,
        handoff_id,
        json.dumps(payload),
    )


async def load_handoff(handoff_id: str) -> dict[str, Any] | None:
    connection_pool = await pool()
    if connection_pool is None:
        return None
    value = await connection_pool.fetchval(
        "SELECT payload FROM grocery_handoffs WHERE id = $1::uuid",
        handoff_id,
    )
    return dict(value) if value is not None else None


async def save_template(template_id: str, payload: dict[str, Any]) -> None:
    connection_pool = await pool()
    if connection_pool is None:
        return
    await connection_pool.execute(
        """
        INSERT INTO grocery_templates (id, payload)
        VALUES ($1::uuid, $2::jsonb)
        ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload
        """,
        template_id,
        json.dumps(payload),
    )


async def load_template(template_id: str) -> dict[str, Any] | None:
    connection_pool = await pool()
    if connection_pool is None:
        return None
    value = await connection_pool.fetchval(
        "SELECT payload FROM grocery_templates WHERE id = $1::uuid",
        template_id,
    )
    return dict(value) if value is not None else None


async def list_templates() -> list[dict[str, Any]]:
    connection_pool = await pool()
    if connection_pool is None:
        return []
    values = await connection_pool.fetch(
        "SELECT payload FROM grocery_templates ORDER BY created_at DESC LIMIT 100"
    )
    return [dict(row["payload"]) for row in values]


async def close_pool() -> None:
    global _pool, _schema_ready
    if _pool is not None:
        await _pool.close()
    _pool = None
    _schema_ready = False
