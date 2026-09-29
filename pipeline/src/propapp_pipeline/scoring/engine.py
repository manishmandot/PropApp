"""Scoring engine: pure `score_as_of` plus `run_scoring`, which writes a month snapshot."""
import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

from propapp_pipeline.db import connect
from propapp_pipeline.scoring.combine import combine, percentiles
from propapp_pipeline.scoring.explain import explain
from propapp_pipeline.scoring.fundamentals import compute_fundamentals
from propapp_pipeline.scoring.market import compute_market
from propapp_pipeline.scoring.observations import (
    as_of_view,
    load_observations,
    load_suburb_states,
)
from propapp_pipeline.scoring.weights import Weights

log = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    scores: pd.DataFrame   # index suburb_code; scores, coverage, top_drivers, watch_outs
    factors: pd.DataFrame  # long, with raw_value


def score_as_of(obs: pd.DataFrame, as_of: date, weights: Weights,
                states: pd.Series) -> ScoreResult:
    view = as_of_view(obs, as_of)
    fundamentals = compute_fundamentals(view)
    market = compute_market(view, as_of, weights)
    combined = combine(percentiles(fundamentals),
                       percentiles(market.values, states), weights)
    raw = fundamentals.join(market.values, how="outer")
    explained = explain(combined.factors, raw)
    scores = combined.scores.join(explained)
    for column in ("top_drivers", "watch_outs"):
        scores[column] = scores[column].apply(lambda v: v if isinstance(v, list) else [])
    raw_long = raw.rename_axis("suburb_code").stack().rename("raw_value").reset_index()
    raw_long.columns = ["suburb_code", "factor", "raw_value"]
    factors = combined.factors.merge(raw_long, on=["suburb_code", "factor"], how="left")
    return ScoreResult(scores, factors)


def _none(value):
    return None if pd.isna(value) else float(value)


def _write(conn, result: ScoreResult, weights: Weights, as_of: date, cutoff: date,
           run_id: int) -> None:
    version = weights.model_version
    with conn.cursor() as cur:
        cur.execute("delete from data.scores where model_version = %s and as_of = %s",
                    (version, as_of))
        with cur.copy("copy data.scores (suburb_code, model_version, as_of, cutoff, run_id, "
                      "propapp_score, fundamentals_score, market_score, coverage, top_drivers, "
                      "watch_outs) from stdin") as copy:
            for code, r in result.scores.iterrows():
                copy.write_row((code, version, as_of, cutoff, run_id, _none(r.propapp_score),
                                _none(r.fundamentals_score), _none(r.market_score), r.coverage,
                                r.top_drivers, r.watch_outs))
        with cur.copy("copy data.score_factors (suburb_code, model_version, as_of, factor, "
                      "layer, raw_value, percentile, weight, contribution) from stdin") as copy:
            for r in result.factors.itertuples():
                copy.write_row((r.suburb_code, version, as_of, r.factor, r.layer,
                                _none(r.raw_value), r.percentile, r.weight, r.contribution))
        # Factor detail is kept for the latest snapshot of each model version only.
        cur.execute(
            "delete from data.score_factors where model_version = %s and as_of < "
            "(select max(as_of) from data.scores where model_version = %s)",
            (version, version))


def run_scoring(db_url: str, cutoff: date, weights: Weights) -> int:
    """Score every suburb with data up to `cutoff`; store the month snapshot. Returns count."""
    as_of = cutoff.replace(day=1)
    with connect(db_url, autocommit=True) as run_log:
        run_id = run_log.execute(
            "insert into data.score_runs (model_version, as_of, status) "
            "values (%s, %s, 'running') returning id", (weights.model_version, as_of),
        ).fetchone()[0]
        try:
            with connect(db_url, autocommit=True) as conn:
                obs, states = load_observations(conn), load_suburb_states(conn)
                result = score_as_of(obs, cutoff, weights, states)
                with conn.transaction():
                    _write(conn, result, weights, as_of, cutoff, run_id)
        except Exception as exc:
            log.exception("score run %s failed", run_id)
            run_log.execute(
                "update data.score_runs set status = 'failed', finished_at = now(), error = %s "
                "where id = %s", (f"{type(exc).__name__}: {exc}", run_id))
            raise
        run_log.execute(
            "update data.score_runs set status = 'success', finished_at = now(), "
            "suburbs_scored = %s where id = %s", (len(result.scores), run_id))
        # The web app's suburb list is a materialized view over the current (latest
        # successful) model, so it can only be refreshed once this run counts as successful.
        run_log.execute("refresh materialized view api.suburbs")
    return len(result.scores)
