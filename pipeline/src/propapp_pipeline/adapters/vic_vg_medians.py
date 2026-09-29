import io
import re

import pandas as pd

from propapp_pipeline.adapters.base import Adapter, NormaliseResult, register
from propapp_pipeline.adapters.common import fetch_configured
from propapp_pipeline.models import Observation, Period
from propapp_pipeline.parsing import SourceLayoutError, find_header_row, parse_number

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTH = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b",
    re.IGNORECASE,
)
YEAR = re.compile(r"\b(\d{4})\b")
KINDS = ("house", "unit")


def quarter_label(label: object) -> Period | None:
    """`Jul - Sep 2025` / `Sep Qtr 2025` → the month the quarter ends in (Period.month)."""
    text = str(label)
    months, year = MONTH.findall(text), YEAR.search(text)
    if not months or not year:
        return None
    month = MONTHS[months[-1][:3].lower()]
    if month % 3:
        return None
    return Period.month(int(year.group(1)), month)


def _column(columns: list[str], source: str, *needles: str) -> str:
    for c in columns:
        low = c.lower()
        if all(any(n in low for n in needle.split("|")) for needle in needles):
            return c
    raise SourceLayoutError(f"{source}: no column matching {needles}")


@register
class VicVgMediansAdapter(Adapter):
    """Victorian Valuer-General quarterly median prices by suburb (houses and units).

    The spec's thin-market rule needs sales counts, so a file without a 12-month sales
    count column fails the run rather than loading medians alone.
    """

    source_id = "vic_vg_medians"

    def fetch(self, http, config):
        files = []
        for kind in KINDS:
            [f] = fetch_configured(http, {"page_url": config["page_url"],
                                          "link_pattern": config[f"{kind}_link_pattern"]})
            files.append(type(f)(f"{kind}-{f.filename}", f.content))
        return files

    def parse(self, raw):
        rows = []
        for f in raw:
            kind = f.filename.split("-", 1)[0]
            if kind not in KINDS:
                raise SourceLayoutError(f"{self.source_id}: unexpected file {f.filename}")
            rows.extend(self._file(f.content, kind))
        return rows

    def _file(self, content: bytes, kind: str) -> list[dict]:
        sheet = next(iter(pd.read_excel(io.BytesIO(content), sheet_name=None, header=None,
                                        dtype=object).values()))
        h = find_header_row(sheet, "Suburb")
        df = sheet.iloc[h + 1:].copy()
        df.columns = [str(c).strip() for c in sheet.iloc[h]]
        columns = list(df.columns)
        median_12m = _column(columns, self.source_id, "12 month|annual|year", "median")
        count_12m = _column(columns, self.source_id, "sales", "12 month|annual|year")
        quarters = {c: p for c in columns
                    if c not in (median_12m, count_12m) and (p := quarter_label(c))}
        if not quarters:
            raise SourceLayoutError(f"{self.source_id}: no quarter median columns")
        newest = max(p.start for p in quarters.values())
        latest_columns = [c for c, p in quarters.items() if p.start == newest]
        if len(latest_columns) > 1:
            raise SourceLayoutError(
                f"{self.source_id}: several columns for the latest quarter: {latest_columns}")
        latest = latest_columns[0]
        return [
            {"kind": kind, "suburb": str(r["Suburb"]).strip(), "period": quarters[latest],
             "median_3m": parse_number(r[latest]), "median_12m": parse_number(r[median_12m]),
             "count_12m": parse_number(r[count_12m])}
            for r in df.to_dict("records") if pd.notna(r["Suburb"])
        ]

    def normalise(self, rows, ctx):
        observations, matched = [], 0
        for r in rows:
            sal = ctx.matcher.match(r["suburb"], "VIC")
            if not sal:
                continue
            matched += 1
            k = r["kind"]
            for metric, value in ((f"median_sale_price_{k}_3m", r["median_3m"]),
                                  (f"median_sale_price_{k}_12m", r["median_12m"]),
                                  (f"sales_count_{k}_12m", r["count_12m"])):
                if value is not None:
                    observations.append(
                        Observation(sal, metric, r["period"], value, self.source_id, "SAL"))
        return NormaliseResult(observations, matched, len(rows))
