import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon


def _square(x: float) -> Polygon:
    return Polygon([(x, -33), (x + 0.01, -33), (x + 0.01, -33.01), (x, -33.01)])


@pytest.fixture
def sal_file(tmp_path):
    """SAL boundaries in the ABS column layout: 3 spatial suburbs + 1 non-spatial."""
    gdf = gpd.GeoDataFrame(
        {
            "SAL_CODE21": ["10001", "10002", "10003", "19494"],
            "SAL_NAME21": ["Alpha", "Beta", "Gamma", "No usual address (NSW)"],
            "STE_NAME21": ["New South Wales"] * 4,
            "AREASQKM21": [1.2, 3.4, 5.6, None],
        },
        geometry=[_square(151.0), _square(151.1), _square(151.2), None],
        crs="EPSG:7844",
    )
    path = tmp_path / "sal.gpkg"
    gdf.to_file(path, driver="GPKG")
    return path


@pytest.fixture
def mb_frames():
    """Mesh-block allocation + counts.

    SA2 101: MB1 (pop 300) in SAL 10001, MB2 (pop 100) in SAL 10002.
    SA2 102: zero population; MB3 (1.0 km²) in SAL 10002, MB4 (3.0 km²) in SAL 10003.
    """
    allocation = pd.DataFrame(
        {
            "MB_CODE_2021": ["1", "2", "3", "4"],
            "SA2_CODE_2021": ["101", "101", "102", "102"],
            "SAL_CODE_2021": ["10001", "10002", "10002", "10003"],
            "POA_CODE_2021": ["2000", "2000", "2001", "2001"],
            "AREA_ALBERS_SQKM": [0.5, 0.5, 1.0, 3.0],
        }
    )
    counts = pd.DataFrame({"MB_CODE_2021": ["1", "2", "3", "4"], "Person": [300, 100, 0, 0]})
    return allocation, counts
