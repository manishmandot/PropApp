import math
from collections.abc import Iterable

import pandas as pd

SUPPRESSED = {"s", "-", "np", "n.a.", "na", "..", ""}


class SourceLayoutError(Exception):
    """A source file or page no longer has the layout the parser expects."""


def parse_number(cell: object) -> float | None:
    """Parse a numeric cell; suppressed or blank cells become None, never 0."""
    if cell is None:
        return None
    if isinstance(cell, int | float):
        return None if isinstance(cell, float) and math.isnan(cell) else float(cell)
    text = str(cell).strip()
    if text.lower() in SUPPRESSED:
        return None
    return float(text.replace("$", "").replace(",", "").replace("%", ""))


def require_columns(df: pd.DataFrame, cols: Iterable[str], source: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SourceLayoutError(f"{source}: missing columns {missing}")


def find_header_row(raw: pd.DataFrame, must_contain: str) -> int:
    """Index of the first row with a cell equal to `must_contain` (case/space-insensitive)."""
    target = must_contain.strip().lower()
    for i, row in enumerate(raw.itertuples(index=False)):
        if any(isinstance(c, str) and c.strip().lower() == target for c in row):
            return i
    raise SourceLayoutError(f"no header row containing {must_contain!r}")
