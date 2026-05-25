"""
Test configuration and fixtures.

Integration tests use a real PostgreSQL database (via Docker Compose).
The DB URL is read from TEST_DATABASE_URL env var; falls back to a local default.

Why real DB and not mocks?
  - We've been burned before by mock/prod divergence (SELECT FOR UPDATE
    semantics, JSONB indexing, constraint violations). Real DB catches this.
  - The adjudicator domain tests use pure objects — no DB needed there.
  - Integration tests here exercise the full stack end-to-end.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from claims.infrastructure.database import Base, init_db
from claims.infrastructure.encryption import init_encryptor
from config import get_settings

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://claims:claims@localhost:5432/claimsdb_test",
)

# ── Test-scoped event loop ────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ── Test DB setup ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Each test gets its own transaction that is rolled back at the end."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        async with session.begin():
            yield session
            await session.rollback()


# ── App fixture ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def app(test_engine):
    """FastAPI app wired to test DB."""
    init_encryptor("")  # no encryption in tests
    init_db(TEST_DB_URL)

    # Override the get_session dependency
    from main import app as fastapi_app
    from claims.infrastructure.database import get_session

    factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_session():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    fastapi_app.dependency_overrides[get_session] = override_get_session
    yield fastapi_app
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Shared test data factories ────────────────────────────────────────────

COVERAGE_RULES_STANDARD = [
    {
        "service_type": "SPECIALIST_VISIT",
        "coverage_percentage": 80,
        "annual_limit": 5000.00,
        "per_visit_limit": 300.00,
        "copay": 30.00,
        "requires_preauth": False,
        "network_restriction": "ANY",
        "excluded_diagnosis_codes": [],
    },
    {
        "service_type": "PREVENTIVE",
        "coverage_percentage": 100,
        "annual_limit": None,
        "per_visit_limit": None,
        "copay": None,
        "requires_preauth": False,
        "network_restriction": "ANY",
        "excluded_diagnosis_codes": [],
    },
    {
        "service_type": "EMERGENCY",
        "coverage_percentage": 90,
        "annual_limit": 50000.00,
        "per_visit_limit": None,
        "copay": 150.00,
        "requires_preauth": False,
        "network_restriction": "ANY",
        "excluded_diagnosis_codes": [],
    },
]


async def create_test_member(client: AsyncClient) -> dict:
    resp = await client.post("/api/v1/members", json={
        "member_id": f"MBR-{uuid.uuid4().hex[:8].upper()}",
        "name": "Jane Test",
        "date_of_birth": "1985-06-15",
        "email": "jane.test@example.com",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def create_test_policy(client: AsyncClient, holder_member_id: str) -> dict:
    today = date.today()
    resp = await client.post("/api/v1/policies", json={
        "holder_member_id": holder_member_id,
        "policy_number": f"POL-{uuid.uuid4().hex[:8].upper()}",
        "effective_date": str(date(today.year, 1, 1)),
        "expiration_date": str(date(today.year, 12, 31)),
        "deductible_amount": 500.00,
        "out_of_pocket_max": 5000.00,
        "coverage_rules": COVERAGE_RULES_STANDARD,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()
