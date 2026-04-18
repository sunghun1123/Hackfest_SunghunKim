"""Shared pytest config.

Unit tests (distance, schemas, mocked Gemini) run against placeholder env
vars and no real DB. Integration tests (marked by `db_session` / `client`
fixture usage) expect a live Postgres and pull DATABASE_URL from the real
backend .env. That way running `pytest` without a DB still passes the unit
subset, while a developer with Postgres up gets full coverage.
"""

import os
import sys
import uuid
from pathlib import Path

import pytest_asyncio

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Load the real .env before any `app.*` import resolves settings, so that
# integration tests reach the dev database.
_env_path = BACKEND_DIR / ".env"
if _env_path.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_path)

# Final placeholder fallbacks for pure-unit tests (no .env available).
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("GOOGLE_PLACES_API_KEY", "test")
os.environ.setdefault("GEMINI_API_KEY", "test")


@pytest_asyncio.fixture
async def db_session():
    """Yield an AsyncSession bound to the real dev DB. Each test should
    clean up any rows it creates via the `_test_cleanup` fixture."""
    from app.db import SessionLocal

    async with SessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    """httpx.AsyncClient wired to the FastAPI app via ASGITransport (no
    network, no uvicorn). Triggers the lifespan so PostGIS detection runs."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Fire the lifespan manually so settings.postgis_enabled is set.
        async with app.router.lifespan_context(app):
            yield ac


@pytest_asyncio.fixture
async def test_restaurant(db_session):
    """Create a temporary restaurant in a known GR location. Cleanup deletes
    the row and lets CASCADE clean menu_items/submissions/ratings/reports."""
    from sqlalchemy import text

    gpid = f"test_{uuid.uuid4().hex[:16]}"
    row = (
        await db_session.execute(
            text(
                """
                INSERT INTO restaurants
                    (google_place_id, name, address, lat, lng, category)
                VALUES (:gpid, 'TestResto', '123 Test St', 42.96, -85.66, 'sandwich')
                RETURNING id
                """
            ),
            {"gpid": gpid},
        )
    ).one()
    await db_session.commit()
    restaurant_id = row.id
    try:
        yield restaurant_id
    finally:
        await db_session.execute(
            text("DELETE FROM restaurants WHERE id = :id"), {"id": restaurant_id}
        )
        await db_session.commit()


@pytest_asyncio.fixture
async def test_menu_item(db_session, test_restaurant):
    """A throwaway ai_parsed menu_item inside `test_restaurant`. Cleanup is
    handled by restaurant-level CASCADE."""
    from sqlalchemy import text

    row = (
        await db_session.execute(
            text(
                """
                INSERT INTO menu_items
                    (restaurant_id, name, price_cents, source, verification_status)
                VALUES (:rid, 'Test Item', 700, 'seed', 'ai_parsed')
                RETURNING id
                """
            ),
            {"rid": test_restaurant},
        )
    ).one()
    await db_session.commit()
    yield row.id


@pytest_asyncio.fixture
async def test_device(db_session):
    """A fresh device_id per test. Cleanup removes point_history,
    submissions, confirmations, ratings, reports, then the device itself."""
    from sqlalchemy import text

    device_id = f"test-dev-{uuid.uuid4().hex[:12]}"
    try:
        yield device_id
    finally:
        for stmt in (
            "DELETE FROM point_history WHERE device_id = :d",
            "DELETE FROM submissions WHERE device_id = :d",
            "DELETE FROM confirmations WHERE device_id = :d",
            "DELETE FROM ratings WHERE device_id = :d",
            "DELETE FROM reports WHERE device_id = :d",
            "DELETE FROM devices WHERE device_id = :d",
        ):
            await db_session.execute(text(stmt), {"d": device_id})
        await db_session.commit()
