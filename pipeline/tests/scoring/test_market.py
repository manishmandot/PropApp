from datetime import date

import numpy as np
import pytest

from propapp_pipeline.scoring.factors import MARKET
from propapp_pipeline.scoring.market import compute_market
from propapp_pipeline.scoring.observations import as_of_view
from propapp_pipeline.scoring.weights import WEIGHTS_DIR, load_weights

from .helpers import frame, monthly, quarterly

W = load_weights(WEIGHTS_DIR / "v1.yaml")
AS_OF = date(2025, 9, 29)


def market(rows, as_of=AS_OF):
    return compute_market(as_of_view(frame(rows), as_of), as_of, W)


def counts(suburb, year, month, houses, units):
    return [monthly(suburb, "sales_count_house_12m", year, month, houses),
            monthly(suburb, "sales_count_unit_12m", year, month, units)]


def test_thin_market_not_eligible():
    result = market(counts("10001", 2025, 6, 12, 7))
    assert "10001" not in result.eligible and result.values.empty


def test_stale_market_not_eligible():
    assert "10001" not in market(counts("10001", 2025, 1, 40, 0)).eligible


def test_lodgement_lag_excludes_recent_months():
    rows = counts("10001", 2025, 6, 40, 0) + counts("10001", 2025, 8, 40, 0) + [
        monthly("10001", "median_sale_price_house_12m", 2025, 6, 1_000_000),
        monthly("10001", "median_sale_price_house_12m", 2025, 8, 5_000_000),
        monthly("10001", "median_sale_price_house_12m", 2024, 6, 800_000),
    ]
    result = market(rows)
    assert result.values.loc["10001", "price_growth_12m"] == pytest.approx(0.25)


def test_dominant_type_and_growth():
    rows = counts("10001", 2025, 6, 25, 30) + counts("10001", 2024, 6, 20, 20) + [
        monthly("10001", "median_sale_price_unit_12m", 2025, 6, 500_000),
        monthly("10001", "median_sale_price_unit_12m", 2024, 6, 400_000),
        monthly("10001", "median_sale_price_house_12m", 2025, 6, 2_000_000),
        monthly("10001", "median_sale_price_house_12m", 2024, 6, 1_000_000),
    ]
    result = market(rows)
    assert result.dwelling_type["10001"] == "unit"
    assert list(result.values.columns) == MARKET
    assert result.values.loc["10001", "price_growth_12m"] == pytest.approx(0.25)
    assert result.values.loc["10001", "sales_volume_change"] == pytest.approx(55 / 40 - 1)


def test_price_growth_needs_prior_year():
    rows = counts("10001", 2025, 6, 40, 0) + [
        monthly("10001", "median_sale_price_house_12m", 2025, 6, 1_000_000)]
    result = market(rows)
    assert "10001" in result.eligible
    assert np.isnan(result.values.loc["10001", "price_growth_12m"])
    assert np.isnan(result.values.loc["10001", "sales_volume_change"])


def test_gross_yield_falls_back_to_all_rent():
    rows = counts("10001", 2025, 6, 0, 30) + [
        monthly("10001", "median_sale_price_unit_12m", 2025, 6, 520_000),
        quarterly("10001", "median_weekly_rent_all_q", 2025, 2, 500),
        quarterly("10001", "median_weekly_rent_all_q", 2024, 2, 400),
    ]
    result = market(rows)
    assert result.values.loc["10001", "gross_yield"] == pytest.approx(0.05)
    assert result.values.loc["10001", "rent_growth_12m"] == pytest.approx(0.25)


def test_momentum():
    rows = counts("10001", 2025, 6, 40, 0) + [
        monthly("10001", "median_sale_price_house_3m", 2025, 6, 440_000),
        monthly("10001", "median_sale_price_house_3m", 2025, 3, 400_000),
        monthly("10001", "median_sale_price_house_12m", 2025, 6, 500_000),
        monthly("10001", "median_sale_price_house_12m", 2024, 6, 400_000),
    ]
    assert market(rows).values.loc["10001", "momentum"] == pytest.approx(1.1**4 - 1 - 0.25)
