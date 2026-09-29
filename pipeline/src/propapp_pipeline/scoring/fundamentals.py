"""Fundamentals factors (spec §5.1): one raw value per suburb per factor."""
import numpy as np
import pandas as pd

from propapp_pipeline.scoring.factors import FUNDAMENTALS
from propapp_pipeline.scoring.observations import latest, value_at

MIN_APPROVAL_MONTHS = 10


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """numerator / denominator, NaN where the denominator is missing or ≤ 0."""
    return numerator / denominator.where(denominator > 0)


def _population_growth(view: pd.DataFrame) -> pd.Series:
    last = latest(view, "population")
    base = value_at(view, "population", last["period_start"] - pd.DateOffset(years=3))
    return _ratio(last["value"], base) ** (1 / 3) - 1


def _supply_pressure(view: pd.DataFrame) -> pd.Series:
    approvals = view[view["metric"] == "building_approvals_dwellings"]
    last = latest(view, "building_approvals_dwellings")["period_start"]
    window = approvals.join(last.rename("last"), on="suburb_code")
    window = window[window["period_start"] > window["last"] - pd.DateOffset(months=12)]
    totals = window.groupby("suburb_code")["value"].agg(["sum", "count"])
    annual = (totals["sum"] * 12 / totals["count"]).where(totals["count"] >= MIN_APPROVAL_MONTHS)
    dwellings = latest(view, "dwellings_total")["value"].reindex(annual.index)
    return _ratio(annual, dwellings) * 1000


def _unemployment(view: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    unemployed = latest(view, "unemployed_count")
    quarter = unemployed["period_start"]

    def rate_at(starts: pd.Series) -> pd.Series:
        count = value_at(view, "unemployed_count", starts)
        labour = value_at(view, "labour_force_count", starts)
        return _ratio(count, labour) * 100

    rate = rate_at(quarter)
    return rate, rate - rate_at(quarter - pd.DateOffset(years=1))


def compute_fundamentals(view: pd.DataFrame) -> pd.DataFrame:
    rate, change = _unemployment(view)
    columns = {
        "population_growth_3y": _population_growth(view),
        "supply_pressure": _supply_pressure(view),
        "median_household_income": latest(view, "median_household_income_weekly")["value"],
        "unemployment_rate": rate,
        "unemployment_change": change,
        "owner_occupier_share": latest(view, "owner_occupier_share")["value"],
    }
    result = pd.DataFrame(columns).reindex(columns=FUNDAMENTALS).astype(float)
    result.index.name = "suburb_code"
    return result.replace([np.inf, -np.inf], np.nan)
