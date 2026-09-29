"""Build observation frames for scoring tests."""
from datetime import date

import pandas as pd

from propapp_pipeline.scoring.observations import period_end


def frame(rows) -> pd.DataFrame:
    """rows: (suburb, metric, period_start: date, granularity, value[, source])."""
    records = []
    for row in rows:
        suburb, metric, start, granularity, value, *rest = row
        records.append({
            "suburb_code": suburb, "metric": metric, "period_start": pd.Timestamp(start),
            "granularity": granularity,
            "period_end": pd.Timestamp(period_end(start, granularity)),
            "value": float(value), "source": rest[0] if rest else "test",
        })
    return pd.DataFrame.from_records(records, columns=[
        "suburb_code", "metric", "period_start", "granularity", "period_end", "value",
        "source"])


def yearly(suburb, metric, year, value, source="test"):
    return (suburb, metric, date(year, 1, 1), "year", value, source)


def monthly(suburb, metric, year, month, value, source="test"):
    return (suburb, metric, date(year, month, 1), "month", value, source)


def quarterly(suburb, metric, year, quarter, value, source="test"):
    return (suburb, metric, date(year, 3 * quarter - 2, 1), "quarter", value, source)
