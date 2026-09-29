import io
import re
from datetime import date, datetime

import pandas as pd

from propapp_pipeline.adapters.base import Adapter, NormaliseResult, register
from propapp_pipeline.adapters.common import fetch_configured
from propapp_pipeline.geo.allocate import allocate
from propapp_pipeline.models import GeoValue, Period
from propapp_pipeline.parsing import SourceLayoutError, parse_number

SHEETS = {"smoothed sa2 unemployment": "unemployed_count",
          "smoothed sa2 labour force": "labour_force_count"}
QUARTER_END_MONTHS = {"mar": 1, "jun": 2, "sep": 3, "dec": 4}
LABEL = re.compile(r"^(mar|jun|sep|dec)-(\d{2})$", re.IGNORECASE)


def quarter_of(label: object) -> Period | None:
    """`Dec-24` (or an Excel date in the quarter) → Period.quarter; None if not a quarter."""
    if isinstance(label, datetime | date):
        return Period.quarter(label.year, (label.month - 1) // 3 + 1)
    m = LABEL.match(str(label).strip())
    if not m:
        return None
    return Period.quarter(2000 + int(m.group(2)), QUARTER_END_MONTHS[m.group(1).lower()])


@register
class JsaSalmAdapter(Adapter):
    """Jobs and Skills Australia Small Area Labour Markets, smoothed SA2 (ASGS 2021)."""

    source_id = "jsa_salm"

    def fetch(self, http, config):
        return fetch_configured(http, config)

    def parse(self, raw):
        sheets = pd.read_excel(io.BytesIO(raw[0].content), sheet_name=None, header=None,
                               dtype=object)
        by_name = {name.strip().lower(): df for name, df in sheets.items()}
        values: list[GeoValue] = []
        for sheet_name, metric in SHEETS.items():
            if sheet_name not in by_name:
                raise SourceLayoutError(f"{self.source_id}: missing sheet {sheet_name!r}")
            values.extend(self._sheet(by_name[sheet_name], metric))
        return values

    def _sheet(self, df: pd.DataFrame, metric: str) -> list[GeoValue]:
        header_index, code_col = _code_header(df)
        periods = {i: quarter_of(c) for i, c in enumerate(df.iloc[header_index])}
        periods = {i: p for i, p in periods.items() if p is not None}
        if not periods:
            raise SourceLayoutError(f"{self.source_id}: no quarter columns in {metric} sheet")
        values = []
        for row in df.iloc[header_index + 1:].itertuples(index=False):
            code = row[code_col]
            if pd.isna(code):
                continue
            code = str(code).split(".")[0].strip()
            for i, period in periods.items():
                value = parse_number(row[i])
                if value is not None:
                    values.append(GeoValue("SA2", code, metric, period, value))
        return values

    def normalise(self, rows, ctx):
        result = allocate(rows, ctx.index, self.source_id)
        return NormaliseResult(result.observations, result.matched, result.total)


def _code_header(df: pd.DataFrame) -> tuple[int, int]:
    for r, row in enumerate(df.itertuples(index=False)):
        for c, cell in enumerate(row):
            if isinstance(cell, str) and cell.strip().lower().startswith("sa2 code"):
                return r, c
    raise SourceLayoutError("jsa_salm: no 'SA2 Code' header row")
