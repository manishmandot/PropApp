import re
import time
from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from propapp_pipeline.parsing import SourceLayoutError

BACKOFF_SECONDS = (2, 4, 8)


def make_client() -> httpx.Client:
    return httpx.Client(
        timeout=120,
        follow_redirects=True,
        headers={"user-agent": "PropAppPipeline/1.0"},
        transport=httpx.HTTPTransport(retries=3),
    )


def download(
    http: httpx.Client,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """GET a URL, retrying 5xx responses with backoff; raises on any other non-2xx."""
    for delay in (*BACKOFF_SECONDS, None):
        response = http.get(url, headers=headers)
        if response.status_code < 500 or delay is None:
            response.raise_for_status()
            return response.content
        sleep(delay)
    raise AssertionError("unreachable")


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.hrefs.extend(v for k, v in attrs if k == "href" and v)


def discover_link(http: httpx.Client, page_url: str, pattern: str) -> str:
    """First link on the page whose href matches `pattern`, as an absolute URL."""
    parser = _LinkParser()
    parser.feed(download(http, page_url).decode("utf-8", errors="replace"))
    regex = re.compile(pattern)
    for href in parser.hrefs:
        if regex.search(href):
            return urljoin(page_url, href)
    raise SourceLayoutError(f"{page_url}: no link matching {pattern}")
