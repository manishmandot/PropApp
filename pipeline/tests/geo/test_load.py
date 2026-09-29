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
