from propapp_pipeline.adapters.base import NormaliseResult
from propapp_pipeline.models import Observation, Period
from propapp_pipeline.quality import check


def obs(n):
    return [Observation(str(10000 + i), "population", Period.year(2024), 1.0, "x", "SAL")
            for i in range(n)]


def test_first_run_skips_row_count():
    assert check(NormaliseResult(obs(10), 10, 10), None, 0.25).passed


def test_row_count_within_tolerance_passes():
    assert check(NormaliseResult(obs(80), 80, 80), previous_rows=100, tolerance=0.25).passed


def test_row_count_outside_tolerance_fails():
    r = check(NormaliseResult(obs(70), 70, 70), previous_rows=100, tolerance=0.25)
    assert not r.passed and "row count" in r.failures[0]


def test_low_match_rate_fails():
    r = check(NormaliseResult(obs(10), 97, 100), None, 0.25)
    assert not r.passed and "match rate" in r.failures[0]


def test_out_of_range_value_fails():
    bad = Observation("10001", "owner_occupier_share", Period.year(2021), 1.4, "fake", "SAL")
    r = check(NormaliseResult([bad], 1, 1), None, 0.25)
    assert not r.passed and "owner_occupier_share" in r.failures[0]


def test_no_tolerance_skips_row_count():
    assert check(NormaliseResult(obs(10), 10, 10), previous_rows=100, tolerance=None).passed


def test_zero_observations_fail():
    r = check(NormaliseResult([], 0, 0), None, 0.25)
    assert not r.passed and "no observations" in r.failures[0]
