import logging
from dataclasses import dataclass
from datetime import date

import httpx

import propapp_pipeline.adapters  # noqa: F401  (registers adapters)
from propapp_pipeline.adapters.base import REGISTRY, NormaliseContext
from propapp_pipeline.db import (
    connect,
    finish_run,
    last_success_date,
    previous_rows_written,
    start_run,
    upsert_observations,
)
from propapp_pipeline.geo.allocate import CorrespondenceIndex
from propapp_pipeline.geo.match import SuburbMatcher
from propapp_pipeline.quality import QualityError, check
from propapp_pipeline.raw_store import RawStore
from propapp_pipeline.sources import sync_sources

log = logging.getLogger(__name__)


@dataclass
class RunOutcome:
    run_id: int
    status: str
    rows_written: int


def run_source(
    source_id: str,
    *,
    db_url: str,
    raw_store: RawStore,
    http: httpx.Client | None,
    today: date,
    config: dict,
    options: dict | None = None,
) -> RunOutcome:
    """Fetch, store, parse, normalise, check and load one source, logging the run.

    Observations are written in a single transaction, so a failure at any point
    leaves previously loaded data untouched.
    """
    adapter = REGISTRY[source_id](**(options or {}))
    source_config = config["sources"][source_id]
    with connect(db_url, autocommit=True) as run_log:
        sync_sources(run_log, config)
        previous = previous_rows_written(run_log, source_id)
        adapter.last_success = last_success_date(run_log, source_id)
        run_id = start_run(run_log, source_id)
        raw_keys: list[str] = []
        rows_parsed = match_rate = None
        try:
            raw = adapter.fetch(http, source_config)
            raw_keys = [raw_store.put(source_id, today, f) for f in raw]
            rows = adapter.parse(raw)
            rows_parsed = len(rows)
            with connect(db_url, autocommit=True) as conn, conn.transaction():
                index = CorrespondenceIndex.load(conn)
                ctx = NormaliseContext(conn, index, SuburbMatcher.load(conn, index), http,
                                       source_config, today)
                result = adapter.normalise(rows, ctx)
                match_rate = result.matched / result.total if result.total else 1.0
                report = check(result, previous, adapter.row_count_tolerance)
                if not report.passed:
                    raise QualityError("; ".join(report.failures))
                written = upsert_observations(conn, result.observations)
        except Exception as exc:
            log.exception("run %s for %s failed", run_id, source_id)
            finish_run(run_log, run_id, "failed", rows_parsed, 0, match_rate,
                       f"{type(exc).__name__}: {exc}", raw_keys)
            return RunOutcome(run_id, "failed", 0)
        finish_run(run_log, run_id, "success", rows_parsed, written, match_rate, None, raw_keys)
        return RunOutcome(run_id, "success", written)
