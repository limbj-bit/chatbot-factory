"""Health endpoint honesty + schema-status transaction isolation."""
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.ai.mock import MockAIProvider
from app.infrastructure.ai.router import AIProviderRouter


def test_router_reports_mock_when_no_provider_keys(monkeypatch):
    """A router that fell back to mock must not claim to be live."""
    router = AIProviderRouter(mock_mode=False)
    # Simulate the no-key fallback without depending on the local .env.
    router.mock_mode = False
    router.providers = {"mock": MockAIProvider(provider_name="mock")}

    status = router.get_status()

    assert router.effective_mock_mode is True
    assert status["mock_mode"] is True
    assert status["configured_mock"] is False
    assert status["live_provider_count"] == 0


@pytest.mark.asyncio
async def test_schema_status_reports_columns_and_heals(tmp_path: Path, monkeypatch):
    """On SQLite the probe must return real columns, not null + ok:true."""
    db = tmp_path / "schema_status.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db.as_posix()}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE stores (
                  id VARCHAR(64) PRIMARY KEY,
                  mall_id VARCHAR(64)
                )
                """
            )
        )
        await conn.execute(text("CREATE TABLE messages (id VARCHAR(64) PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE sessions (id VARCHAR(64) PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE store_knowledge (id VARCHAR(64) PRIMARY KEY)"))

    import app.infrastructure.database.session as sess_mod
    from app.main import get_schema_status

    monkeypatch.setattr(sess_mod, "engine", engine)
    monkeypatch.setattr(sess_mod, "async_session_factory", session_factory)

    result = await get_schema_status()

    assert result["ok"] is True
    assert result["stores_columns"] is not None
    assert "brand_logo_url" in result["stores_columns"]
    assert result["migrate_ran"] is True
    assert result["probe_error_after_migrate"] is None

    await engine.dispose()
