import io

import pandas as pd

from propapp_pipeline.adapters.base import Adapter, NormaliseResult, register
from propapp_pipeline.adapters.common import fetch_configured
from propapp_pipeline.adapters.vic_vg_medians import quarter_label
from propapp_pipeline.models import Observation, Period
from propapp_pipeline.parsing import SourceLayoutError, find_header_row, parse_number

SHEET = "all properties"
METRIC = "median_weekly_rent_all_q"


@register
class VicDffhRentalAdapter(Adapter):
    """Victorian DFFH Rental Report: moving annual median rents by suburb group.

    Each matched member suburb of a group receives the group's value.
    """

    source_id = "vic_dffh_rental"

    def fetch(self, http, config):
        return fetch_configured(http, config)

    def parse(self, raw):
        sheets = pd.read_excel(io.BytesIO(raw[0].content), sheet_name=None, header=None,
                               dtype=object)
        sheet = next((df for name, df in sheets.items() if name.strip().lower() == SHEET), None)
        if sheet is None:
            raise SourceLayoutError(f"{self.source_id}: no 'All properties' sheet")
        h = find_header_row(sheet, "Median")
        if h == 0:
            raise SourceLayoutError(f"{self.source_id}: no quarter label row above the header")
        labels = sheet.iloc[h - 1].ffill()
        medians: dict[int, Period] = {}
        for i, cell in enumerate(sheet.iloc[h]):
            if isinstance(cell, str) and cell.strip().lower() == "median":
                month = quarter_label(labels.iloc[i])
                if month is None:
                    raise SourceLayoutError(f"{self.source_id}: bad quarter label "
                                            f"{labels.iloc[i]!r}")
                medians[i] = Period.quarter(month.start.year, month.start.month // 3)
        group_col = min(medians) - 2
        rows = []
        for r in sheet.iloc[h + 1:].itertuples(index=False):
            group = r[group_col]
            if not isinstance(group, str) or not group.strip():
                continue
            values = {p: v for i, p in medians.items() if (v := parse_number(r[i])) is not None}
            rows.append({"members": [m.strip() for m in group.split("-") if m.strip()],
                         "values": values})
        return rows

    def normalise(self, rows, ctx):
        observations, matched, total = [], 0, 0
        for r in rows:
            for name in r["members"]:
                total += 1
                sal = ctx.matcher.match(name, "VIC")
                if not sal:
                    continue
                matched += 1
                observations.extend(
                    Observation(sal, METRIC, period, value, self.source_id, "DFFH_GROUP")
                    for period, value in r["values"].items())
        return NormaliseResult(observations, matched, total)
