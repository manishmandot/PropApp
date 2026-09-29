from datetime import date

import pytest

from propapp_pipeline.models import (
    METRICS,
    Granularity,
    Kind,
    Observation,
    Period,
)


def test_period_rejects_mid_quarter():
    with pytest.raises(ValueError):
        Period(date(2024, 2, 1), Granularity.QUARTER)


def test_period_rejects_mid_month():
    with pytest.raises(ValueError):
        Period(date(2024, 2, 15), Granularity.MONTH)


def test_period_quarter_helper():
    assert Period.quarter(2024, 3) == Period(date(2024, 7, 1), Granularity.QUARTER)


def test_period_helpers():
    assert Period.month(2025, 3).start == date(2025, 3, 1)
    assert Period.year(2021) == Period(date(2021, 1, 1), Granularity.YEAR)


def test_observation_rejects_unknown_metric():
    with pytest.raises(ValueError):
        Observation("10001", "vacancy_rate", Period.year(2024), 1.0, "x", "SAL")


def test_metric_kinds():
    assert METRICS["population"].kind is Kind.ADDITIVE
    assert METRICS["median_weekly_rent_all_q"].kind is Kind.INTENSIVE


def test_vocabulary_is_complete():
    assert len(METRICS) == 20
    assert METRICS["owner_occupier_share"].max == 1
    assert METRICS["median_sale_price_unit_3m"].min == 10_000
