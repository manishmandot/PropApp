"""Observations as a pandas frame, with point-in-time views (spec §5.5)."""
from datetime import date, timedelta

import pandas as pd
import psycopg

COLUMNS = ["suburb_code", "metric", "period_start", "granularity", "period_end", "value",
           "source"]
KEY = ["suburb_code", "metric", "period_start"]
MONTHS_IN = {"month": 1, "quarter": 3, "year": 12}


def add_months(d: date, months: int) -> date:
    index = d.year * 12 + d.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def period_end(start: date, granularity: str) -> date:
    return add_months(start, MONTHS_IN[granularity]) - timedelta(days=1)


def load_observations(conn: psycopg.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """
        select suburb_code, metric, period_start, period_granularity,
               (period_start + case period_granularity
                   when 'month' then interval '1 month'
                   when 'quarter' then interval '3 months'
                   else interval '1 year' end - interval '1 day')::date,
               value, source
        from data.observations
        """
    ).fetchall()
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["period_start"] = pd.to_datetime(df["period_start"])
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["value"] = df["value"].astype(float)
    return df


def load_suburb_states(conn: psycopg.Connection) -> pd.Series:
    rows = conn.execute("select sal_code, state from data.suburbs").fetchall()
    return pd.Series(dict(rows), name="state", dtype=object)


def as_of_view(obs: pd.DataFrame, as_of: date, census_fixed: bool = False) -> pd.DataFrame:
    """Observations usable at `as_of`: periods ending on or before it.

    `census_fixed` (backtest only) also admits every abs_census row, since the 2021 Census
    is the only one loaded. Where two sources report the same suburb, metric and period,
    the alphabetically first source is kept so results are deterministic.
    """
    usable = obs["period_end"] <= pd.Timestamp(as_of)
    if census_fixed:
        usable |= obs["source"] == "abs_census"
    view = obs[usable].sort_values([*KEY, "source"])
    return view.drop_duplicates(KEY, keep="first")


def latest(view: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Each suburb's latest period of `metric`: frame indexed by suburb, period_start/value."""
    rows = view[view["metric"] == metric].sort_values("period_start")
    last = rows.drop_duplicates("suburb_code", keep="last")
    return last.set_index("suburb_code")[["period_start", "value"]]


def series(view: pd.DataFrame, metric: str) -> pd.Series:
    """All values of `metric`, indexed by (suburb_code, period_start)."""
    rows = view[view["metric"] == metric]
    return rows.set_index(["suburb_code", "period_start"])["value"]


def value_at(view: pd.DataFrame, metric: str, period_start: pd.Series) -> pd.Series:
    """Value of `metric` at each suburb's given period start (NaN where missing)."""
    values = series(view, metric)
    keys = pd.MultiIndex.from_arrays([period_start.index, period_start.values])
    return pd.Series(values.reindex(keys).to_numpy(), index=period_start.index, dtype=float)
