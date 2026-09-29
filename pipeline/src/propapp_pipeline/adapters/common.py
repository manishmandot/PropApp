import io
import zipfile
from collections.abc import Iterator
from urllib.parse import unquote, urlparse

import httpx

from propapp_pipeline.http import discover_link, download
from propapp_pipeline.raw_store import RawFile


def fetch_configured(http: httpx.Client, config: dict) -> list[RawFile]:
    """Download the source's `url`, or the link matching `link_pattern` on `page_url`."""
    url = config.get("url") or discover_link(http, config["page_url"], config["link_pattern"])
    filename = unquote(urlparse(url).path.rsplit("/", 1)[-1]) or "download"
    return [RawFile(filename, download(http, url))]


def zip_members(content: bytes) -> Iterator[tuple[str, bytes]]:
    """(name, bytes) for every file in a zip, recursing into nested zips."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            if name.endswith("/"):
                continue
            data = z.read(name)
            if name.lower().endswith(".zip"):
                yield from zip_members(data)
            else:
                yield name, data
