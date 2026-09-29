from datetime import date

import numpy as np
import pandas as pd
import pytest

from propapp_pipeline.db import connect
from propapp_pipeline.scoring.backtest import (
    backtest_dates,
    outcomes,
    prepare,
    rank_metrics,
    run_backtest,
    tune,
)
from propapp_pipeline.scoring.observations import as_of_view
from propapp_pipeline.scoring.weights import WEIGHTS_DIR, load_weights

from .conftest import SEED_ROWS
from .helpers import frame, monthly, yearly

W = load_weights(WEIGHTS_DIR / "v1.yaml")
STATES = pd.Series({"10001": "NSW", "10002": "NSW", "10003": "NSW"})


def test_backtest_dates():
    assert backtest_dates(2016, 2017) == [date(2016, 6, 30), date(2016, 12, 31),
                                          date(2017, 6, 30), date(2017, 12, 31)]


def test_rank_metrics_perfect_order():
    s = pd.Series(range(20), dtype=float)
    rho, excess, n = rank_metrics(s, s * 0.01)
    assert rho == pytest.approx(1.0) and n == 20 and excess > 0


def test_rank_metrics_too_few():
    rho, excess, n = rank_metrics(pd.Series([1.0, 2.0]), pd.Series([0.1, np.nan]))
    assert np.isnan(rho) and n == 1


def test_outcomes_use_future_values():
    obs = frame([monthly("10001", "median_sale_price_house_12m", 2023, 6, 800_000),
                 monthly("10001", "median_sale_price_house_12m", 2024, 6, 1_000_000)])
    growth = outcomes(as_of_view(obs, date(2100, 1, 1)),
                      pd.Series({"10001": pd.Timestamp("2023-06-01")}),
                      pd.Series({"10001": "house"}), 12)
    assert growth["10001"] == pytest.approx(0.25)


def test_prepare_uses_only_past_data():
    base = frame(SEED_ROWS)
    later = frame([*SEED_ROWS, yearly("10002", "population", 2027, 5000)])
    d = date(2025, 12, 31)
    a, b = prepare(base, STATES, [d], W)[0], prepare(later, STATES, [d], W)[0]
    pd.testing.assert_frame_equal(a.pct_fund, b.pct_fund)


def test_census_fixed_in_backtest():
    [p] = prepare(frame(SEED_ROWS), STATES, [date(2019, 6, 30)], W)
    assert p.pct_fund["median_household_income"].notna().any()


def test_tune_is_deterministic_and_valid(tmp_path):
    prepared = prepare(frame(SEED_ROWS), STATES, [date(2025, 12, 31)], W)
    a = tune(prepared, W, samples=5, seed=7, weights_dir=tmp_path)
    b = tune(prepared, W, samples=5, seed=7, weights_dir=tmp_path)
    assert a == b and a.model_version == "v1"
    assert sum(a.fundamentals.values()) == pytest.approx(1)
    assert sum(a.market.values()) == pytest.approx(1)


def test_backtest_does_not_write_scores(seeded, tmp_path):
    report = run_backtest(seeded, 2025, 2025, 2025, W, tune_samples=None,
                          reports_dir=tmp_path, weights_dir=tmp_path)
    with connect(seeded) as conn:
        counts = conn.execute("select (select count(*) from data.scores), "
                              "(select count(*) from data.backtest_results)").fetchone()
    assert counts == (0, 4)
    text = (tmp_path / "v1-backtest.md").read_text()
    assert report.model_version == "v1" and "Census" in text and "late lodgements" in text


def test_tune_finds_better_weights(tmp_path):
    from propapp_pipeline.scoring.backtest import Prepared
    from propapp_pipeline.scoring.factors import FUNDAMENTALS

    (tmp_path / "v1.yaml").write_text("")
    ranks = pd.Series(range(30), index=[f"s{i}" for i in range(30)], dtype=float)
    pct = pd.DataFrame({f: (ranks if f == "population_growth_3y" else 29 - ranks) * 100 / 29
                        for f in FUNDAMENTALS})
    p = Prepared(date(2020, 6, 30), pct, pd.DataFrame(), {12: ranks, 24: ranks}, 0.0)
    tuned = tune([p], W, samples=400, seed=1, weights_dir=tmp_path)
    assert tuned.model_version == "v2" and tuned is not W
    assert tuned.fundamentals["population_growth_3y"] > W.fundamentals["population_growth_3y"]
    assert tuned.market == W.market


def test_cli_backtest(seeded, tmp_path, monkeypatch):
    from propapp_pipeline.cli import main
    from propapp_pipeline.scoring import backtest

    monkeypatch.setenv("DATABASE_URL", seeded)
    monkeypatch.setattr(backtest, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(backtest.run_backtest, "__kwdefaults__",
                        {"reports_dir": tmp_path, "weights_dir": tmp_path})
    assert main(["backtest", "--years", "2025", "--holdout-from", "2025",
                 "--weights", "v1"]) == 0
    assert (tmp_path / "v1-backtest.md").exists()


# --- review fixes ---------------------------------------------------------------------

def _no_market(prepared):
    return [replace_market(p) for p in prepared]


def replace_market(p):
    from dataclasses import replace as dc_replace
    return dc_replace(p, pct_market=p.pct_market.iloc[0:0])


def test_tune_keeps_market_weights_without_market_coverage(tmp_path):
    prepared = _no_market(prepare(frame(SEED_ROWS), STATES, [date(2025, 12, 31)], W))
    tuned = tune(prepared, W, samples=20, seed=3, weights_dir=tmp_path)
    assert tuned.market == W.market


def test_market_coverage_recorded():
    [p] = prepare(frame(SEED_ROWS), STATES, [date(2025, 12, 31)], W)
    assert p.market_coverage == pytest.approx(1 / 2)   # 10001 of the 2 NSW suburbs scored


def test_training_dates_embargoed_before_holdout():
    from propapp_pipeline.scoring.backtest import training_dates
    dates = backtest_dates(2020, 2021)
    assert training_dates(dates, 2022, 12) == [date(2020, 6, 30), date(2020, 12, 31)]
    assert training_dates(dates, 2022, 24) == []


def test_backtest_view_applies_release_lags():
    from propapp_pipeline.scoring.backtest import backtest_view
    obs = frame([yearly("10001", "population", 2019, 1000, "abs_erp")])
    assert backtest_view(obs, date(2020, 1, 31)).empty
    assert len(backtest_view(obs, date(2020, 4, 30))) == 1


def test_tuned_report_shows_baseline_and_skips_identical_version(seeded, tmp_path):
    (tmp_path / "v1.yaml").write_text((WEIGHTS_DIR / "v1.yaml").read_text())
    report = run_backtest(seeded, 2025, 2025, 2026, W, tune_samples=3,
                          reports_dir=tmp_path, weights_dir=tmp_path)
    versions = {r["model_version"] for r in report.rows}
    if report.model_version == "v1":           # starting weights won: nothing new written
        assert not (tmp_path / "v2.yaml").exists()
    else:
        assert versions == {"v1", report.model_version}
        assert "v1" in (tmp_path / f"{report.model_version}-backtest.md").read_text()
