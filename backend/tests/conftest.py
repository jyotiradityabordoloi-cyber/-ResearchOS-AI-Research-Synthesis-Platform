"""Tests run against a real Postgres + pgvector database (`researchos_test`).

Start it with `docker compose up -d db` from the repo root. Override with TEST_DATABASE_URL.
"""

import os

TEST_DB = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://researchos:researchos@localhost:5434/researchos_test",
)
os.environ["DATABASE_URL"] = TEST_DB  # must be set before app modules import settings
os.environ.setdefault("AI_PROVIDER", "demo")
os.environ.setdefault("EMBEDDING_PROVIDER", "hash")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


VALID_INTERVIEW = {
    "participant_id": "P01",
    "participant_role": "Product Manager",
    "company_size": "50-200",
    "plan_tier": "Pro",
    "pain": "Spends hours every week copying interview notes into spreadsheets by hand.",
    "behavior": "Exports call transcripts and tags them manually in Google Sheets.",
    "verbatim_quote": "I lose an entire afternoon just organising notes.",
}


@pytest.fixture
def project(client):
    resp = client.post(
        "/api/projects",
        json={
            "name": "Onboarding research",
            "objectives": ["Understand activation drop-off"],
            "target_segments": ["SMB", "Mid-market"],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
