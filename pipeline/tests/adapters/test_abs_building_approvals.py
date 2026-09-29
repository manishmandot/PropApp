from propapp_pipeline.adapters.abs_building_approvals import AbsBuildingApprovalsAdapter
from propapp_pipeline.models import Period
from propapp_pipeline.raw_store import RawFile

from .conftest import by, make_ctx

CSV = (b"DATAFLOW,MEASURE,SECTOR,BUILDING_TYPE,REGION_TYPE,REGION,TSEST,FREQ,TIME_PERIOD,"
       b"OBS_VALUE\n"
       b"ABS:BA_SA2(1.0.0),1,9,100,SA2,101,10,M,2025-03,40\n"
       b"ABS:BA_SA2(1.0.0),2,9,100,SA2,101,10,M,2025-03,99999\n")
CONFIG = {"region_column": "REGION", "filters": {"MEASURE": "1", "REGION_TYPE": "SA2"}}


def test_monthly_period_parsed():
    adapter = AbsBuildingApprovalsAdapter()
    adapter.config = CONFIG
    res = adapter.normalise(adapter.parse([RawFile("ba.csv", CSV)]),
                            make_ctx([("SA2", "101", "10001", 1, 1.0)]))
    obs = by(res, "10001", "building_approvals_dwellings")
    assert obs.period == Period.month(2025, 3) and obs.value == 40
    assert len(res.observations) == 1
