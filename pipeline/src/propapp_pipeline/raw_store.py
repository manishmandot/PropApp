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
        self._ensure(self.bucket, public=False)

    def ensure_public_bucket(self, name: str) -> None:
        self._ensure(name, public=True)

    def _ensure(self, name: str, *, public: bool) -> None:
        response = self.http.get(f"{self.url}/storage/v1/bucket/{name}", headers=self.headers)
        if response.status_code == 200:
            return
        self.http.post(
            f"{self.url}/storage/v1/bucket",
            headers=self.headers,
            json={"id": name, "name": name, "public": public,
                  "file_size_limit": MAX_RAW_FILE_BYTES},
        ).raise_for_status()

    def put_object(self, bucket: str, key: str, content: bytes,
                   content_type: str = "application/octet-stream") -> None:
        self.http.post(
            f"{self.url}/storage/v1/object/{bucket}/{key}",
            headers={**self.headers, "x-upsert": "true", "content-type": content_type},
            content=content,
        ).raise_for_status()

    def public_url(self, bucket: str, key: str) -> str:
        return f"{self.url}/storage/v1/object/public/{bucket}/{key}"

    def put(self, source: str, run_date: date, file: RawFile) -> str:
        key = raw_key(source, run_date, file.filename)
        self.put_object(self.bucket, key, file.content)
        return key
