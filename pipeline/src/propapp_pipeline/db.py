from datetime import date

import psycopg

from propapp_pipeline.models import Observation


def connect(url: str, *, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(url, autocommit=autocommit)


def start_run(conn: psycopg.Connection, source: str) -> int:
    return conn.execute(
        "insert into data.ingestion_runs (source, status) values (%s, 'running') returning id",
        (source,),
    ).fetchone()[0]


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    status: str,
    rows_parsed: int | None,
    rows_written: int | None,
    match_rate: float | None,
    error: str | None,
    raw_keys: list[str],
) -> None:
    conn.execute(
        """
        update data.ingestion_runs set finished_at = now(), status = %s, rows_parsed = %s,
            rows_written = %s, match_rate = %s, error = %s, raw_keys = %s
        where id = %s
        """,
        (status, rows_parsed, rows_written, match_rate, error, raw_keys, run_id),
    )


def previous_rows_written(conn: psycopg.Connection, source: str) -> int | None:
    row = conn.execute(
        "select rows_written from data.ingestion_runs where source = %s and status = 'success' "
        "order by started_at desc, id desc limit 1",
        (source,),
    ).fetchone()
    return row[0] if row else None


def last_success_date(conn: psycopg.Connection, source: str) -> date | None:
    row = conn.execute(
        "select max(started_at)::date from data.ingestion_runs "
        "where source = %s and status = 'success'", (source,)).fetchone()
    return row[0]


def upsert_observations(conn: psycopg.Connection, obs: list[Observation]) -> int:
    """Upsert observations on the unique key. Returns the number of rows written."""
    with conn.cursor() as cur:
        cur.execute("drop table if exists _obs")
        cur.execute("create temp table _obs (like data.observations including defaults)")
        with cur.copy(
            "copy _obs (suburb_code, metric, period_start, period_granularity, value, source, "
            "source_geography) from stdin"
        ) as copy:
            for o in obs:
                copy.write_row((o.suburb_code, o.metric, o.period.start, o.period.granularity.value,
                                o.value, o.source, o.source_geography))
        cur.execute(
            """
            insert into data.observations
            select distinct on (source, metric, suburb_code, period_start, period_granularity) *
            from _obs
            on conflict (source, metric, suburb_code, period_start, period_granularity)
            do update set value = excluded.value, source_geography = excluded.source_geography,
                          ingested_at = excluded.ingested_at
            """
        )
        written = cur.rowcount
        cur.execute("drop table _obs")
    return written
