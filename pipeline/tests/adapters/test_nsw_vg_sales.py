from datetime import date

import pytest

from propapp_pipeline.adapters.nsw_vg_sales import NswVgSalesAdapter
from propapp_pipeline.db import connect
from propapp_pipeline.http import make_client
from propapp_pipeline.models import Period
from propapp_pipeline.parsing import SourceLayoutError
from propapp_pipeline.raw_store import RawFile

from .conftest import by, make_ctx, zip_bytes

CONFIG = {
    "weekly_url_template": "https://vg.test/weekly/{date:%Y%m%d}.zip",
    "yearly_url_template": "https://vg.test/yearly/{year}.zip",
}


def b_record(dealing, contract, price, *, locality="ALPHA", postcode="2000", nature="R",
             strata="", interest=""):
    fields = ["B", "001", f"P{dealing}", "1", "20260921 01:02", "", "", "12", "SMITH ST",
              locality, postcode, "600", "M", contract, "", str(price), "R2", nature,
              "RESIDENCE", strata, "", "", interest, f"D{dealing}"]
    return ";".join(fields)


def dat_zip(*records):
    body = "\n".join(["A;RTSALEDATA;001;20260921 01:02;VG", *records, "Z;3;1;0"]).encode()
    inner = zip_bytes({"001_SALES_DATA_NNME_21092026.DAT": body})
    return [RawFile("20260921.zip", zip_bytes({"20260921/001.zip": inner}))]


def test_filters_non_residential_and_partial_interest():
    sales = NswVgSalesAdapter().parse(dat_zip(
        b_record(1, "20260105", 900000),
        b_record(2, "20260105", 900000, nature="V"),
        b_record(3, "20260105", 900000, interest="50"),
        b_record(4, "20260105", 0),
        b_record(5, "", 900000),
        b_record(6, "20260105", 700000, interest="100"),
    ))
    assert [s.dealing_number for s in sales] == ["D1", "D6"]
    assert sales[0].contract_date == date(2026, 1, 5) and sales[0].price == 900000


def test_strata_is_unit():
    [sale] = NswVgSalesAdapter().parse(dat_zip(b_record(1, "20260105", 650000, strata="12")))
    assert sale.is_strata


def test_file_without_sales_raises():
    with pytest.raises(SourceLayoutError):
        NswVgSalesAdapter().parse(dat_zip())


@pytest.fixture
def conn(db_url):
    with connect(db_url, autocommit=True) as c:
        c.execute("insert into data.suburbs (sal_code, name, state) values "
                  "('10001', 'Alpha', 'NSW')")
        yield c


def normalise(conn, raw):
    adapter = NswVgSalesAdapter()
    ctx = make_ctx(suburbs=[("10001", "Alpha", "NSW")], conn=conn, today=date(2026, 9, 29))
    return adapter.normalise(adapter.parse(raw), ctx)


def test_rolling_12m_median_and_count(conn):
    res = normalise(conn, dat_zip(
        b_record(1, "20250715", 100000),
        b_record(2, "20251001", 200000),
        b_record(3, "20260110", 300000),
        b_record(4, "20260420", 400000),
        b_record(5, "20260605", 1000000),
        b_record(6, "20250630", 5000000),
    ))
    june = Period.month(2026, 6)
    assert by(res, "10001", "median_sale_price_house_12m", june).value == 300000
    assert by(res, "10001", "sales_count_house_12m", june).value == 5
    assert by(res, "10001", "median_sale_price_house_3m", june).value == 700000
    assert not [o for o in res.observations if o.period.start > date(2026, 9, 1)]
    assert {o.source_geography for o in res.observations} == {"SAL"}


def test_unmatched_sale_stored_with_null_sal(conn):
    res = normalise(conn, dat_zip(b_record(1, "20260105", 900000, locality="NOWHERE")))
    assert (res.matched, res.total, res.observations) == (0, 1, [])
    assert conn.execute("select sal_code, address from data.nsw_sales").fetchall() == [
        (None, "12 SMITH ST NOWHERE 2000")]


def test_weekly_fetch_skips_unpublished_newest(httpx_mock):
    httpx_mock.add_response(url="https://vg.test/weekly/20260928.zip", status_code=404)
    for day in ("20260921", "20260914", "20260907"):
        httpx_mock.add_response(url=f"https://vg.test/weekly/{day}.zip", content=b"z")
    files = NswVgSalesAdapter(as_of="2026-09-29").fetch(make_client(), CONFIG)
    assert [f.filename for f in files] == ["20260921.zip", "20260914.zip", "20260907.zip"]


def test_yearly_backfill_fetch(httpx_mock):
    for year in (2024, 2025):
        httpx_mock.add_response(url=f"https://vg.test/yearly/{year}.zip", content=b"z")
    files = NswVgSalesAdapter(years="2024-2025").fetch(make_client(), CONFIG)
    assert [f.filename for f in files] == ["2024.zip", "2025.zip"]
