from datetime import date

from propapp_pipeline.raw_store import LocalRawStore, RawFile, SupabaseRawStore


def test_local_raw_store_key(tmp_path):
    key = LocalRawStore(tmp_path).put("abs_erp", date(2026, 9, 29), RawFile("a.csv", b"x"))
    assert key == "raw/abs_erp/2026-09-29/a.csv" and (tmp_path / key).read_bytes() == b"x"


def test_supabase_put_upserts(httpx_mock):
    import httpx
    httpx_mock.add_response(
        method="POST", url="https://p.supabase.co/storage/v1/object/raw/raw/src/2026-09-29/f.zip")
    store = SupabaseRawStore("https://p.supabase.co", "secret", httpx.Client())
    key = store.put("src", date(2026, 9, 29), RawFile("f.zip", b"zz"))
    request = httpx_mock.get_request()
    assert key == "raw/src/2026-09-29/f.zip"
    assert request.headers["x-upsert"] == "true"
    assert request.headers["authorization"] == "Bearer secret"


def test_supabase_ensure_bucket_creates_when_missing(httpx_mock):
    import httpx
    httpx_mock.add_response(method="GET", url="https://p.supabase.co/storage/v1/bucket/raw",
                            status_code=404)
    httpx_mock.add_response(method="POST", url="https://p.supabase.co/storage/v1/bucket")
    SupabaseRawStore("https://p.supabase.co", "secret", httpx.Client()).ensure_bucket()
    created = httpx_mock.get_requests()[-1]
    assert b'"public": false' in created.content or b'"public":false' in created.content
