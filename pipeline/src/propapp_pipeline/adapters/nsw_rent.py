import io
import re

import pandas as pd

from propapp_pipeline.adapters.base import Adapter, NormaliseResult, register
from propapp_pipeline.adapters.common import fetch_configured
from propapp_pipeline.geo.allocate import allocate
from propapp_pipeline.models import GeoValue, Period
from propapp_pipeline.parsing import SourceLayoutError, find_header_row, parse_number

RENT_METRICS = {"total": "median_weekly_rent_all_q", "house": "median_weekly_rent_house_q",
                "flat/unit": "median_weekly_rent_unit_q"}
QUARTERS = {"mar": 1, "jun": 2, "sep": 3, "dec": 4}
TITLE = re.compile(r"\b(mar|jun|sep|dec)[a-z]*\s+(?:quarter|qtr)?\s*(\d{4})", re.IGNORECASE)


def quarter_from_title(text: str) -> Period | None:
    m = TITLE.search(text)
    return Period.quarter(int(m.group(2)), QUARTERS[m.group(1).lower()]) if m else None


def _column(columns: list[str], *needles: str) -> str:
    for c in columns:
        if all(n in c.lower() for n in needles):
            return c
    raise SourceLayoutError(f"nsw_rent: no column containing {' '.join(needles)!r}")


@register
class NswRentAdapter(Adapter):
    """NSW Rent and Sales Report rent tables (new bonds by postcode, one quarter per file)."""

    source_id = "nsw_rent"

    def fetch(self, http, config):
        return fetch_configured(http, config)

    def parse(self, raw):
        sheets = pd.read_excel(io.BytesIO(raw[0].content), sheet_name=None, header=None,
                               dtype=object)
        sheet = next((df for name, df in sheets.items() if name.strip().lower() == "postcode"),
                     None)
        if sheet is None:
            raise SourceLayoutError(f"{self.source_id}: no 'Postcode' sheet")
        h = find_header_row(sheet, "Postcode")
        title = " ".join(str(c) for c in sheet.iloc[:h].to_numpy().ravel() if pd.notna(c))
        period = quarter_from_title(title) or quarter_from_title(raw[0].filename)
        if period is None:
            raise SourceLayoutError(f"{self.source_id}: cannot find the quarter in {title!r}")
        df = sheet.iloc[h + 1:].copy()
        df.columns = [str(c).strip() for c in sheet.iloc[h]]
        columns = list(df.columns)
        dwelling = _column(columns, "dwelling")
        bedrooms = _column(columns, "bedroom")
        median = _column(columns, "median")
        bonds = _column(columns, "new bonds lodged")

        values = []
        for r in df.to_dict("records"):
            if pd.isna(r["Postcode"]) or str(r[bedrooms]).strip().lower() != "total":
                continue
            postcode = str(r["Postcode"]).split(".")[0].strip().zfill(4)
            kind = str(r[dwelling]).strip().lower()
            if kind not in RENT_METRICS:
                continue
            rent = parse_number(r[median])
            if rent is not None:
                values.append(GeoValue("POA", postcode, RENT_METRICS[kind], period, rent))
            lodged = parse_number(r[bonds])
            if kind == "total" and lodged is not None:
                values.append(GeoValue("POA", postcode, "bonds_lodged_q", period, lodged))
        return values

    def normalise(self, rows, ctx):
        result = allocate(rows, ctx.index, self.source_id)
        return NormaliseResult(result.observations, result.matched, result.total)
