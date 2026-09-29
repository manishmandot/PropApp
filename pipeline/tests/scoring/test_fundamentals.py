from datetime import date

import numpy as np
import pytest

from propapp_pipeline.scoring.factors import FUNDAMENTALS
from propapp_pipeline.scoring.fundamentals import compute_fundamentals
from propapp_pipeline.scoring.observations import as_of_view

from .helpers import frame, monthly, quarterly, yearly


def view_of(rows, as_of=date(2026, 9, 29)):
    return as_of_view(frame(rows), as_of)


def test_columns_are_fundamentals():
    f = compute_fundamentals(view_of([yearly("10001", "owner_occupier_share", 2021, 0.6)]))
    assert list(f.columns) == FUNDAMENTALS
    assert f.loc["10001", "owner_occupier_share"] == 0.6


def test_population_growth_cagr():
    f = compute_fundamentals(view_of([yearly("10001", "population", 2021, 1000),
                                      yearly("10001", "population", 2024, 1331)]))
    assert f.loc["10001", "population_growth_3y"] == pytest.approx(0.10)


def test_growth_with_zero_base_is_missing():
    f = compute_fundamentals(view_of([yearly("10001", "population", 2021, 0),
                                      yearly("10001", "population", 2024, 50),
                                      yearly("10002", "population", 2024, 50)]))
    assert np.isnan(f.loc["10001", "population_growth_3y"])
    assert np.isnan(f.loc["10002", "population_growth_3y"])


def test_supply_pressure_scales_partial_year():
    rows = [monthly("10001", "building_approvals_dwellings", 2025, m, 10) for m in range(2, 13)]
    rows.append(monthly("10001", "building_approvals_dwellings", 2024, 12, 999))  # outside window
    rows.append(yearly("10001", "dwellings_total", 2021, 1000))
    f = compute_fundamentals(view_of(rows))
    assert f.loc["10001", "supply_pressure"] == pytest.approx(120)


def test_supply_pressure_needs_ten_months_and_dwellings():
    rows = [monthly("10001", "building_approvals_dwellings", 2025, m, 10) for m in range(4, 13)]
    rows += [yearly("10001", "dwellings_total", 2021, 1000)]
    rows += [monthly("10002", "building_approvals_dwellings", 2025, m, 10) for m in range(1, 13)]
    rows += [yearly("10002", "dwellings_total", 2021, 0)]
    f = compute_fundamentals(view_of(rows))
    assert np.isnan(f.loc["10001", "supply_pressure"])
    assert np.isnan(f.loc["10002", "supply_pressure"])


def test_unemployment_rate_and_change():
    f = compute_fundamentals(view_of([
        quarterly("10001", "unemployed_count", 2024, 4, 32),
        quarterly("10001", "labour_force_count", 2024, 4, 800),
        quarterly("10001", "unemployed_count", 2023, 4, 40),
        quarterly("10001", "labour_force_count", 2023, 4, 800),
    ]))
    assert f.loc["10001", "unemployment_rate"] == pytest.approx(4.0)
    assert f.loc["10001", "unemployment_change"] == pytest.approx(-1.0)


def test_zero_labour_force_is_missing():
    f = compute_fundamentals(view_of([quarterly("10001", "unemployed_count", 2024, 4, 0),
                                      quarterly("10001", "labour_force_count", 2024, 4, 0)]))
    assert np.isnan(f.loc["10001", "unemployment_rate"])
