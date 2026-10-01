from datetime import UTC, date, datetime, timedelta

import psycopg
import pytest

from propapp_pipeline.db import connect
from propapp_pipeline.scoring.engine import run_scoring
from propapp_pipeline.scoring.weights import WEIGHTS_DIR, load_weights

from .conftest import insert_observations
from .helpers import yearly

W = load_weights(WEIGHTS_DIR / "v1.yaml")


def fetch(db_url, sql, *params):
    with connect(db_url) as conn:
        return conn.execute(sql, params).fetchall()


@pytest.fixture
def scored(seeded):
    with connect(seeded) as conn:
        conn.execute("insert into data.suburbs (sal_code, name, state) values "
                     "('20001', 'Albert Park (Vic.)', 'VIC')")
    insert_observations(seeded, [yearly("20001", "owner_occupier_share", 2021, 0.5, "abs_census")])
    run_scoring(seeded, date(2025, 12, 31), W)
    return seeded


def test_current_model_empty_before_scoring(db_url):
    assert fetch(db_url, "select * from api.current_model") == []


def test_web_reader_can_read_api_but_not_data(scored):
    with connect(scored) as conn:
        conn.execute("set role web_reader")
        assert conn.execute("select count(*) from api.suburbs").fetchone()[0] == 4
        assert conn.execute("select count(*) from api.suburb_shapes").fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("select * from data.scores")


def test_suburbs_view_fields(scored):
    [row] = fetch(scored, "select slug, coverage, market_reason, median_price, dwelling_type, "
                          "gross_yield is not null from api.suburbs where sal_code = '10001'")
    assert row == ("10001-alpha-nsw", "fundamentals_market", None, 1_100_000, "house", True)


def test_market_reason_texts(scored):
    reasons = dict(fetch(scored, "select sal_code, market_reason from api.suburbs"))
    assert reasons["10002"].startswith("Fewer than 20 sales")
    assert reasons["20001"] == "No market data for this state yet"
    assert fetch(scored, "select slug from api.suburbs where sal_code='20001'") == [
        ("20001-albert-park-vic",)]


def test_history_factors_and_model(scored):
    assert fetch(scored, "select model_version from api.current_model") == [("v1",)]
    assert fetch(scored, "select as_of from api.score_history where sal_code='10001'") == [
        (date(2025, 12, 1),)]
    assert len(fetch(scored, "select * from api.suburb_factors where sal_code='10001'")) > 5


def test_freshness_flags_overdue_source(db_url):
    with connect(db_url) as conn:
        conn.execute("insert into data.sources (id, name, commercial_use, cadence_days) values "
                     "('fast','Fast','confirmed',7), ('slow','Slow','confirmed',365), "
                     "('never','Never','pending',30)")
        old = datetime.now(UTC) - timedelta(days=20)
        conn.execute("insert into data.ingestion_runs (source, started_at, finished_at, status) "
                     "values ('fast', %s, %s, 'success'), ('slow', %s, %s, 'success')",
                     (old, old, old, old))
    stale = dict(fetch(db_url, "select id, is_stale from api.source_freshness"))
    assert stale == {"fast": True, "slow": False, "never": True}


def test_median_price_uses_scoring_window(scored):
    # a partial recent month (inside the 3-month lag) must not replace the scored month
    insert_observations(scored, [
        ("10001", "median_sale_price_house_12m", date(2025, 11, 1), "month", 9_999_999,
         "nsw_vg_sales"),
        ("10001", "sales_count_house_12m", date(2025, 11, 1), "month", 5, "nsw_vg_sales"),
        ("10002", "median_sale_price_house_12m", date(2023, 3, 1), "month", 700_000,
         "nsw_vg_sales"),
        ("10002", "sales_count_house_12m", date(2023, 3, 1), "month", 30, "nsw_vg_sales"),
    ])
    with connect(scored) as conn:
        conn.execute("refresh materialized view api.suburbs")
    rows = {r[0]: r[1:] for r in fetch(
        scored, "select sal_code, median_price, median_price_month from api.suburbs")}
    assert rows["10001"] == (1_100_000, date(2025, 9, 1))
    assert rows["10002"] == (None, None)          # older than the 6-month market window


def test_web_reader_statement_timeout(db_url):
    [(config,)] = fetch(db_url, "select rolconfig from pg_roles where rolname = 'web_reader'")
    assert "statement_timeout=5s" in config
