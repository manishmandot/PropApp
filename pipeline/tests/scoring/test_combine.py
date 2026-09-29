import numpy as np
import pandas as pd
import pytest

from propapp_pipeline.scoring.combine import combine, percentiles
from propapp_pipeline.scoring.factors import FUNDAMENTALS, MARKET
from propapp_pipeline.scoring.weights import WEIGHTS_DIR, load_weights

W = load_weights(WEIGHTS_DIR / "v1.yaml")


def full(layer_columns, values: dict[str, float]) -> pd.DataFrame:
    """One-row-per-suburb percentile frame; unspecified factors are 50."""
    return pd.DataFrame({s: {c: v.get(c, 50.0) for c in layer_columns}
                         for s, v in values.items()}).T


def test_percentile_rank_and_direction():
    p = percentiles(pd.DataFrame({"supply_pressure": [1.0, 2.0, 3.0],
                                  "gross_yield": [0.03, 0.05, 0.04]}, index=list("abc")))
    assert p["supply_pressure"].tolist() == [100.0, 50.0, 0.0]
    assert p["gross_yield"].tolist() == [0.0, 100.0, 50.0]


def test_single_value_is_50_and_nan_kept():
    p = percentiles(pd.DataFrame({"momentum": [0.1, np.nan]}, index=["a", "b"]))
    assert p.loc["a", "momentum"] == 50 and np.isnan(p.loc["b", "momentum"])


def test_winsorised_tails_tie():
    values = list(range(199)) + [10_000]
    p = percentiles(pd.DataFrame({"momentum": values}, index=[str(i) for i in range(200)]))
    assert p.loc["199", "momentum"] == p.loc["198", "momentum"]


def test_market_ranked_within_state():
    raw = pd.DataFrame({"momentum": [1.0, 2.0, 10.0, 20.0]}, index=["n1", "n2", "v1", "v2"])
    states = pd.Series({"n1": "NSW", "n2": "NSW", "v1": "VIC", "v2": "VIC"})
    p = percentiles(raw, states)
    assert p["momentum"].tolist() == [0.0, 100.0, 0.0, 100.0]


def test_missing_weight_threshold():
    fund = full(FUNDAMENTALS, {"a": {}, "b": {}})
    fund.loc["a", ["owner_occupier_share", "unemployment_change"]] = np.nan   # 0.25 missing
    fund.loc["b", ["owner_occupier_share", "unemployment_change",
                   "population_growth_3y"]] = np.nan                         # 0.55 missing
    scores = combine(fund, pd.DataFrame(columns=MARKET), W).scores
    assert scores.loc["a", "fundamentals_score"] == pytest.approx(50)
    assert np.isnan(scores.loc["b", "fundamentals_score"])
    assert scores.loc["b", "coverage"] == "insufficient"
    assert np.isnan(scores.loc["b", "propapp_score"])


def test_blend_and_coverage():
    fund = full(FUNDAMENTALS, {"a": {c: 80.0 for c in FUNDAMENTALS},
                               "b": {c: 70.0 for c in FUNDAMENTALS}})
    market = full(MARKET, {"a": {c: 40.0 for c in MARKET}, "m": {c: 90.0 for c in MARKET}})
    scores = combine(fund, market, W).scores
    assert scores.loc["a", "propapp_score"] == pytest.approx(60)
    assert scores.loc["a", "coverage"] == "fundamentals_market"
    assert scores.loc["b", "propapp_score"] == pytest.approx(70)
    assert scores.loc["b", "coverage"] == "fundamentals"
    assert scores.loc["m", "coverage"] == "insufficient"


def test_contributions_sum_to_layer_score():
    fund = full(FUNDAMENTALS, {"a": {"population_growth_3y": 90.0, "supply_pressure": 10.0}})
    fund.loc["a", "owner_occupier_share"] = np.nan
    result = combine(fund, pd.DataFrame(columns=MARKET), W)
    rows = result.factors[result.factors.suburb_code == "a"]
    assert rows.weight.sum() == pytest.approx(1)
    assert rows.contribution.sum() == pytest.approx(result.scores.loc["a", "fundamentals_score"])
    assert "owner_occupier_share" not in rows.factor.tolist()
