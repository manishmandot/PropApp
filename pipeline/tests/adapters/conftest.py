import io
import zipfile
from datetime import date

import pandas as pd
import pytest

from propapp_pipeline.adapters.base import NormaliseContext
from propapp_pipeline.geo.allocate import Correspondence, CorrespondenceIndex
from propapp_pipeline.geo.match import SuburbMatcher


def make_ctx(correspondences=(), suburbs=(), conn=None, today=date(2026, 9, 29)):
    index = CorrespondenceIndex.from_rows(Correspondence(*c) for c in correspondences)
    return NormaliseContext(conn, index, SuburbMatcher.from_rows(list(suburbs), index), None,
                            {}, today)


def zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return buf.getvalue()


def xlsx_bytes(sheets: dict[str, list[list]]) -> bytes:
    """Workbook whose sheets are written cell-for-cell (no header inference)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf) as xl:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(xl, sheet_name=name, header=False, index=False)
    return buf.getvalue()


def by(result, code, metric):
    return next(o for o in result.observations if o.suburb_code == code and o.metric == metric)


@pytest.fixture
def ctx_factory():
    return make_ctx
