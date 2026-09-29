from datetime import date

import pytest

from propapp_pipeline.cli import main
from propapp_pipeline.db import connect
from propapp_pipeline.scoring import engine
from propapp_pipeline.scoring.engine import run_scoring
from propapp_pipeline.scoring.weights import WEIGHTS_DIR, load_weights

W = load_weights(WEIGHTS_DIR / "v1.yaml")


def query(db_url, sql):
    with connect(db_url) as conn:
        return conn.execute(sql).fetchall()


def count(db_url, table):
    return query(db_url, f"select count(*) from data.{table}")[0][0]


def test_run_scoring_writes_scores_and_factors(seeded):
    assert run_scoring(seeded, date(2025, 12, 31), W) == 3
    rows = dict(query(seeded, "select suburb_code, coverage from data.scores"))
    assert rows == {"10001": "fundamentals_market", "10002": "fundamentals",
                    "10003": "insufficient"}
    (as_of, cutoff, version), = query(
        seeded, "select distinct as_of, cutoff, model_version from data.scores")
    assert (as_of, cutoff, version) == (date(2025, 12, 1), date(2025, 12, 31), "v1")
    drivers = query(seeded, "select top_drivers from data.scores where suburb_code='10001'")[0][0]
    assert drivers and isinstance(drivers[0], str)
    factors = query(seeded, "select distinct layer from data.score_factors "
                            "where suburb_code='10001'")
    assert {r[0] for r in factors} == {"fundamentals", "market"}
    assert query(seeded, "select status, suburbs_scored from data.score_runs") == [("success", 3)]


def test_rescore_replaces(seeded):
    run_scoring(seeded, date(2025, 12, 30), W)
    run_scoring(seeded, date(2025, 12, 31), W)
    assert count(seeded, "scores") == 3 and count(seeded, "score_runs") == 2


def test_older_snapshot_factors_pruned(seeded):
    run_scoring(seeded, date(2025, 11, 30), W)
    run_scoring(seeded, date(2025, 12, 31), W)
    assert count(seeded, "scores") == 6
    assert {r[0] for r in query(seeded, "select distinct as_of from data.score_factors")} == {
        date(2025, 12, 1)}


def test_failed_scoring_keeps_previous_scores(seeded, monkeypatch):
    run_scoring(seeded, date(2025, 12, 31), W)

    def boom(*args):
        raise RuntimeError("explain broke")

    monkeypatch.setattr(engine, "explain", boom)
    with pytest.raises(RuntimeError):
        run_scoring(seeded, date(2025, 12, 31), W)
    assert count(seeded, "scores") == 3
    runs = query(seeded, "select status, error from data.score_runs order by id")
    assert runs[-1][0] == "failed" and "explain broke" in runs[-1][1]


def test_cli_score_exit_codes(seeded, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", seeded)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert main(["score", "--cutoff", "2025-12-31", "--weights", "v1"]) == 0
    monkeypatch.setattr(engine, "explain", lambda *a: (_ for _ in ()).throw(RuntimeError("x")))
    assert main(["score", "--cutoff", "2025-12-31"]) == 1
