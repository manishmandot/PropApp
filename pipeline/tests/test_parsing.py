import pandas as pd
import pytest

from propapp_pipeline.parsing import (
    SourceLayoutError,
    find_header_row,
    parse_number,
    require_columns,
)


@pytest.mark.parametrize("cell", ["s", "-", "np", "n.a.", "..", "", "  ", None, float("nan")])
def test_parse_number_suppressed(cell):
    assert parse_number(cell) is None


def test_parse_number_formats():
    assert parse_number("$1,250,000") == 1250000.0
    assert parse_number("4.5%") == 4.5
    assert parse_number(7) == 7.0
    assert parse_number(" 12 ") == 12.0


def test_parse_number_rejects_text():
    with pytest.raises(ValueError):
        parse_number("twelve")


def test_require_columns_names_missing():
    with pytest.raises(SourceLayoutError, match="nsw_rent.*Median"):
        require_columns(pd.DataFrame({"Postcode": []}), ["Postcode", "Median"], "nsw_rent")


def test_find_header_row():
    raw = pd.DataFrame([["Title", None], [None, None], [" Postcode ", "Median"], ["2000", "650"]])
    assert find_header_row(raw, "postcode") == 2
    with pytest.raises(SourceLayoutError):
        find_header_row(raw, "Suburb")
