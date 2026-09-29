import os
from pathlib import Path

import psycopg
import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
DATA_TABLES = ["observations", "geo_correspondences", "nsw_sales", "ingestion_runs", "sources",
               "suburbs"]


def _with_db(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture(scope="session")
def _test_database():
    admin_url = os.environ.get(
        "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"
    )
    dbname = f"propapp_test_{os.getpid()}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'drop database if exists "{dbname}"')
        admin.execute(f'create database "{dbname}" template template0')
    url = _with_db(admin_url, dbname)
    with psycopg.connect(url, autocommit=True) as conn:
        for migration in sorted(MIGRATIONS.glob("*.sql")):
            conn.execute(migration.read_text())
    yield url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'drop database if exists "{dbname}" with (force)')


@pytest.fixture
def db_url(_test_database):
    yield _test_database
    with psycopg.connect(_test_database, autocommit=True) as conn:
        conn.execute("truncate " + ", ".join(f"data.{t}" for t in DATA_TABLES) + " cascade")
