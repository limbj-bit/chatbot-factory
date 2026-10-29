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


# Columns added after initial create_all(). Each statement MUST run in its own
# transaction: on Postgres, one failed ALTER aborts the whole transaction and
# later adds (e.g. brand_logo_url) never apply if earlier columns already exist.
LIGHTWEIGHT_ALTERS = (
    "ALTER TABLE messages ADD COLUMN detected_language VARCHAR(8)",
    "ALTER TABLE messages ADD COLUMN translation_ko TEXT",
    "ALTER TABLE sessions ADD COLUMN mall_id VARCHAR(64) DEFAULT 'demo_mall'",
    "ALTER TABLE stores ADD COLUMN brand_logo_url TEXT",
)


async def apply_lightweight_migrations(target_engine=None) -> None:
    """Idempotent ALTER TABLE adds. One transaction per statement; log skips."""
    import logging
    from sqlalchemy import text as _text

    eng = target_engine if target_engine is not None else engine
    log = logging.getLogger(__name__)
    for stmt in LIGHTWEIGHT_ALTERS:
        try:
            async with eng.begin() as conn:
                await conn.execute(_text(stmt))
            log.info("schema migrate applied: %s", stmt)
        except Exception as e:
            # Expected when column already exists; still log so silent drift is visible.
            log.info("schema migrate skip: %s (%s: %s)", stmt, type(e).__name__, e)


async def init_db() -> None:
    """Create tables if they don't exist, then apply lightweight column adds."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await apply_lightweight_migrations(engine)


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
