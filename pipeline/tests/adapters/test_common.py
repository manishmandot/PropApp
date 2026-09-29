from propapp_pipeline.adapters.common import fetch_configured
from propapp_pipeline.http import make_client


def test_fetch_direct_url(httpx_mock):
    httpx_mock.add_response(url="https://x.gov.au/d/file.zip", content=b"z")
    [f] = fetch_configured(make_client(), {"url": "https://x.gov.au/d/file.zip"})
    assert (f.filename, f.content) == ("file.zip", b"z")


def test_fetch_discovered_link(httpx_mock):
    httpx_mock.add_response(url="https://x.gov.au/page", text='<a href="/f/rent%20q3.xlsx">x</a>')
    httpx_mock.add_response(url="https://x.gov.au/f/rent%20q3.xlsx", content=b"x")
    [f] = fetch_configured(make_client(), {"page_url": "https://x.gov.au/page",
                                           "link_pattern": r"rent.*\.xlsx"})
    assert f.filename == "rent q3.xlsx"
