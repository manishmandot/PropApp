from datetime import date

import pandas as pd
import pytest

from propapp_pipeline.db import connect
from propapp_pipeline.scoring.observations import (
    as_of_view,
    latest,
    load_observations,
    load_suburb_states,
    period_end,
    value_at,
)

from .helpers import frame, monthly, quarterly, yearly


@pytest.fixture
def obs_frame():
    return frame([
        monthly("10001", "median_sale_price_house_12m", 2025, 8, 900_000, "nsw_vg_sales"),
        monthly("10001", "median_sale_price_house_12m", 2025, 9, 910_000, "nsw_vg_sales"),
        quarterly("10001", "median_weekly_rent_all_q", 2025, 1, 580, "nsw_rent"),
        quarterly("10001", "median_weekly_rent_all_q", 2025, 2, 600, "nsw_rent"),
        quarterly("10001", "median_weekly_rent_all_q", 2025, 2, 650, "vic_dffh_rental"),
        yearly("10001", "median_household_income_weekly", 2021, 1850, "abs_census"),
    ])


def has_census(view):
    return (view.source == "abs_census").any()


def test_period_end():
    assert period_end(date(2025, 7, 1), "quarter") == date(2025, 9, 30)
    assert period_end(date(2024, 2, 1), "month") == date(2024, 2, 29)
    assert period_end(date(2021, 1, 1), "year") == date(2021, 12, 31)


def test_as_of_excludes_periods_ending_later(obs_frame):
    view = as_of_view(obs_frame, date(2025, 9, 29))
    sales = view[view.metric == "median_sale_price_house_12m"]
    assert sales.period_start.tolist() == [pd.Timestamp("2025-08-01")]


def test_latest_value_prefers_newest_then_source(obs_frame):
    view = as_of_view(obs_frame, date(2025, 12, 31))
    assert latest(view, "median_weekly_rent_all_q").loc["10001", "value"] == 600
    assert latest(view, "median_weekly_rent_all_q").loc["10001", "period_start"] == \
        pd.Timestamp("2025-04-01")


def test_value_at(obs_frame):
    view = as_of_view(obs_frame, date(2025, 12, 31))
    starts = pd.Series({"10001": pd.Timestamp("2025-01-01"), "10002": pd.Timestamp("2025-01-01")})
    values = value_at(view, "median_weekly_rent_all_q", starts)
    assert values["10001"] == 580 and pd.isna(values["10002"])


def test_census_fixed_view(obs_frame):
    assert not has_census(as_of_view(obs_frame, date(2018, 6, 30)))
    assert has_census(as_of_view(obs_frame, date(2018, 6, 30), census_fixed=True))


def test_load_observations_roundtrip(db_url):
    with connect(db_url) as conn:
        conn.execute("insert into data.suburbs (sal_code, name, state) values ('10001','A','NSW')")
        conn.execute("""
            insert into data.observations (suburb_code, metric, period_start,
                period_granularity, value, source, source_geography)
            values ('10001','population','2024-01-01','year',1000,'abs_erp','SA2'),
                   ('10001','median_weekly_rent_all_q','2025-04-01','quarter',600,'nsw_rent','POA')
        """)
        conn.commit()
        obs = load_observations(conn)
        states = load_suburb_states(conn)
    assert len(obs) == 2 and states["10001"] == "NSW"
    rent = obs[obs.metric == "median_weekly_rent_all_q"].iloc[0]
    assert rent.period_end == pd.Timestamp("2025-06-30") and rent.value == 600
