"""Suburb boundary tiles for the web app's map explorer (spec §6.2).

Features carry only the 5-band score, so exact scores stay behind the server (where plan
limits apply later); the app fetches them on hover.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import psycopg

from propapp_pipeline.raw_store import SupabaseRawStore

TILES_BUCKET = "tiles"
TILES_KEY = "suburbs.pmtiles"
TILES_CACHE_SECONDS = 300
# Supabase's default per-file upload limit; raise with TILES_MAX_BYTES after raising it there.
MAX_TILES_BYTES = int(os.environ.get("TILES_MAX_BYTES", 50 * 1024 * 1024))
SIMPLIFY_DEGREES = 0.0005
TIPPECANOE_OPTIONS = ["-l", "suburbs", "-zg", "--coalesce-densest-as-needed",
                      "--extend-zooms-if-still-dropping", "--force"]


def score_band(score: float | None) -> int:
    """1 for 0–20 … 5 for 80–100 (100 included); 0 when unscored."""
    if score is None:
        return 0
    return min(int(score // 20) + 1, 5)


def export_geojson(conn: psycopg.Connection, path: Path) -> int:
    """Write one newline-delimited GeoJSON feature per suburb with a boundary."""
    rows = conn.execute(
        """
        select sub.sal_code, sub.name, sub.state, a.slug, a.propapp_score,
               extensions.st_asgeojson(
                   extensions.st_simplifypreservetopology(sub.geom, %s), 5)
        from data.suburbs sub
        join api.suburbs a using (sal_code)
        where sub.geom is not null
        order by sub.sal_code
        """,
        (SIMPLIFY_DEGREES,),
    )
    count = 0
    with path.open("w") as out:
        for code, name, state, slug, score, geometry in rows:
            feature = {
                "type": "Feature",
                "properties": {"code": code, "name": name, "state": state, "slug": slug,
                               "band": score_band(score)},
                "geometry": json.loads(geometry),
            }
            out.write(json.dumps(feature, separators=(",", ":")) + "\n")
            count += 1
    return count


def build_pmtiles(geojson: Path, out: Path, run=subprocess.run) -> None:
    if shutil.which("tippecanoe") is None:
        raise RuntimeError("tippecanoe is not installed (apt-get install tippecanoe)")
    argv = ["tippecanoe", "-o", str(out), *TIPPECANOE_OPTIONS, str(geojson)]
    try:
        run(argv, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"tippecanoe failed with exit code {exc.returncode}") from exc


def upload_tiles(store: SupabaseRawStore, path: Path) -> str:
    """Upload to the public `tiles` bucket; returns the file's public URL.

    The file is replaced in place, so it is served with a short cache lifetime: browsers
    and the CDN pick up new tiles within minutes, and mixed old/new byte ranges are brief.
    """
    size = path.stat().st_size
    if size > MAX_TILES_BYTES:
        raise RuntimeError(
            f"suburbs.pmtiles is {size / 1e6:.1f} MB, over the {MAX_TILES_BYTES / 1e6:.0f} MB "
            "upload limit (TILES_MAX_BYTES); raise the Supabase upload limit and the setting")
    store.ensure_public_bucket(TILES_BUCKET)
    store.put_object(TILES_BUCKET, TILES_KEY, path.read_bytes(),
                     cache_seconds=TILES_CACHE_SECONDS)
    return store.public_url(TILES_BUCKET, TILES_KEY)
