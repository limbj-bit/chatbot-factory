"""brand_logo_url must still be added when earlier ALTERs already exist."""
import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.infrastructure.database.session import apply_lightweight_migrations


@pytest.mark.asyncio
async def test_brand_logo_column_added_when_earlier_alters_already_exist(tmp_path: Path):
    db = tmp_path / "legacy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db.as_posix()}")

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE stores ("
                "id VARCHAR(64) PRIMARY KEY, "
                "mall_id VARCHAR(64), "
                "store_name VARCHAR(128))"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE messages ("
                "id VARCHAR(64) PRIMARY KEY, "
                "detected_language VARCHAR(8))"
            )
        )
        await conn.execute(text("CREATE TABLE sessions (id VARCHAR(64) PRIMARY KEY)"))

    await apply_lightweight_migrations(engine)

    async with engine.connect() as conn:
        cols = (await conn.execute(text("PRAGMA table_info(stores)"))).fetchall()
        names = [c[1] for c in cols]
        assert "brand_logo_url" in names
        # SELECT shape the ORM expects must not blow up
        await conn.execute(text("SELECT brand_logo_url FROM stores"))

    await engine.dispose()
