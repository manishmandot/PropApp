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


# Only the metrics the factors read; everything else stays in the database.
SCORING_METRICS = [
    "population", "building_approvals_dwellings", "dwellings_total",
    "median_household_income_weekly", "unemployed_count", "labour_force_count",
    "owner_occupier_share",
    *(f"sales_count_{t}_12m" for t in ("house", "unit")),
    *(f"median_sale_price_{t}_{w}" for t in ("house", "unit") for w in ("12m", "3m")),
    *(f"median_weekly_rent_{t}_q" for t in ("house", "unit", "all")),
]
CATEGORIES = ["suburb_code", "metric", "granularity", "source"]
CHUNK_ROWS = 250_000


def period_ends(starts: pd.Series, granularity: pd.Series) -> pd.Series:
    """Last day of each period (vectorised `period_end`)."""
    months = granularity.astype(str).map(MONTHS_IN).to_numpy()
    index = starts.dt.year.to_numpy() * 12 + starts.dt.month.to_numpy() - 1 + months
    following = pd.to_datetime({"year": index // 12, "month": index % 12 + 1, "day": 1})
    return pd.Series(following.to_numpy(), index=starts.index) - pd.Timedelta(days=1)


def load_observations(conn: psycopg.Connection) -> pd.DataFrame:
    """Scoring metrics as a compact frame (category columns), streamed in chunks."""
    chunks = []
    with conn.transaction(), conn.cursor(name="scoring_observations") as cur:
        cur.itersize = CHUNK_ROWS
        cur.execute(
            "select suburb_code, metric, period_start, period_granularity, value, source "
            "from data.observations where metric = any(%s)", (SCORING_METRICS,))
        while rows := cur.fetchmany(CHUNK_ROWS):
            chunk = pd.DataFrame(rows, columns=[c for c in COLUMNS if c != "period_end"])
            for column in CATEGORIES:
                chunk[column] = chunk[column].astype("category")
            chunks.append(chunk)
    if not chunks:
        return pd.DataFrame({c: pd.Series(dtype=object) for c in COLUMNS})
    df = pd.concat(chunks, ignore_index=True)
    for column in CATEGORIES:  # concat of differing categories falls back to object
        df[column] = df[column].astype("category")
    df["period_start"] = pd.to_datetime(df["period_start"])
    df["value"] = df["value"].astype(float)
    df["period_end"] = period_ends(df["period_start"], df["granularity"])
    return df[COLUMNS]


def load_suburb_states(conn: psycopg.Connection) -> pd.Series:
    rows = conn.execute("select sal_code, state from data.suburbs").fetchall()
    return pd.Series(dict(rows), name="state", dtype=object)


def as_of_view(obs: pd.DataFrame, as_of: date, census_fixed: bool = False,
               release_lags: dict[str, int] | None = None) -> pd.DataFrame:
    """Observations usable at `as_of`: periods ending on or before it.

    `census_fixed` (backtest only) also admits every abs_census row, since the 2021 Census
    is the only one loaded. Where two sources report the same suburb, metric and period,
    the alphabetically first source is kept so results are deterministic. `release_lags`
    (backtest only) delays each source's periods by its publication lag in months.
    """
    cutoff = pd.Series(pd.Timestamp(as_of), index=obs.index)
    for source, months in (release_lags or {}).items():
        cutoff = cutoff.mask(obs["source"] == source,
                             pd.Timestamp(as_of) - pd.DateOffset(months=months))
    usable = obs["period_end"] <= cutoff
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
