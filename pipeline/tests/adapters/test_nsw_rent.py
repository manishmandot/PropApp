import pytest

from propapp_pipeline.adapters.nsw_rent import NswRentAdapter, quarter_from_title
from propapp_pipeline.models import Period
from propapp_pipeline.parsing import SourceLayoutError
from propapp_pipeline.raw_store import RawFile

from .conftest import by, make_ctx, xlsx_bytes

HEADER = ["GMR", "GCCSA", "Postcode", "Dwelling Types", "Number of Bedrooms", "First QNt",
          "Median Weekly Rent for New Bonds $", "Third QNt", "New Bonds Lodged No.",
          "Total Bonds Held No."]
Q = Period.quarter(2025, 2)


def workbook(rows, header=HEADER):
    return [RawFile("rent-tables-jun-qtr-2025.xlsx", xlsx_bytes({
        "Postcode": [["Rent and Sales Report - Rent tables, June Quarter 2025"], [None],
                     header, *rows],
    }))]


def row(postcode, dwelling, median, bonds, bedrooms="Total"):
    return ["Sydney", "Greater Sydney", postcode, dwelling, bedrooms, 0, median, 0, bonds, 0]


CORR = [("POA", "2000", "10002", 100, 0.5), ("POA", "2000", "10009", 100, 0.5),
        ("POA", "2001", "10002", 300, 1.0)]


def normalised(rows):
    adapter = NswRentAdapter()
    return adapter.normalise(adapter.parse(workbook(rows)), make_ctx(CORR))


def test_quarter_from_title():
    assert quarter_from_title("Rent tables, June Quarter 2025") == Q
    assert quarter_from_title("Rent tables Dec Qtr 2024") == Period.quarter(2024, 4)
    assert quarter_from_title("Rent tables") is None


def test_suppressed_rent_skipped():
    rows = NswRentAdapter().parse(workbook([row(2000, "Total", "s", 12),
                                            row(2000, "Flat/Unit", "-", "-")]))
    assert [(r.metric, r.value) for r in rows] == [("bonds_lodged_q", 12)]


def test_rent_intensive_across_postcodes():
    res = normalised([row(2000, "Total", 500, 40), row(2001, "Total", 700, 60),
                      row(2000, "House", 650, 10, bedrooms="3"),
                      row(2000, "Townhouse", 900, 5)])
    assert by(res, "10002", "median_weekly_rent_all_q", Q).value == pytest.approx(650)
    assert by(res, "10009", "bonds_lodged_q", Q).value == pytest.approx(20)
    assert {o.metric for o in res.observations} == {"median_weekly_rent_all_q", "bonds_lodged_q"}


def test_house_and_unit_mapped():
    res = normalised([row(2001, "House", 720, 3), row(2001, "Flat/Unit", 610, 9)])
    assert by(res, "10002", "median_weekly_rent_house_q", Q).value == 720
    assert by(res, "10002", "median_weekly_rent_unit_q", Q).value == 610


def test_missing_median_column_raises():
    header = [h if "Median" not in h else "Rent" for h in HEADER]
    with pytest.raises(SourceLayoutError, match="median"):
        NswRentAdapter().parse(workbook([], header))
