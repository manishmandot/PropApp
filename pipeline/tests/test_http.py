import httpx
import pytest

from propapp_pipeline.http import discover_link, download, make_client
from propapp_pipeline.parsing import SourceLayoutError


def test_discover_link_resolves_relative(httpx_mock):
    httpx_mock.add_response(url="https://x.gov.au/p",
                            text='<a href="/a.pdf">a</a><a href="/files/rent-2025.xlsx">r</a>')
    assert discover_link(make_client(), "https://x.gov.au/p", r"rent-.*\.xlsx$") == \
        "https://x.gov.au/files/rent-2025.xlsx"


def test_discover_link_no_match_raises(httpx_mock):
    httpx_mock.add_response(url="https://x.gov.au/p", text='<a href="/a.pdf">a</a>')
    with pytest.raises(SourceLayoutError):
        discover_link(make_client(), "https://x.gov.au/p", r"\.xlsx$")


def test_download_retries_5xx(httpx_mock):
    httpx_mock.add_response(url="https://x.gov.au/f", status_code=503)
    httpx_mock.add_response(url="https://x.gov.au/f", content=b"ok")
    sleeps = []
    assert download(make_client(), "https://x.gov.au/f", sleep=sleeps.append) == b"ok"
    assert sleeps == [2]


def test_download_raises_on_404(httpx_mock):
    httpx_mock.add_response(url="https://x.gov.au/f", status_code=404)
    with pytest.raises(httpx.HTTPStatusError):
        download(make_client(), "https://x.gov.au/f", sleep=lambda s: None)
