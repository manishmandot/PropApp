import pytest

from propapp_pipeline.adapters.vic_vg_medians import VicVgMediansAdapter, quarter_label
from propapp_pipeline.models import Period
from propapp_pipeline.parsing import SourceLayoutError
from propapp_pipeline.raw_store import RawFile

from .conftest import by, make_ctx, xlsx_bytes

HEADER = ["Suburb", "Apr - Jun 2025", "Jul - Sep 2025", "12 Month Median",
          "No of Sales (12 months)", "Change %"]
SUBURBS = [("20001", "Albert Park", "VIC"), ("20002", "Middle Park", "VIC")]
SEP = Period.month(2025, 9)


def file(kind, rows, header=HEADER):
    sheet = [["Median house prices by suburb - September quarter 2025"], [None], header, *rows]
    return RawFile(f"{kind}-suburb.xlsx", xlsx_bytes({"Sheet1": sheet}))


def normalised(raw):
    adapter = VicVgMediansAdapter()
    return adapter.normalise(adapter.parse(raw), make_ctx(suburbs=SUBURBS))


def test_quarter_label():
    assert quarter_label("Jul - Sep 2025") == SEP
    assert quarter_label("Sep Qtr 2025") == SEP
    assert quarter_label("12 Month Median") is None


def test_vic_quarter_maps_to_last_month():
    res = normalised([file("house", [["ALBERT PARK", 2000000, 2100000, 2050000, 140, 2.0]]),
                      file("unit", [["ALBERT PARK", 800000, 810000, 790000, "s", 1.0]])])
    assert by(res, "20001", "median_sale_price_house_3m", SEP).value == 2100000
    assert by(res, "20001", "median_sale_price_house_12m", SEP).value == 2050000
    assert by(res, "20001", "sales_count_house_12m", SEP).value == 140
    assert by(res, "20001", "median_sale_price_unit_3m", SEP).value == 810000
    assert not [o for o in res.observations if o.metric == "sales_count_unit_12m"]


def test_unmatched_vic_suburb_counted():
    res = normalised([file("house", [["ALBERT PARK", 1, 2100000, 2050000, 140, 0],
                                     ["NOWHERE", 1, 900000, 900000, 30, 0]])])
    assert (res.matched, res.total) == (1, 2)


def test_missing_sales_count_column_raises():
    header = [h for h in HEADER if "Sales" not in h]
    with pytest.raises(SourceLayoutError, match="sales"):
        VicVgMediansAdapter().parse([file("house", [], header)])
