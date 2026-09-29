import json
import subprocess

import httpx
import pytest

from propapp_pipeline.db import connect
from propapp_pipeline.raw_store import SupabaseRawStore
from propapp_pipeline.tiles import build_pmtiles, export_geojson, score_band, upload_tiles

SQUARE = "MULTIPOLYGON(((151 -33, 151.01 -33, 151.01 -33.01, 151 -33.01, 151 -33)))"


def test_score_band_edges():
    assert [score_band(s) for s in (None, 0, 19.9, 20, 99.9, 100)] == [0, 1, 1, 2, 5, 5]


def test_export_geojson(db_url, tmp_path):
    with connect(db_url) as conn:
        conn.execute("insert into data.suburbs (sal_code, name, state, geom) values "
                     "('10001', 'Alpha', 'NSW', extensions.st_geomfromtext(%s, 4326)), "
                     "('10002', 'Beta', 'NSW', null)", (SQUARE,))
        conn.execute("refresh materialized view api.suburbs")
        conn.commit()
        path = tmp_path / "suburbs.geojsonl"
        assert export_geojson(conn, path) == 1
    feature = json.loads(path.read_text().splitlines()[0])
    assert feature["properties"] == {"code": "10001", "name": "Alpha", "state": "NSW",
                                     "slug": "10001-alpha-nsw", "band": 0}
    assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_build_pmtiles_command(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/tippecanoe")
    calls = []
    build_pmtiles(tmp_path / "in.geojsonl", tmp_path / "out.pmtiles",
                  run=lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0))
    argv = calls[0]
    assert argv[:3] == ["tippecanoe", "-o", str(tmp_path / "out.pmtiles")]
    assert "-l" in argv and argv[argv.index("-l") + 1] == "suburbs" and "--force" in argv


def test_missing_tippecanoe_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="tippecanoe"):
        build_pmtiles(tmp_path / "in.geojsonl", tmp_path / "out.pmtiles")


def test_upload_tiles(httpx_mock, tmp_path):
    base = "https://p.supabase.co/storage/v1"
    httpx_mock.add_response(method="GET", url=f"{base}/bucket/tiles", status_code=404)
    httpx_mock.add_response(method="POST", url=f"{base}/bucket")
    httpx_mock.add_response(method="POST", url=f"{base}/object/tiles/suburbs.pmtiles")
    path = tmp_path / "suburbs.pmtiles"
    path.write_bytes(b"PMTiles")
    url = upload_tiles(SupabaseRawStore("https://p.supabase.co", "k", httpx.Client()), path)
    assert url == f"{base}/object/public/tiles/suburbs.pmtiles"
    bucket = json.loads(httpx_mock.get_requests()[1].content)
    assert bucket["public"] is True


def test_upload_tiles_short_cache_and_size_limit(httpx_mock, tmp_path, monkeypatch):
    import propapp_pipeline.tiles as tiles

    base = "https://p.supabase.co/storage/v1"
    httpx_mock.add_response(method="GET", url=f"{base}/bucket/tiles")
    httpx_mock.add_response(method="POST", url=f"{base}/object/tiles/suburbs.pmtiles")
    path = tmp_path / "suburbs.pmtiles"
    path.write_bytes(b"x" * 10)
    upload_tiles(SupabaseRawStore("https://p.supabase.co", "k", httpx.Client()), path)
    assert httpx_mock.get_requests()[-1].headers["cache-control"] == "max-age=300"

    monkeypatch.setattr(tiles, "MAX_TILES_BYTES", 5)
    with pytest.raises(RuntimeError, match="upload limit"):
        upload_tiles(SupabaseRawStore("https://p.supabase.co", "k", httpx.Client()), path)
