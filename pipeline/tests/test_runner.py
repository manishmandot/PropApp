from dataclasses import replace
from datetime import date

import pytest
import yaml

from propapp_pipeline import db, runner
from propapp_pipeline.cli import main
from propapp_pipeline.db import connect
from propapp_pipeline.raw_store import LocalRawStore
from propapp_pipeline.runner import run_source
from tests.fake_adapter import CFG, SUBURBS

TODAY = date(2026, 9, 29)


@pytest.fixture
def seeded_suburbs(db_url):
    with connect(db_url) as conn:
        for code in SUBURBS:
            conn.execute("insert into data.suburbs (sal_code, name, state) values (%s,%s,'NSW')",
                         (code, f"S{code}"))
    return db_url


def run(db_url, tmp_path, **options):
    return run_source("fake", db_url=db_url, raw_store=LocalRawStore(tmp_path), http=None,
                      today=TODAY, config=CFG, options=options)


def all_values(db_url):
    with connect(db_url) as conn:
        return [r[0] for r in conn.execute(
            "select value from data.observations order by suburb_code")]


def run_row(db_url, run_id):
    with connect(db_url) as conn:
        cur = conn.execute("select * from data.ingestion_runs where id = %s", (run_id,))
        return dict(zip([c.name for c in cur.description], cur.fetchone(), strict=True))


def test_successful_run_writes_and_logs(seeded_suburbs, tmp_path):
    out = run(seeded_suburbs, tmp_path)
    assert out.status == "success" and out.rows_written == 3
    assert all_values(seeded_suburbs) == [1.0, 1.0, 1.0]
    row = run_row(seeded_suburbs, out.run_id)
    assert row["status"] == "success" and row["raw_keys"] == ["raw/fake/2026-09-29/fake.csv"]
    assert row["match_rate"] == 1.0 and row["rows_parsed"] == 3
    with connect(seeded_suburbs) as conn:
        assert conn.execute("select commercial_use from data.sources where id='fake'"
                            ).fetchone() == ("confirmed",)


def test_rerun_is_idempotent(seeded_suburbs, tmp_path):
    run(seeded_suburbs, tmp_path)
    out = run(seeded_suburbs, tmp_path, value="2")
    assert out.status == "success"
    assert all_values(seeded_suburbs) == [2.0, 2.0, 2.0]


def test_failed_run_leaves_data_untouched(seeded_suburbs, tmp_path, monkeypatch):
    run(seeded_suburbs, tmp_path)

    def upsert_then_raise(conn, obs):
        db.upsert_observations(conn, [replace(o, value=99.0) for o in obs])
        raise RuntimeError("boom")

    monkeypatch.setattr(runner, "upsert_observations", upsert_then_raise)
    out = run(seeded_suburbs, tmp_path, value="99")
    assert out.status == "failed"
    assert all_values(seeded_suburbs) == [1.0, 1.0, 1.0]
    assert "boom" in run_row(seeded_suburbs, out.run_id)["error"]


def test_quality_failure_is_logged(seeded_suburbs, tmp_path):
    out = run(seeded_suburbs, tmp_path, value="-5")
    assert out.status == "failed"
    assert "out of range" in run_row(seeded_suburbs, out.run_id)["error"]
    assert all_values(seeded_suburbs) == []


def test_cli_exit_code(seeded_suburbs, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", seeded_suburbs)
    monkeypatch.setenv("SUPABASE_URL", "https://unused.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "unused")
    config = tmp_path / "sources.yaml"
    config.write_text(yaml.safe_dump(CFG))
    store = LocalRawStore(tmp_path)
    args = ["--config", str(config), "run", "fake"]
    assert main(args, raw_store=store) == 0
    assert main([*args, "--option", "raise_in_parse=1"], raw_store=store) == 1


def test_runner_tells_adapter_last_success(seeded_suburbs, tmp_path, monkeypatch):
    seen = []
    from tests.fake_adapter import FakeAdapter
    original = FakeAdapter.fetch

    def spy(self, http, config):
        seen.append(self.last_success)
        return original(self, http, config)

    monkeypatch.setattr(FakeAdapter, "fetch", spy)
    run(seeded_suburbs, tmp_path)
    run(seeded_suburbs, tmp_path)
    assert seen[0] is None and seen[1] == date.today()
