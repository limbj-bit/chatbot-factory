"""Store lookup must succeed when brand_logo_url column is absent (deferred)."""
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.application.store_service import store_service


@pytest.mark.asyncio
async def test_get_store_works_without_brand_logo_column(tmp_path: Path, monkeypatch):
    db = tmp_path / "no_logo_col.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db.as_posix()}")
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
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
                "INSERT INTO stores (id, mall_id, store_name, created_at, updated_at) "
                "VALUES ('1', 'defer_mall', 'Defer Shop', '2026-01-01', '2026-01-01')"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE messages (id VARCHAR(64) PRIMARY KEY, detected_language VARCHAR(8))"
            )
        )
        await conn.execute(text("CREATE TABLE sessions (id VARCHAR(64) PRIMARY KEY)"))

    import app.infrastructure.database.session as sess_mod

    monkeypatch.setattr(sess_mod, "engine", engine)

    # Force the defer fallback path (migrate intentionally does nothing).
    async def _noop_migrate(_engine=None):
        return None

    monkeypatch.setattr(sess_mod, "apply_lightweight_migrations", _noop_migrate)

    async with Session() as session:
        store = await store_service.get_store_by_mall_id(session, "defer_mall")
        assert store is not None
        assert store.mall_id == "defer_mall"
        assert store.__dict__.get("brand_logo_url") is None
        resp = store_service._to_response(store)
        assert resp.brand_logo_url is None

    await engine.dispose()
