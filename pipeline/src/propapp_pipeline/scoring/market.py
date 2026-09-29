"""Market factors and market-layer eligibility (spec §5.1–5.2)."""
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from propapp_pipeline.scoring.factors import MARKET
from propapp_pipeline.scoring.observations import value_at
from propapp_pipeline.scoring.weights import Weights

TYPES = ("house", "unit")


@dataclass
class MarketResult:
    values: pd.DataFrame  # eligible suburbs × market factors
    eligible: pd.Index
    dwelling_type: pd.Series  # "house" | "unit", eligible suburbs
    reference_month: pd.Series  # L per eligible suburb


def _months_back(starts: pd.Series, months: int) -> pd.Series:
    return starts - pd.DateOffset(months=months)


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator / denominator.where(denominator > 0)


def _reference_month(view: pd.DataFrame, limit: pd.Timestamp) -> pd.Series:
    """L: each suburb's latest month with a 12-month sales count, no later than `limit`."""
    counts = view[view["metric"].isin([f"sales_count_{t}_12m" for t in TYPES])
                  & (view["period_start"] <= limit)]
    return counts.groupby("suburb_code")["period_start"].max()


def _total_sales(view: pd.DataFrame, starts: pd.Series) -> pd.Series:
    return sum(value_at(view, f"sales_count_{t}_12m", starts).fillna(0) for t in TYPES)


def _pick(by_type: dict[str, pd.Series], dwelling: pd.Series) -> pd.Series:
    return by_type["house"].where(dwelling == "house", by_type["unit"])


def _rent(view: pd.DataFrame, dwelling: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Latest rent for the dominant type (else all dwellings), and its value a year earlier."""
    rows = view[view["metric"].str.startswith("median_weekly_rent_")]
    rows = rows[rows["suburb_code"].isin(dwelling.index)]
    wanted = "median_weekly_rent_" + dwelling + "_q"
    has_typed = rows.merge(wanted.rename("metric").reset_index(), on=["suburb_code", "metric"])
    metric = wanted.where(wanted.index.isin(has_typed["suburb_code"]), "median_weekly_rent_all_q")
    chosen = rows.merge(metric.rename("metric").reset_index(), on=["suburb_code", "metric"])
    last = chosen.sort_values("period_start").drop_duplicates("suburb_code", keep="last")
    last = last.set_index("suburb_code")
    keys = pd.MultiIndex.from_arrays([
        last.index, last["metric"], last["period_start"] - pd.DateOffset(years=1)])
    earlier = chosen.set_index(["suburb_code", "metric", "period_start"])["value"]
    base = pd.Series(earlier.reindex(keys).to_numpy(), index=last.index)
    return last["value"].reindex(dwelling.index), base.reindex(dwelling.index)


def compute_market(view: pd.DataFrame, as_of: date, weights: Weights) -> MarketResult:
    as_of_month = pd.Timestamp(as_of).to_period("M").to_timestamp()
    limit = as_of_month - pd.DateOffset(months=weights.market_lag_months)
    oldest = as_of_month - pd.DateOffset(months=weights.market_max_age_months)

    ref = _reference_month(view, limit)
    by_type = {t: value_at(view, f"sales_count_{t}_12m", ref).fillna(0) for t in TYPES}
    total = by_type["house"] + by_type["unit"]
    eligible_mask = (total >= weights.thin_market_min_sales) & (ref >= oldest)
    ref = ref[eligible_mask]
    eligible = ref.index
    dwelling = pd.Series(np.where(by_type["house"][eligible] >= by_type["unit"][eligible],
                                  "house", "unit"), index=eligible, dtype=object)

    def median(kind: str, months_back: int) -> pd.Series:
        starts = _months_back(ref, months_back)
        return _pick({t: value_at(view, f"median_sale_price_{t}_{kind}", starts) for t in TYPES},
                     dwelling)

    growth_12m = _ratio(median("12m", 0), median("12m", 12)) - 1
    momentum = _ratio(median("3m", 0), median("3m", 3)) ** 4 - 1 - growth_12m
    rent, rent_base = _rent(view, dwelling)
    values = pd.DataFrame({
        "price_growth_12m": growth_12m,
        "momentum": momentum,
        "gross_yield": _ratio(rent * 52, median("12m", 0)),
        "rent_growth_12m": _ratio(rent, rent_base) - 1,
        "sales_volume_change": _ratio(total[eligible],
                                      _total_sales(view, _months_back(ref, 12))) - 1,
    }, index=eligible).reindex(columns=MARKET).astype(float)
    values.index.name = "suburb_code"
    return MarketResult(values.replace([np.inf, -np.inf], np.nan), eligible, dwelling, ref)
