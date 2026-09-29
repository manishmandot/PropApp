import pytest

from propapp_pipeline.db import connect
from propapp_pipeline.geo.load import build_correspondences, load_suburbs


def correspondences(db_url, geography, code):
    with connect(db_url) as conn:
        rows = conn.execute(
            "select sal_code, ratio from data.geo_correspondences "
            "where from_geography = %s and from_code = %s", (geography, code)).fetchall()
    return dict(rows)


@pytest.fixture
def loaded(db_url, sal_file, mb_frames):
    with connect(db_url) as conn:
        load_suburbs(conn, sal_file)
        build_correspondences(conn, *mb_frames)
    return db_url


def test_load_suburbs_skips_null_geometry(db_url, sal_file):
    with connect(db_url) as conn:
        assert load_suburbs(conn, sal_file) == 3
        row = conn.execute(
            "select name, state, extensions.st_srid(geom), extensions.geometrytype(geom) "
            "from data.suburbs where sal_code = '10001'").fetchone()
    assert row == ("Alpha", "NSW", 4326, "MULTIPOLYGON")


def test_ratio_is_population_weighted(loaded):
    rows = correspondences(loaded, "SA2", "101")
    assert rows == {"10001": pytest.approx(0.75), "10002": pytest.approx(0.25)}


def test_zero_population_falls_back_to_area(loaded):
    rows = correspondences(loaded, "SA2", "102")
    assert rows == {"10002": pytest.approx(0.25), "10003": pytest.approx(0.75)}


def test_postcode_correspondences_built(loaded):
    assert correspondences(loaded, "POA", "2000") == {
        "10001": pytest.approx(0.75), "10002": pytest.approx(0.25)}


def test_rebuild_replaces_rows(loaded, mb_frames):
    with connect(loaded) as conn:
        build_correspondences(conn, *mb_frames)
        n = conn.execute("select count(*) from data.geo_correspondences").fetchone()[0]
    assert n == 8


def test_read_abs_table_concatenates_sheets(tmp_path):
    import io

    import pandas as pd

    from propapp_pipeline.geo.load import read_abs_table

    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as xl:
        pd.DataFrame([["Mesh Block Counts, 2021", None], [None, None],
                      ["MB_CODE_2021", "Person"], ["1", 300]]).to_excel(
            xl, sheet_name="Table 1", header=False, index=False)
        pd.DataFrame([["MB_CODE_2021", "Person"], ["2", 100]]).to_excel(
            xl, sheet_name="Table 2", header=False, index=False)
        pd.DataFrame([["Explanatory notes"]]).to_excel(
            xl, sheet_name="Notes", header=False, index=False)
    df = read_abs_table(buf.getvalue(), "counts.xlsx", "MB_CODE_2021")
    assert df["MB_CODE_2021"].tolist() == ["1", "2"]
    assert df["Person"].tolist() == [300, 100]


def test_read_abs_table_csv_in_zip():
    import io
    import zipfile

    from propapp_pipeline.geo.load import read_abs_table

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("SAL_2021_AUST.csv", "MB_CODE_2021,SAL_CODE_2021\n10000010000,10001\n")
    df = read_abs_table(buf.getvalue(), "SAL_2021_AUST.zip", "MB_CODE_2021")
    assert df.to_dict("records") == [{"MB_CODE_2021": "10000010000", "SAL_CODE_2021": "10001"}]
