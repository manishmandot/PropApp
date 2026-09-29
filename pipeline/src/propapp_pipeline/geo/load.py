from pathlib import Path

import geopandas as gpd
import pandas as pd
import psycopg

STATE_ABBREVIATIONS = {
    "New South Wales": "NSW",
    "Victoria": "VIC",
    "Queensland": "QLD",
    "South Australia": "SA",
    "Western Australia": "WA",
    "Tasmania": "TAS",
    "Northern Territory": "NT",
    "Australian Capital Territory": "ACT",
    "Other Territories": "OT",
}

CORRESPONDENCE_GEOGRAPHIES = {"SA2": "SA2_CODE_2021", "POA": "POA_CODE_2021"}


def load_suburbs(conn: psycopg.Connection, boundaries_path: Path) -> int:
    """Load ABS SAL 2021 boundaries into data.suburbs. Returns rows loaded."""
    gdf = gpd.read_file(boundaries_path)
    gdf = gdf[gdf.geometry.notna()].to_crs("EPSG:4326")
    rows = [
        (
            str(r.SAL_CODE21),
            r.SAL_NAME21,
            STATE_ABBREVIATIONS[r.STE_NAME21],
            r.geometry.wkb,
            None if pd.isna(r.AREASQKM21) else float(r.AREASQKM21),
        )
        for r in gdf.itertuples()
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            insert into data.suburbs (sal_code, name, state, geom, area_sqkm)
            values (%s, %s, %s, extensions.st_multi(extensions.st_geomfromwkb(%s, 4326)), %s)
            on conflict (sal_code) do update set
                name = excluded.name, state = excluded.state,
                geom = excluded.geom, area_sqkm = excluded.area_sqkm
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def _correspondence_rows(mb: pd.DataFrame, geography: str, column: str) -> pd.DataFrame:
    grouped = (
        mb.groupby([column, "SAL_CODE_2021"], as_index=False)
        .agg(population=("Person", "sum"), area=("AREA_ALBERS_SQKM", "sum"))
        .rename(columns={column: "from_code", "SAL_CODE_2021": "sal_code"})
    )
    from_population = grouped.groupby("from_code")["population"].transform("sum")
    grouped["weight"] = grouped["population"].where(from_population > 0, grouped["area"])
    grouped["ratio"] = grouped["weight"] / grouped.groupby("from_code")["weight"].transform("sum")
    grouped["from_geography"] = geography
    return grouped[["from_geography", "from_code", "sal_code", "weight", "ratio"]]


def build_correspondences(
    conn: psycopg.Connection, mb_allocation: pd.DataFrame, mb_counts: pd.DataFrame
) -> int:
    """Rebuild SA2→SAL and POA→SAL correspondences from mesh blocks. Returns rows written.

    Weight is the mesh-block Census population shared by the from-area and the suburb;
    a from-area with zero population is weighted by mesh-block area instead.
    """
    mb = mb_allocation.astype({"MB_CODE_2021": str}).merge(
        mb_counts.astype({"MB_CODE_2021": str})[["MB_CODE_2021", "Person"]],
        on="MB_CODE_2021",
        how="left",
    )
    mb["Person"] = mb["Person"].fillna(0)
    known = {r[0] for r in conn.execute("select sal_code from data.suburbs")}
    mb = mb[mb["SAL_CODE_2021"].astype(str).isin(known)]

    frames = [_correspondence_rows(mb, g, col) for g, col in CORRESPONDENCE_GEOGRAPHIES.items()]
    rows = pd.concat(frames)
    rows = rows[rows["ratio"].notna()]
    with conn.cursor() as cur:
        cur.execute(
            "delete from data.geo_correspondences where from_geography = any(%s)",
            (list(CORRESPONDENCE_GEOGRAPHIES),),
        )
        with cur.copy(
            "copy data.geo_correspondences (from_geography, from_code, sal_code, weight, ratio) "
            "from stdin"
        ) as copy:
            for r in rows.itertuples(index=False):
                copy.write_row((r.from_geography, str(r.from_code), str(r.sal_code),
                                float(r.weight), float(r.ratio)))
    conn.commit()
    return len(rows)


def read_abs_table(content: bytes, filename: str, header: str) -> pd.DataFrame:
    """Read an ABS CSV/XLSX (optionally zipped) into one frame of strings.

    XLSX tables may span several sheets with title rows above the header; every sheet
    containing `header` is read from its header row and the sheets are concatenated.
    """
    import io
    import zipfile

    from propapp_pipeline.parsing import SourceLayoutError, find_header_row

    name = filename.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            inner = [n for n in z.namelist() if n.lower().endswith((".csv", ".xlsx"))]
            if len(inner) != 1:
                raise SourceLayoutError(f"{filename}: expected one table file, found {inner}")
            return read_abs_table(z.read(inner[0]), inner[0], header)
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content), dtype=str)
    frames = []
    for sheet in pd.read_excel(io.BytesIO(content), sheet_name=None, header=None,
                               dtype=object).values():
        try:
            start = find_header_row(sheet, header)
        except SourceLayoutError:
            continue
        body = sheet.iloc[start + 1:].copy()
        body.columns = [str(c).strip() for c in sheet.iloc[start]]
        frames.append(body.dropna(subset=[header]))
    if not frames:
        raise SourceLayoutError(f"{filename}: no sheet with header {header!r}")
    df = pd.concat(frames, ignore_index=True)
    df[header] = df[header].astype(str)
    return df
