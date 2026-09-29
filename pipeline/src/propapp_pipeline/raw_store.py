from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

import httpx

# Census DataPacks and NSW yearly sales zips exceed Supabase's 50 MB default; the
# project's global upload limit must also be raised to at least this (see README).
MAX_RAW_FILE_BYTES = 1024**3


@dataclass(frozen=True)
class RawFile:
    filename: str
    content: bytes


def raw_key(source: str, run_date: date, filename: str) -> str:
    return f"raw/{source}/{run_date.isoformat()}/{filename}"


class RawStore(Protocol):
    def put(self, source: str, run_date: date, file: RawFile) -> str: ...


class LocalRawStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, source: str, run_date: date, file: RawFile) -> str:
        key = raw_key(source, run_date, file.filename)
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file.content)
        return key


class SupabaseRawStore:
    """Stores raw files unchanged in a private Supabase Storage bucket."""

    def __init__(self, url: str, service_key: str, http: httpx.Client, bucket: str = "raw"):
        self.url = url.rstrip("/")
        self.bucket = bucket
        self.http = http
        self.headers = {"authorization": f"Bearer {service_key}", "apikey": service_key}

    def ensure_bucket(self) -> None:
        response = self.http.get(f"{self.url}/storage/v1/bucket/{self.bucket}",
                                 headers=self.headers)
        if response.status_code == 200:
            return
        self.http.post(
            f"{self.url}/storage/v1/bucket",
            headers=self.headers,
            json={"id": self.bucket, "name": self.bucket, "public": False,
                  "file_size_limit": MAX_RAW_FILE_BYTES},
        ).raise_for_status()

    def put(self, source: str, run_date: date, file: RawFile) -> str:
        key = raw_key(source, run_date, file.filename)
        self.http.post(
            f"{self.url}/storage/v1/object/{self.bucket}/{key}",
            headers={**self.headers, "x-upsert": "true",
                     "content-type": "application/octet-stream"},
            content=file.content,
        ).raise_for_status()
        return key
