"""Store lookup must self-heal when brand_logo_url column is missing."""
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.store_service import store_service
from app.infrastructure.database.models import StoreModel


@pytest.mark.asyncio
async def test_get_store_heals_missing_brand_logo_column(tmp_path: Path, monkeypatch):
    db = tmp_path / "drift.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db.as_posix()}")
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        # Minimal legacy stores table WITHOUT brand_logo_url (and without other new cols).
        # Use full create from metadata first then drop column — SQLite can't drop easily,
        # so create legacy shape manually and skip create_all.
        await conn.execute(
            text(
                """
                CREATE TABLE stores (
                  id VARCHAR(64) PRIMARY KEY,
                  mall_id VARCHAR(64),
                  store_name VARCHAR(128),
                  industry VARCHAR(32) DEFAULT 'beauty',
                  as_type VARCHAR(64) DEFAULT 'refund_and_warranty',
                  theme_color VARCHAR(16) DEFAULT '#2E7D32',
                  policy_config_json TEXT DEFAULT '{}',
                  welcome_message TEXT DEFAULT '',
                  plan_type VARCHAR(32) DEFAULT 'free_trial',
                  trial_days INTEGER,
                  expires_at DATETIME,
                  is_active BOOLEAN DEFAULT 1,
                  webhook_url VARCHAR(512),
                  allowed_domains VARCHAR(512),
                  daily_quota_limit INTEGER DEFAULT 300,
                  daily_quota_used INTEGER DEFAULT 0,
                  quota_reset_date VARCHAR(16),
                  bot_icon_style VARCHAR(64) DEFAULT 'flaticon_cute_robot',
                  launcher_shape VARCHAR(32) DEFAULT 'cosbot_badge',
                  bot_label VARCHAR(32) DEFAULT 'bot',
                  bot_name VARCHAR(64) DEFAULT 'bot',
                  brand_badge VARCHAR(32),
                  header_title VARCHAR(64) DEFAULT 'center',
                  chat_template VARCHAR(32) DEFAULT 'cosraw_grid',
                  quick_buttons_json TEXT DEFAULT '[]',
                  contact_email VARCHAR(128) DEFAULT 'a@b.c',
                  business_hours VARCHAR(64) DEFAULT '24h',
                  input_placeholder VARCHAR(128) DEFAULT 'q',
                  bot_avatar_url TEXT,
                  created_at DATETIME,
                  updated_at DATETIME
                )
                """
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE messages (id VARCHAR(64) PRIMARY KEY, detected_language VARCHAR(8))"
            )
        )
        await conn.execute(text("CREATE TABLE sessions (id VARCHAR(64) PRIMARY KEY)"))

    # Point lightweight migrations at this engine
    import app.infrastructure.database.session as sess_mod

    monkeypatch.setattr(sess_mod, "engine", engine)

    async with Session() as session:
        # Direct ORM select must fail before heal
        with pytest.raises(Exception):
            await session.execute(
                text("SELECT brand_logo_url FROM stores LIMIT 1")
            )
            await session.rollback()

    async with Session() as session:
        # get_store should migrate then return None (no row)
        store = await store_service.get_store_by_mall_id(session, "missing_mall")
        assert store is None

    async with engine.connect() as conn:
        cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(stores)"))).fetchall()]
        assert "brand_logo_url" in cols

    await engine.dispose()
