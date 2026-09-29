"""Shared support for ABS Data API (SDMX-CSV) sources reported by SA2."""
import io
from typing import ClassVar

import pandas as pd

from propapp_pipeline.adapters.base import Adapter, NormaliseResult
from propapp_pipeline.geo.allocate import allocate
from propapp_pipeline.http import download
from propapp_pipeline.models import GeoValue, Period
from propapp_pipeline.parsing import parse_number, require_columns
from propapp_pipeline.raw_store import RawFile

SDMX_CSV = "application/vnd.sdmx.data+csv"


def read_sdmx_csv(content: bytes, required: list[str]) -> pd.DataFrame:
    """Read SDMX-CSV; `code: label` cells are reduced to their codes."""
    df = pd.read_csv(io.BytesIO(content), dtype=str)
    require_columns(df, ["TIME_PERIOD", "OBS_VALUE", *required], "ABS Data API")
    for column in df.columns:
        if column != "OBS_VALUE":
            df[column] = df[column].str.split(":", n=1).str[0].str.strip()
    return df


class AbsSdmxAdapter(Adapter):
    """An SA2-level ABS Data API series allocated to suburbs.

    Config: `url` (full data query), `region_column` (the dataflow's region dimension)
    and `filters` ({dimension: code}) applied on top of the query.
    """

    metric: ClassVar[str]
    config: dict

    def fetch(self, http, config):
        self.config = config
        content = download(http, config["url"], headers={"accept": SDMX_CSV})
        return [RawFile(f"{self.source_id}.csv", content)]

    def period(self, time_period: str) -> Period:
        raise NotImplementedError

    def parse(self, raw):
        region = self.config["region_column"]
        filters = self.config.get("filters", {})
        df = read_sdmx_csv(raw[0].content, [region, *filters])
        for dimension, code in filters.items():
            df = df[df[dimension] == str(code)]
        values = []
        for row in df.to_dict("records"):
            value = parse_number(row["OBS_VALUE"])
            if value is not None:
                values.append(GeoValue("SA2", row[region], self.metric,
                                       self.period(row["TIME_PERIOD"]), value))
        return values

    def normalise(self, rows, ctx):
        result = allocate(rows, ctx.index, self.source_id)
        return NormaliseResult(result.observations, result.matched, result.total)
