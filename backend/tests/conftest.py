"""Test wiring.

Pure tests (diff, routing, extraction, adapters) need nothing.
Database tests use a *dedicated* database on the same Postgres server as local dev: `TEST_DATABASE_URL`
if set, otherwise `DATABASE_URL` with `_test` appended to the database name. It is created and migrated
on first use, and each test runs inside a transaction that is rolled back. Sharing the dev database
would make tests depend on whatever the operator configured there (Slack webhooks, real assessments).
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from radar.assess.llm import LLM
from radar.config import Settings
from radar.container import build_deps
from radar.models import Base, Team
from tests.fakes import FakeLLM, FixtureFetcher, RecordingNotifier

DEV_DB = os.environ.get("DATABASE_URL") or "postgresql+psycopg://radar:radar@localhost:5434/radar"
TEST_DB = os.environ.get("TEST_DATABASE_URL") or (
    make_url(DEV_DB).set(database=f"{make_url(DEV_DB).database}_test").render_as_string(hide_password=False)
)


def _ensure_test_database() -> None:
    """Create the test database (and the pgvector extension + schema) if it does not exist yet."""
    url = make_url(TEST_DB)
    admin = create_engine(url.set(database=make_url(DEV_DB).database), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()
    eng = create_engine(TEST_DB)
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(conn)
    eng.dispose()


@pytest.fixture(scope="session")
def engine():
    try:
        _ensure_test_database()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"database not available at {TEST_DB}: {exc}")
    return create_engine(TEST_DB, pool_pre_ping=True)


@pytest.fixture
def db(engine) -> Session:
    """A session inside an outer transaction that is always rolled back."""
    connection = engine.connect()
    outer = connection.begin()
    session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(openai_api_key="test", llm_daily_budget_usd=100.0, backfill_days=365, page_change_min_chars=40, _env_file=None)


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fetcher() -> FixtureFetcher:
    return FixtureFetcher()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest.fixture
def deps(settings, fake_llm, fetcher, notifier):
    return build_deps(settings, llm_client=fake_llm, fetcher=fetcher, notifier=notifier)


@pytest.fixture
def unconfigured_deps(settings, fetcher, notifier):
    return build_deps(settings, llm_client=None, fetcher=fetcher, notifier=notifier)


@pytest.fixture
def teams(db) -> list[Team]:
    """Reuse seeded teams when present. Unique(key) is checked against committed rows, not the savepoint."""
    wanted = [
        {"key": "marketing", "name": "Marketing", "lens": "positioning"},
        {"key": "product", "name": "Product", "lens": "coverage"},
        {"key": "rnd", "name": "R&D", "lens": "technical"},
    ]
    existing = {row.key: row for row in db.scalars(select(Team)).all()}
    rows: list[Team] = []
    for spec in wanted:
        row = existing.get(spec["key"])
        if row is None:
            row = Team(
                key=spec["key"],
                name=spec["name"],
                lens=spec["lens"],
                immediate_threshold=75,
                digest_threshold=50,
            )
            db.add(row)
        rows.append(row)
    db.flush()
    return rows


@pytest.fixture
def llm(settings, fake_llm) -> LLM:
    return LLM(fake_llm, settings)
