import pytest

from propapp_pipeline.adapters.abs_erp import AbsErpAdapter
from propapp_pipeline.adapters.abs_sdmx import read_sdmx_csv
from propapp_pipeline.models import Period
from propapp_pipeline.parsing import SourceLayoutError
from propapp_pipeline.raw_store import RawFile

from .conftest import by, make_ctx

CSV = (b"DATAFLOW,MEASURE,REGION_TYPE,ASGS_2021,FREQ,TIME_PERIOD,OBS_VALUE\n"
       b"ABS:ABS_ANNUAL_ERP_ASGS2021(1.0.0),ERP,SA2,101,A,2023,980\n"
       b"ABS:ABS_ANNUAL_ERP_ASGS2021(1.0.0),ERP,SA2,101,A,2024,1000\n"
       b"ABS:ABS_ANNUAL_ERP_ASGS2021(1.0.0),ERP,SA3,10101,A,2024,50000\n")
CONFIG = {"region_column": "ASGS_2021", "filters": {"MEASURE": "ERP", "REGION_TYPE": "SA2"}}
CORR = [("SA2", "101", "10001", 300, 0.75), ("SA2", "101", "10002", 100, 0.25)]


def run(csv=CSV):
    adapter = AbsErpAdapter()
    adapter.config = CONFIG
    return adapter.normalise(adapter.parse([RawFile("erp.csv", csv)]), make_ctx(CORR))


def test_erp_allocated_additively():
    res = run()
    assert by(res, "10001", "population", Period.year(2024)).value == 750
    assert by(res, "10002", "population", Period.year(2024)).value == 250
    assert (res.matched, res.total) == (2, 2)
    assert {o.period for o in res.observations} == {Period.year(2023), Period.year(2024)}


def test_code_label_cells_reduced_to_codes():
    df = read_sdmx_csv(b"REGION_TYPE,ASGS_2021,TIME_PERIOD,OBS_VALUE\n"
                       b"SA2: Statistical Area Level 2,101: Alpha,2024,5\n",
                       ["ASGS_2021"])
    assert df.iloc[0]["REGION_TYPE"] == "SA2" and df.iloc[0]["ASGS_2021"] == "101"


def test_missing_region_column_raises():
    with pytest.raises(SourceLayoutError, match="ASGS_2021"):
        run(CSV.replace(b"ASGS_2021", b"REGION"))
