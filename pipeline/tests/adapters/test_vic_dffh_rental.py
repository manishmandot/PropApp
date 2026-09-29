import pytest

from propapp_pipeline.adapters.vic_dffh_rental import VicDffhRentalAdapter
from propapp_pipeline.models import Period
from propapp_pipeline.parsing import SourceLayoutError
from propapp_pipeline.raw_store import RawFile

from .conftest import by, make_ctx, xlsx_bytes

SUBURBS = [("20001", "Albert Park", "VIC"), ("20002", "Middle Park", "VIC"),
           ("20003", "West St Kilda", "VIC"), ("20010", "Carlton", "VIC")]


def workbook(sheet_name="All properties"):
    return [RawFile("moving-annual-rents-by-suburb.xlsx", xlsx_bytes({
        "1 bedroom flat": [["x"]],
        sheet_name: [
            [None, None, "Jun 2025", None, "Sep 2025", None],
            [None, None, "Count", "Median", "Count", "Median"],
            ["Inner Melbourne", "Albert Park-Middle Park-West St Kilda", 300, 620, 310, 630],
            [None, "Carlton-Nowhereville", 500, "-", 520, 540],
        ],
    }))]


def normalised():
    adapter = VicDffhRentalAdapter()
    return adapter.normalise(adapter.parse(workbook()), make_ctx(suburbs=SUBURBS))


def test_group_value_applied_to_each_member():
    res = normalised()
    sep = Period.quarter(2025, 3)
    values = {o.suburb_code: o.value for o in res.observations if o.period == sep
              and o.suburb_code in ("20001", "20002", "20003")}
    assert values == {"20001": 630, "20002": 630, "20003": 630}
    assert by(res, "20001", "median_weekly_rent_all_q", Period.quarter(2025, 2)).value == 620
    assert {o.source_geography for o in res.observations} == {"DFFH_GROUP"}


def test_unmatched_members_and_suppressed_cells():
    res = normalised()
    carlton = [o for o in res.observations if o.suburb_code == "20010"]
    assert [o.period for o in carlton] == [Period.quarter(2025, 3)]
    assert (res.matched, res.total) == (4, 5)


def test_missing_sheet_raises():
    with pytest.raises(SourceLayoutError, match="All properties"):
        VicDffhRentalAdapter().parse(workbook("Summary"))
