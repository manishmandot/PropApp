import psycopg
import pytest

from propapp_pipeline.db import connect


def test_schema_tables_exist(db_url):
    with connect(db_url) as conn:
        names = {r[0] for r in conn.execute(
            "select table_name from information_schema.tables where table_schema='data'")}
    assert names == {"suburbs", "geo_correspondences", "observations",
                     "ingestion_runs", "sources", "nsw_sales"}


def test_observation_unique_key(db_url):
    with connect(db_url) as conn:
        conn.execute("insert into data.suburbs (sal_code, name, state) values ('10001','A','NSW')")
        insert = ("insert into data.observations (suburb_code, metric, period_start, "
                  "period_granularity, value, source, source_geography) "
                  "values ('10001','population','2024-01-01','year',1,'abs_erp','SA2')")
        conn.execute(insert)
        with pytest.raises(psycopg.errors.UniqueViolation):
            conn.execute(insert)
