import pytest

from propapp_pipeline.adapters.abs_census import AbsCensusAdapter
from propapp_pipeline.models import Period
from propapp_pipeline.parsing import SourceLayoutError
from propapp_pipeline.raw_store import RawFile

from .conftest import by, make_ctx, zip_bytes

DIR = "2021 Census GCP Suburbs and Localities for AUS/"
G01 = b"SAL_CODE_2021,Tot_P_M,Tot_P_F,Tot_P_P\nSAL10001,500,520,1020\nSAL10002,0,0,0\n"
G02 = (b"SAL_CODE_2021,Median_age_persons,Median_mortgage_repay_monthly,"
       b"Median_tot_hhd_inc_weekly,Average_household_size\n"
       b"SAL10001,38,2100,1850,2.6\nSAL10002,0,0,0,0\n")
G37 = (b"SAL_CODE_2021,O_OR_Total,O_MTG_Total,R_Tot_Total,Total_Total\n"
       b"SAL10001,200,300,450,1000\nSAL10002,0,0,0,0\n")


def census_zip(g02=G02):
    return [RawFile("census.zip", zip_bytes({
        DIR + "2021Census_G01_AUST_SAL.csv": G01,
        DIR + "2021Census_G02_AUST_SAL.csv": g02,
        DIR + "2021Census_G37_AUST_SAL.csv": G37,
    }))]


def normalised(raw):
    adapter = AbsCensusAdapter()
    return adapter.normalise(adapter.parse(raw), make_ctx())


def test_owner_occupier_share():
    assert by(normalised(census_zip()), "10001", "owner_occupier_share").value == 0.5


def test_sal_prefix_stripped_and_values_mapped():
    res = normalised(census_zip())
    assert by(res, "10001", "population_census").value == 1020
    assert by(res, "10001", "median_household_income_weekly").value == 1850
    assert by(res, "10001", "avg_household_size").value == 2.6
    assert by(res, "10001", "dwellings_total").value == 1000
    assert {o.period for o in res.observations} == {Period.year(2021)}
    assert {o.source_geography for o in res.observations} == {"SAL"}


def test_empty_suburb_has_no_share_or_medians():
    metrics = {o.metric for o in normalised(census_zip()).observations
               if o.suburb_code == "10002"}
    assert metrics == {"population_census", "dwellings_total"}


def test_missing_column_raises():
    bad = G02.replace(b"Median_tot_hhd_inc_weekly", b"Median_income")
    with pytest.raises(SourceLayoutError, match="Median_tot_hhd_inc_weekly"):
        AbsCensusAdapter().parse(census_zip(bad))
