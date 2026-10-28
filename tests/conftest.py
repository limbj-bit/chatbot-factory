import os
import pytest
from sqlalchemy import text
from app.infrastructure.database.models import Base
from app.infrastructure.database.session import engine, init_db


@pytest.fixture(autouse=True)
async def clean_database():
    """Ensure clean database tables for every test."""
    await init_db()
    async with engine.begin() as conn:
        # Drop and recreate tables for clean test isolation
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
