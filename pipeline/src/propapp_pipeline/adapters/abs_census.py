import io
import re

import pandas as pd

from propapp_pipeline.adapters.base import Adapter, NormaliseResult, register
from propapp_pipeline.adapters.common import fetch_configured, zip_members
from propapp_pipeline.geo.allocate import allocate
from propapp_pipeline.models import GeoValue, Period
from propapp_pipeline.parsing import SourceLayoutError, parse_number, require_columns

CENSUS = Period.year(2021)
CODE = "SAL_CODE_2021"
TABLES = {
    "G01": {"Tot_P_P": "population_census"},
    "G02": {
        "Median_age_persons": "median_age",
        "Median_tot_hhd_inc_weekly": "median_household_income_weekly",
        "Average_household_size": "avg_household_size",
    },
    "G37": {"Total_Total": "dwellings_total"},
}
TENURE = ["O_OR_Total", "O_MTG_Total", "Total_Total"]
MEDIANS = set(TABLES["G02"].values())
MIN_TENURE_DWELLINGS = 5


@register
class AbsCensusAdapter(Adapter):
    """ABS Census 2021 General Community Profile DataPack at SAL level."""

    source_id = "abs_census"

    def fetch(self, http, config):
        return fetch_configured(http, config)

    def _tables(self, content: bytes) -> dict[str, pd.DataFrame]:
        tables = {}
        for name, data in zip_members(content):
            m = re.search(r"2021Census_(G\d+)_AUST_SAL\.csv$", name)
            if m and m.group(1) in TABLES:
                tables[m.group(1)] = pd.read_csv(io.BytesIO(data), dtype=str)
        missing = set(TABLES) - set(tables)
        if missing:
            raise SourceLayoutError(f"{self.source_id}: DataPack lacks tables {sorted(missing)}")
        return tables

    def parse(self, raw):
        tables = self._tables(raw[0].content)
        values: list[GeoValue] = []
        for table, columns in TABLES.items():
            df = tables[table]
            extra = TENURE if table == "G37" else []
            require_columns(df, [CODE, *columns, *extra], self.source_id)
            for row in df.to_dict("records"):
                code = row[CODE].removeprefix("SAL")
                for column, metric in columns.items():
                    value = parse_number(row[column])
                    if value is not None:
                        values.append(GeoValue("SAL", code, metric, CENSUS, value))
                if table == "G37":
                    share = _owner_occupier_share(*(parse_number(row[c]) for c in TENURE))
                    if share is not None:
                        values.append(GeoValue("SAL", code, "owner_occupier_share", CENSUS,
                                               share))
        return _drop_medians_of_empty_suburbs(values)

    def normalise(self, rows, ctx):
        result = allocate(rows, ctx.index, self.source_id)
        return NormaliseResult(result.observations, result.matched, result.total)


def _owner_occupier_share(
    owned: float | None, mortgaged: float | None, total: float | None
) -> float | None:
    """Owned outright + mortgaged over all occupied dwellings.

    Skipped when a component is missing or the suburb has too few dwellings for Census
    perturbation to leave a meaningful ratio; capped at 1 because ABS perturbs totals and
    components independently. `Total_Total` includes "not stated", so the share is a
    slight understatement.
    """
    if owned is None or mortgaged is None or total is None or total < MIN_TENURE_DWELLINGS:
        return None
    return min((owned + mortgaged) / total, 1.0)


def _drop_medians_of_empty_suburbs(values: list[GeoValue]) -> list[GeoValue]:
    """The Census reports 0 for medians of unpopulated suburbs; those are not data."""
    empty = {v.code for v in values if v.metric == "population_census" and v.value == 0}
    return [v for v in values if not (v.code in empty and v.metric in MEDIANS)]
