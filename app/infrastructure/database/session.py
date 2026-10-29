import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings
from app.infrastructure.database.models import Base

# Ensure parent directory for sqlite exists
if settings.DATABASE_URL.startswith("sqlite"):
    db_file_path = settings.DATABASE_URL.split("///")[-1]
    db_dir = os.path.dirname(db_file_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

# SQLAlchemy's default Postgres dialect expects psycopg (psycopg3), which is
# not installed. Normalise the URL so asyncpg is always used for Postgres.
# asyncpg does not accept libpq-style params (sslmode, channel_binding, etc.)
# as keyword arguments, so strip them from the URL and translate sslmode into
# connect_args={"ssl": ...}.
import re as _re

_db_url = settings.DATABASE_URL
_connect_args = {}
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql+asyncpg://", 1)

# Strip query params that asyncpg cannot handle (sslmode, channel_binding, etc.)
if "?" in _db_url:
    _base, _query = _db_url.split("?", 1)
    _params = {}
    for _pair in _query.split("&"):
        if "=" in _pair:
            _k, _v = _pair.split("=", 1)
            if _k.lower() == "sslmode":
                # asyncpg uses ssl= instead of sslmode=
                if _v.lower() in ("require", "verify-ca", "verify-full"):
                    _connect_args["ssl"] = "require"
            elif _k.lower() == "channel_binding":
                pass  # asyncpg does not support this; ignore
            else:
                _params[_k] = _v
    if _params:
        _db_url = _base + "?" + "&".join(f"{k}={v}" for k, v in _params.items())
    else:
        _db_url = _base

engine = create_async_engine(
    _db_url,
    echo=False,
    future=True,
    connect_args=_connect_args,
)

async_session_factory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def init_db() -> None:
    """Create tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Lightweight, idempotent migrations for columns added after initial deploy.
    # create_all() does not ALTER existing tables (Render Postgres / local SQLite).
    from sqlalchemy import text as _text

    async with engine.begin() as conn:
        for stmt in (
            "ALTER TABLE messages ADD COLUMN detected_language VARCHAR(8)",
            "ALTER TABLE messages ADD COLUMN translation_ko TEXT",
            "ALTER TABLE sessions ADD COLUMN mall_id VARCHAR(64) DEFAULT 'demo_mall'",
        ):
            try:
                await conn.execute(_text(stmt))
            except Exception:
                pass  # column already exists


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
