import pytest

from propapp_pipeline.geo.allocate import Correspondence as C
from propapp_pipeline.geo.allocate import CorrespondenceIndex, allocate
from propapp_pipeline.models import GeoValue, Period

Y = Period.year(2024)
Q = Period.quarter(2025, 1)


@pytest.fixture
def idx():
    return CorrespondenceIndex.from_rows([
        C("SA2", "101", "10001", 300, 0.75),
        C("SA2", "101", "10002", 100, 0.25),
        C("POA", "2000", "10002", 100, 0.5),
        C("POA", "2000", "10009", 100, 0.5),
        C("POA", "2001", "10002", 300, 1.0),
    ])


def value_for(res, code, metric=None):
    return next(o.value for o in res.observations
                if o.suburb_code == code and (metric is None or o.metric == metric))


def test_additive_splits_by_ratio(idx):
    res = allocate([GeoValue("SA2", "101", "population", Y, 1000)], idx, "abs_erp")
    assert {o.suburb_code: o.value for o in res.observations} == {"10001": 750, "10002": 250}
    assert {o.source_geography for o in res.observations} == {"SA2"}


def test_intensive_is_weighted_mean_of_overlapping_sources(idx):
    res = allocate([
        GeoValue("POA", "2000", "median_weekly_rent_all_q", Q, 500),
        GeoValue("POA", "2001", "median_weekly_rent_all_q", Q, 700),
    ], idx, "nsw_rent")
    assert value_for(res, "10002") == pytest.approx(650)
    assert value_for(res, "10009") == pytest.approx(500)


def test_unknown_code_counts_unmatched(idx):
    res = allocate([GeoValue("SA2", "999", "population", Y, 5)], idx, "abs_erp")
    assert (res.matched, res.total, res.observations) == (0, 1, [])


def test_sal_values_pass_through(idx):
    res = allocate([GeoValue("SAL", "10001", "median_age", Y, 38)], idx, "abs_census")
    assert (res.matched, res.total) == (1, 1)
    assert res.observations[0].value == 38 and res.observations[0].source_geography == "SAL"


def test_targets_unknown_is_empty(idx):
    assert idx.targets("SA2", "nope") == []
