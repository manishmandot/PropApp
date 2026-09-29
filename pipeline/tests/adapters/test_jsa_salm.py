from datetime import datetime

import pytest

from propapp_pipeline.adapters.jsa_salm import JsaSalmAdapter, quarter_of
from propapp_pipeline.models import Period
from propapp_pipeline.parsing import SourceLayoutError
from propapp_pipeline.raw_store import RawFile

from .conftest import by, make_ctx, xlsx_bytes

HEADER = ["Statistical Area Level 2 (SA2) (2021 ASGS)", "SA2 Code (2021 ASGS)", "Sep-24",
          "Dec-24"]


def sheet(title, rows):
    return [[title], [None], HEADER, *rows]


def workbook(unemployed_rows=None):
    return [RawFile("salm.xlsx", xlsx_bytes({
        "Smoothed SA2 unemployment rate": sheet("Unemployment rate (%)",
                                                [["Alpha", "101", 5.0, 4.0]]),
        "Smoothed SA2 unemployment": sheet("Unemployment (persons)", unemployed_rows or [
            ["Alpha", "101", 40, 32], ["Beta", "102", "-", 10]]),
        "Smoothed SA2 labour force": sheet("Labour force (persons)", [
            ["Alpha", "101", 800, 800], ["Beta", "102", 200, 200]]),
    }))]


def test_quarter_label_parsing():
    assert quarter_of("Dec-24") == Period.quarter(2024, 4)
    assert quarter_of("Mar-11") == Period.quarter(2011, 1)
    assert quarter_of(datetime(2024, 9, 1)) == Period.quarter(2024, 3)
    assert quarter_of("SA2 Code (2021 ASGS)") is None


def test_suppressed_cells_skipped():
    adapter = JsaSalmAdapter()
    rows = adapter.parse(workbook())
    beta = [r for r in rows if r.code == "102" and r.metric == "unemployed_count"]
    assert [r.period for r in beta] == [Period.quarter(2024, 4)]
    assert len(rows) == 7


def test_counts_allocated():
    adapter = JsaSalmAdapter()
    res = adapter.normalise(adapter.parse(workbook()),
                            make_ctx([("SA2", "101", "10001", 1, 1.0),
                                      ("SA2", "102", "10002", 1, 1.0)]))
    assert by(res, "10001", "unemployed_count", Period.quarter(2024, 4)).value == 32
    assert by(res, "10002", "labour_force_count", Period.quarter(2024, 3)).value == 200


def test_missing_sheet_raises():
    raw = [RawFile("salm.xlsx", xlsx_bytes({"Other": [["x"]]}))]
    with pytest.raises(SourceLayoutError, match="unemployment"):
        JsaSalmAdapter().parse(raw)
