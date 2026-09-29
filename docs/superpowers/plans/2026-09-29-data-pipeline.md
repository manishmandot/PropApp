# Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest the eight v1 public data sources into Supabase Postgres, normalise them to ABS SAL suburbs in one `observations` table, and run them on a schedule with logging and quality checks.

**Architecture:** A Python package (`pipeline/`) holds one adapter per source behind a common `fetch → parse → normalise` contract. A runner stores raw files in Supabase Storage, allocates non-SAL data to suburbs using population-weighted correspondences built from ABS mesh blocks, runs quality checks, and upserts inside one transaction. Every run is logged in `data.ingestion_runs`. GitHub Actions runs the sources on a schedule.

**Tech Stack:** Python 3.12, uv, httpx, psycopg 3, pandas, geopandas/pyogrio, openpyxl, PyYAML, pytest, ruff. Postgres 16 + PostGIS (Supabase in production, `postgis/postgis:16-3.4` for tests). GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-29-propapp-design.md` (§4 is the part this plan implements; §3 gives context)

## Global Constraints

- The canonical unit is ABS SAL, ASGS Edition 3 (2021). `suburb_code` is the 5-digit SAL code as text, without the `SAL` prefix (e.g. `10001`).
- All pipeline tables live in Postgres schema `data`. It has no grants to `anon`/`authenticated`, so nothing in it is reachable through the Supabase API. The app gets views in a later sub-project.
- `observations` unique key: (`source`, `metric`, `suburb_code`, `period_start`, `period_granularity`). Loads are upserts.
- Metrics come only from the controlled vocabulary in `models.METRICS`. Any other name is a programming error.
- Quality defaults: row count within ±25% of the source's previous successful run (skipped on first run; `row_count_tolerance` can be overridden per adapter); ≥98% of rows matched to a suburb; every value within its metric's range.
- A failed check or any exception leaves `observations` unchanged, marks the run `failed` with an error message, and makes the CLI exit with code 1.
- Raw files are stored unchanged at `raw/<source>/<YYYY-MM-DD>/<filename>` in the private Supabase Storage bucket `raw`.
- Correspondence weights come from mesh-block 2021 Census population. When a from-area has zero population, mesh-block area is used instead.
- NSW sale addresses are stored only in `data.nsw_sales`. Only suburb-level aggregates leave that table.
- Secrets come from the environment only (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) and are never committed.
- **Out of scope** (handled by later sub-projects): the scoring trigger, vector tiles, and showing attribution in the app.

## Review Focus

1. **Source layout drift.** A publisher renames a column, a sheet, or a link on its landing page. Expected: the run fails naming the source and the missing column or link, and the previous data stays live. Tests: Task 5 `test_require_columns_names_missing`, Task 5 `test_discover_link_no_match_raises`.
2. **Suppressed or blank cells** (`s`, `-`, `np`, `n.a.`, empty) in ABS, JSA, DCJ and DFFH files. Expected: the cell is skipped, never read as 0. Test: Task 5 `test_parse_number_suppressed`, used by Tasks 10, 12 and 14.
3. **Ambiguous or variant locality names** (the same name twice in one state, `MT` vs `Mount`, SAL names with a `(NSW)` suffix). Expected: the postcode picks between candidates; unmatched rows count against the match rate. Tests: Task 4 `test_match_disambiguates_by_postcode`, `test_match_mt_and_suffix`.
4. **Re-running unchanged data**, e.g. monthly schedules on quarterly sources. Expected: no duplicate rows, the same row count, and the run passes. Test: Task 6 `test_rerun_is_idempotent`.
5. **Failure midway through a load.** Expected: no partial observations, earlier data intact, and the run logged `failed` with its error. Test: Task 6 `test_failed_run_leaves_data_untouched`.

---

## File Structure

```
pipeline/
  pyproject.toml
  sources.yaml                      # per-source URLs, licence, attribution, cadence
  src/propapp_pipeline/
    __main__.py  cli.py             # `python -m propapp_pipeline …`
    config.py                       # env settings
    models.py                       # Period, METRICS, Observation, GeoValue
    db.py                           # connect(), observation/run-log persistence
    raw_store.py                    # Supabase + local raw file stores
    http.py                         # client with retries, discover_link()
    parsing.py                      # parse_number, require_columns, find_header_row
    quality.py                      # quality checks
    runner.py                       # run_source orchestration
    sources.py                      # load sources.yaml, sync to data.sources
    geo/load.py                     # suburbs + mesh-block correspondences
    geo/allocate.py                 # CorrespondenceIndex, allocate()
    geo/match.py                    # SuburbMatcher
    adapters/base.py                # Adapter ABC, RawFile, NormaliseResult, registry
    adapters/abs_sdmx.py            # shared ABS Data API CSV reader
    adapters/{abs_census,abs_erp,abs_building_approvals,jsa_salm,
              nsw_vg_sales,nsw_rent,vic_vg_medians,vic_dffh_rental}.py
  tests/  (mirrors src; fixtures/<source>/…)
supabase/migrations/20260929000100_pipeline_schema.sql
.github/workflows/{pipeline-ci,pipeline-weekly,pipeline-monthly,pipeline-manual}.yml
```

---

### Task 1: Package scaffold, schema, and test database

**Files:**
- Create: `pipeline/pyproject.toml`, `pipeline/src/propapp_pipeline/__init__.py`, `pipeline/src/propapp_pipeline/config.py`, `pipeline/src/propapp_pipeline/db.py`
- Create: `supabase/migrations/20260929000100_pipeline_schema.sql`
- Test: `pipeline/tests/conftest.py`, `pipeline/tests/test_schema.py`

**Interfaces:**
- Produces: `Settings.from_env() -> Settings` (fields `database_url`, `supabase_url`, `supabase_service_role_key`); `db.connect(url: str) -> psycopg.Connection`; pytest fixture `db_url: str` (a fresh database with the migrations applied; data tables are truncated after each test).

- [ ] **Step 1: Write the failing test**

```python
def test_schema_tables_exist(db_url):
    with connect(db_url) as conn:
        names = {r[0] for r in conn.execute(
            "select table_name from information_schema.tables where table_schema='data'")}
    assert names == {"suburbs", "geo_correspondences", "observations",
                     "ingestion_runs", "sources", "nsw_sales"}

def test_observation_unique_key(db_url):
    # inserting the same (source, metric, suburb_code, period_start, period_granularity) twice raises UniqueViolation
```

- [ ] **Step 2: Run the tests to check they fail**

Start the test database: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgis/postgis:16-3.4`

Run: `cd pipeline && uv run pytest tests/test_schema.py -v`
Expected: FAIL (the fixture or module doesn't exist yet)

- [ ] **Step 3: Write the migration**

The migration creates `extensions` if missing, runs `create extension if not exists postgis with schema extensions`, and creates schema `data` with these tables:

| Table | Columns |
|---|---|
| `suburbs` | `sal_code text pk`, `name text`, `state text`, `geom extensions.geometry(MultiPolygon,4326)`, `area_sqkm numeric` |
| `geo_correspondences` | `from_geography text`, `from_code text`, `sal_code text fk`, `weight double precision`, `ratio double precision`; pk (`from_geography`,`from_code`,`sal_code`) |
| `observations` | `suburb_code text fk`, `metric text`, `period_start date`, `period_granularity text check in ('month','quarter','year')`, `value double precision`, `source text`, `source_geography text`, `ingested_at timestamptz default now()`; pk = unique key above; index (`suburb_code`,`metric`) |
| `ingestion_runs` | `id bigserial pk`, `source text`, `started_at timestamptz`, `finished_at timestamptz`, `status text check in ('running','success','failed')`, `rows_parsed int`, `rows_written int`, `match_rate double precision`, `error text`, `raw_keys text[]` |
| `sources` | `id text pk`, `name text`, `url text`, `licence text`, `attribution text`, `commercial_use text check in ('confirmed','pending','prohibited')`, `cadence_days int` |
| `nsw_sales` | `dealing_number text`, `property_id text`, `contract_date date`, `price numeric`, `is_strata bool`, `locality text`, `postcode text`, `address text`, `sal_code text null`; pk (`dealing_number`,`property_id`) |

In `pyproject.toml`, `requires-python = ">=3.12"`, with the dependencies from the tech stack. The `conftest.py` reads `TEST_DATABASE_URL`, defaulting to `postgresql://postgres:postgres@localhost:5432/postgres`. It creates a database `propapp_test_<pid>`, applies `supabase/migrations/*.sql` in sorted order, and drops the database at the end of the session.

- [ ] **Step 4: Run the tests to check they pass**

Run: `uv run pytest tests/test_schema.py -v && uv run ruff check`
Expected: PASS, ruff clean

- [ ] **Step 5: Commit**

```bash
git add pipeline supabase && git commit -m "feat(pipeline): scaffold package and data schema"
```

---

### Task 2: Core models and metric vocabulary

**Files:**
- Create: `pipeline/src/propapp_pipeline/models.py`
- Test: `pipeline/tests/test_models.py`

**Interfaces:**
- Produces:
  - `Granularity(StrEnum)`: `MONTH`, `QUARTER`, `YEAR`
  - `Period(start: date, granularity: Granularity)`, frozen. `start` must be the first day of its month, quarter or year, otherwise `ValueError`. `Period.month(y, m)`, `Period.quarter(y, q)`, `Period.year(y)`.
  - `Kind(StrEnum)`: `ADDITIVE`, `INTENSIVE`
  - `MetricDef(name, kind, min, max)`
  - `METRICS: dict[str, MetricDef]`
  - `Observation(suburb_code, metric, period, value, source, source_geography)`, frozen. `ValueError` if `metric not in METRICS`.
  - `GeoValue(geography, code, metric, period, value)`: a value before it is allocated to suburbs.

`METRICS` (name, kind, min, max). This is the complete v1 vocabulary:

| Metric | Kind | Min | Max |
|---|---|---|---|
| `population` | additive | 0 | 250 000 |
| `population_census` | additive | 0 | 250 000 |
| `dwellings_total` | additive | 0 | 120 000 |
| `building_approvals_dwellings` | additive | 0 | 5 000 |
| `unemployed_count` | additive | 0 | 50 000 |
| `labour_force_count` | additive | 0 | 200 000 |
| `median_household_income_weekly` | intensive | 0 | 20 000 |
| `median_age` | intensive | 0 | 100 |
| `avg_household_size` | intensive | 0 | 10 |
| `owner_occupier_share` | intensive | 0 | 1 |
| `sales_count_house_12m` / `sales_count_unit_12m` | additive | 0 | 10 000 |
| `median_sale_price_house_12m` / `_unit_12m` / `_house_3m` / `_unit_3m` | intensive | 10 000 | 50 000 000 |
| `median_weekly_rent_house_q` / `_unit_q` / `_all_q` | intensive | 50 | 10 000 |
| `bonds_lodged_q` | additive | 0 | 10 000 |

- [ ] **Step 1: Write the failing tests**

```python
def test_period_rejects_mid_quarter():
    with pytest.raises(ValueError):
        Period(date(2024, 2, 1), Granularity.QUARTER)

def test_period_quarter_helper():
    assert Period.quarter(2024, 3) == Period(date(2024, 7, 1), Granularity.QUARTER)

def test_observation_rejects_unknown_metric():
    with pytest.raises(ValueError):
        Observation("10001", "vacancy_rate", Period.year(2024), 1.0, "x", "SAL")

def test_metric_kinds():
    assert METRICS["population"].kind is Kind.ADDITIVE
    assert METRICS["median_weekly_rent_all_q"].kind is Kind.INTENSIVE
```

- [ ] **Step 2: Run the tests to check they fail.** `uv run pytest tests/test_models.py -v` → FAIL (import error)
- [ ] **Step 3: Implement `models.py`** with the signatures and table above.
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(pipeline): observation models and metric vocabulary"`

---

### Task 3: Load suburbs and build correspondences

**Files:**
- Create: `pipeline/src/propapp_pipeline/geo/__init__.py`, `pipeline/src/propapp_pipeline/geo/load.py`
- Test: `pipeline/tests/geo/test_load.py`, `pipeline/tests/fixtures/geo/` (a tiny SAL GeoPackage with 3 suburbs; mesh-block allocation and counts CSVs with 6 mesh blocks)

**Interfaces:**
- Consumes: `db.connect`
- Produces:
  - `load_suburbs(conn, boundaries_path: Path) -> int`: reads the ABS SAL 2021 GDA2020 file with geopandas and converts it to EPSG:4326, promoting polygons to multipolygons. It drops rows with null geometry (non-spatial SALs). Codes come from `SAL_CODE21`, names from `SAL_NAME21`, states from `STE_NAME21` mapped to abbreviations (`NSW`, `VIC`, `QLD`, `SA`, `WA`, `TAS`, `NT`, `ACT`, `OT`). It upserts and returns the row count.
  - `build_correspondences(conn, mb_allocation: pd.DataFrame, mb_counts: pd.DataFrame) -> int`: builds rows for `from_geography` in `{"SA2", "POA"}`.
    - `weight` = total mesh-block population in (from_code ∩ sal_code). If the from-area's total population is 0, `weight` = the overlapping mesh-block area instead.
    - `ratio` = weight / the from-area's total weight.
    - It replaces all existing rows for those geographies.
  - `build_correspondences` takes as input the ABS allocation columns `MB_CODE_2021`, `SA2_CODE_2021`, `SAL_CODE_2021`, `POA_CODE_2021` and `AREA_ALBERS_SQKM`, joined from the MB, SAL and POA allocation files, and the mesh-block counts columns `MB_CODE_2021` and `Person`.

- [ ] **Step 1: Write the failing tests**

```python
def test_ratio_is_population_weighted(db_url, geo_fixtures):
    # fixture: SA2 "101" has MBs pop 300 in SAL 10001 and 100 in SAL 10002
    rows = correspondences(db_url, "SA2", "101")
    assert rows == {"10001": pytest.approx(0.75), "10002": pytest.approx(0.25)}

def test_zero_population_falls_back_to_area(db_url, geo_fixtures):
    # fixture: SA2 "102" has pop 0; MB areas 1.0 km² in 10002 and 3.0 km² in 10003
    assert correspondences(db_url, "SA2", "102") == {"10002": pytest.approx(0.25), "10003": pytest.approx(0.75)}

def test_load_suburbs_skips_null_geometry(db_url, geo_fixtures):
    assert load_suburbs(conn, geo_fixtures / "sal.gpkg") == 3   # fixture has 4 rows, 1 with null geometry
```

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement `geo/load.py`.** Use a pandas group-by on (from_code, SAL_CODE_2021) to build the rows, then write them with psycopg `COPY`.
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(pipeline): load SAL suburbs and mesh-block correspondences"`

---

### Task 4: Allocation and suburb name matching

**Files:**
- Create: `pipeline/src/propapp_pipeline/geo/allocate.py`, `pipeline/src/propapp_pipeline/geo/match.py`
- Test: `pipeline/tests/geo/test_allocate.py`, `pipeline/tests/geo/test_match.py`

**Interfaces:**
- Consumes: `GeoValue`, `Observation`, `METRICS`, `Kind` (Task 2); `data.geo_correspondences` and `data.suburbs` (Task 3)
- Produces:
  - `Correspondence(from_geography, from_code, sal_code, weight, ratio)`
  - `CorrespondenceIndex.from_rows(rows: list[Correspondence])`, `CorrespondenceIndex.load(conn)`, and `.targets(geography, code) -> list[Correspondence]` (empty if unknown)
  - `AllocationResult(observations: list[Observation], matched: int, total: int)`
  - `allocate(values: Iterable[GeoValue], index: CorrespondenceIndex, source: str) -> AllocationResult`, where:
    - **Additive:** SAL value = Σ value × `ratio`.
    - **Intensive:** SAL value = Σ value × `weight` / Σ `weight`, taken over the source areas that have a value for that (metric, period).
    - A `GeoValue` whose `geography == "SAL"` passes straight through.
    - `matched` counts input values that had at least one target.
  - `normalise_name(name: str) -> str`: upper-cases the name, removes any parenthetical, maps a leading or whole-word `MT` to `MOUNT`, and collapses whitespace.
  - `SuburbMatcher.from_rows(suburbs: list[tuple[str, str, str]], index)`, `SuburbMatcher.load(conn, index)`, and `.match(name, state, postcode: str | None = None) -> str | None`:
    - A single candidate for (normalised name, state) is returned.
    - With several candidates, it returns the one with the highest POA→SAL `ratio` for the postcode.
    - It returns `None` if there's no candidate, or if the postcode can't separate the candidates.

- [ ] **Step 1: Write the failing tests**

```python
def test_additive_splits_by_ratio():
    idx = CorrespondenceIndex.from_rows([C("SA2","101","10001",300,0.75), C("SA2","101","10002",100,0.25)])
    res = allocate([GeoValue("SA2","101","population",Period.year(2024),1000)], idx, "abs_erp")
    assert {o.suburb_code: o.value for o in res.observations} == {"10001": 750, "10002": 250}

def test_intensive_is_weighted_mean_of_overlapping_sources():
    # SAL 10002 gets POA 2000 (weight 100, rent 500) and POA 2001 (weight 300, rent 700) → 650
    ...
    assert value_for(res, "10002") == pytest.approx(650)

def test_unknown_code_counts_unmatched():
    res = allocate([GeoValue("SA2","999","population",Period.year(2024),5)], idx, "abs_erp")
    assert (res.matched, res.total, res.observations) == (0, 1, [])

def test_match_mt_and_suffix():
    m = SuburbMatcher.from_rows([("10050","Mount Druitt","NSW"), ("10060","Paddington (NSW)","NSW")], idx)
    assert m.match("MT DRUITT","NSW") == "10050"
    assert m.match("PADDINGTON","NSW") == "10060"

def test_match_disambiguates_by_postcode():
    # two "Bald Hills" in NSW; POA 2549 → 10070 ratio 1.0
    assert m.match("BALD HILLS","NSW","2549") == "10070"
    assert m.match("BALD HILLS","NSW") is None
```

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement `geo/allocate.py` and `geo/match.py`** with the signatures above.
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(pipeline): allocate area data to suburbs and match locality names"`

---

### Task 5: Raw store, HTTP, and parsing helpers

**Files:**
- Create: `pipeline/src/propapp_pipeline/raw_store.py`, `pipeline/src/propapp_pipeline/http.py`, `pipeline/src/propapp_pipeline/parsing.py`
- Test: `pipeline/tests/test_raw_store.py`, `pipeline/tests/test_http.py`, `pipeline/tests/test_parsing.py`

**Interfaces:**
- Produces:
  - **`RawFile`:** `RawFile(filename: str, content: bytes)`, defined here and re-exported by `adapters.base`.
  - **Raw store:**
    - `RawStore` is a Protocol with `put(source: str, run_date: date, file: RawFile) -> str`, returning the key `raw/<source>/<YYYY-MM-DD>/<filename>`.
    - `LocalRawStore(root: Path)` is the test implementation.
    - `SupabaseRawStore(url, service_key, http, bucket="raw")` has `ensure_bucket()`, which creates a private bucket if it's missing, and `put`, which POSTs to `/storage/v1/object/<bucket>/<key>` with `x-upsert: true`.
  - **HTTP:**
    - `make_client() -> httpx.Client` uses a 120 s timeout, follows redirects, sets the user agent `PropAppPipeline/1.0`, and retries 3 times on connection errors and 5xx responses, with backoff of 2, 4 and 8 s.
    - `download(http, url) -> bytes` raises on any non-2xx response.
    - `discover_link(http, page_url, pattern: str) -> str` returns the first `href` on the page matching the regex, resolved to an absolute URL. It raises `SourceLayoutError(f"{page_url}: no link matching {pattern}")` if nothing matches.
  - **Parsing:**
    - `SourceLayoutError(Exception)`.
    - `parse_number(cell) -> float | None` returns `None` for `s`, `-`, `np`, `n.a.`, `..`, empty, NaN and `None`. It strips `$`, `,` and `%` (without scaling percentages) and accepts numbers directly.
    - `require_columns(df, cols: Iterable[str], source: str)` raises `SourceLayoutError` naming the source and every missing column.
    - `find_header_row(raw: pd.DataFrame, must_contain: str) -> int` returns the index of the first row with a cell equal to `must_contain`, ignoring case and surrounding whitespace, and raises `SourceLayoutError` otherwise.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("cell", ["s", "-", "np", "n.a.", "..", "", None, float("nan")])
def test_parse_number_suppressed(cell):
    assert parse_number(cell) is None

def test_parse_number_formats():
    assert parse_number("$1,250,000") == 1250000.0 and parse_number("4.5%") == 4.5 and parse_number(7) == 7.0

def test_require_columns_names_missing():
    with pytest.raises(SourceLayoutError, match="nsw_rent.*Median"):
        require_columns(pd.DataFrame({"Postcode": []}), ["Postcode", "Median"], "nsw_rent")

def test_discover_link_no_match_raises(httpx_mock):   # pytest-httpx
    httpx_mock.add_response(url="https://x.gov.au/p", text='<a href="/a.pdf">a</a>')
    with pytest.raises(SourceLayoutError):
        discover_link(make_client(), "https://x.gov.au/p", r"\.xlsx$")

def test_local_raw_store_key(tmp_path):
    key = LocalRawStore(tmp_path).put("abs_erp", date(2026, 9, 29), RawFile("a.csv", b"x"))
    assert key == "raw/abs_erp/2026-09-29/a.csv" and (tmp_path / key).read_bytes() == b"x"
```

Add `pytest-httpx` to the dev dependencies.

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement the three modules.** Use httpx `HTTPTransport(retries=3)` for connection errors, plus a small loop for 5xx responses.
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(pipeline): raw file store, http client, parsing helpers"`

---

### Task 6: Adapter contract, runner, quality checks, and CLI

**Files:**
- Create: `adapters/__init__.py`, `adapters/base.py`, `quality.py`, `runner.py`, `sources.py`, `cli.py`, `__main__.py` (all under `pipeline/src/propapp_pipeline/`), and `pipeline/sources.yaml`
- Modify: `pipeline/src/propapp_pipeline/db.py` (add persistence functions)
- Test: `pipeline/tests/test_quality.py`, `pipeline/tests/test_runner.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5.
- Produces:
  - **Adapter contract (`adapters/base.py`):**
    - `NormaliseResult(observations: list[Observation], matched: int, total: int)`.
    - `NormaliseContext(conn, index: CorrespondenceIndex, matcher: SuburbMatcher, http, source_config: dict)`.
    - `Adapter(ABC)` has the class vars `source_id: str` and `row_count_tolerance: float = 0.25`, and these methods:
      - `__init__(self, **options)`
      - `fetch(self, http, config: dict) -> list[RawFile]`
      - `parse(self, raw: list[RawFile]) -> list`
      - `normalise(self, rows, ctx) -> NormaliseResult`
    - `REGISTRY: dict[str, type[Adapter]]`, filled in by the `@register` decorator.
  - **Quality checks:** `quality.check(result, previous_rows: int | None, tolerance: float, min_match_rate: float = 0.98) -> QualityReport(passed: bool, failures: list[str])`, where:
    - The row-count check compares `len(result.observations)` with `previous_rows`, and is skipped when that is `None`.
    - The match rate is `matched / total`, counted as 1.0 when `total == 0`.
    - The range check lists up to 10 offending observations.
  - **Persistence (`db.py`):**
    - `start_run(conn, source) -> int`
    - `finish_run(conn, run_id, status, rows_parsed, rows_written, match_rate, error, raw_keys)`
    - `previous_rows_written(conn, source) -> int | None`, from the latest `success` run
    - `upsert_observations(conn, obs: list[Observation]) -> int`, which uses `COPY` into a temp table and then `INSERT … ON CONFLICT DO UPDATE` on `value`, `source_geography` and `ingested_at`
  - **Sources config (`sources.py`):** `load_config(path) -> dict[str, dict]` and `sync_sources(conn, config)`, which upserts `data.sources`.
  - **Runner (`runner.py`):** `run_source(source_id, *, db_url, raw_store, http, today: date, config: dict, options: dict | None = None) -> RunOutcome(run_id, status, rows_written)`:
    1. `sync_sources`
    2. `start_run`, committed immediately on its own autocommit connection
    3. fetch, then `raw_store.put` each file
    4. parse
    5. In one transaction: normalise (which may write to adapter staging tables such as `nsw_sales`), then `quality.check`. If the check fails, raise `QualityError`. Otherwise run `upsert_observations`.
    6. `finish_run(success)`.

    Any exception rolls the transaction back, calls `finish_run(failed, error=str(exc))`, and returns `status="failed"`.
  - **CLI:**
    - `python -m propapp_pipeline run <source> [--years 2015-2025] [--option KEY=VALUE …]` passes `--years` and each `--option` to the adapter as keyword options, and exits 1 when the status is failed. `runner` imports `upsert_observations` by name so tests can patch it.
    - `python -m propapp_pipeline load-geo` downloads the boundary, allocation and mesh-block-count files named under `geo:` in `sources.yaml`, then calls the Task 3 loaders.
  - **`sources.yaml`:**
    - Has a `geo:` section (the SAL boundaries URL; the MB, SAL and POA allocation URLs; the mesh-block counts URL) and one `sources:` entry per adapter.
    - Each entry has these keys: `name`, `page_url`, `link_pattern` or `url`, `licence`, `attribution`, `commercial_use`, `cadence_days`.
    - `commercial_use` is `confirmed` for ABS sources (CC BY 4.0) and `pending` for all others.
    - `cadence_days` values: census 1826, erp 365, building approvals 31, jsa_salm 92, nsw_vg_sales 7, nsw_rent 92, vic_vg_medians 92, vic_dffh_rental 92.

- [ ] **Step 1: Write the failing tests.** They use a `FakeAdapter` registered in the test module, which returns configurable observations or raises on demand.

```python
def test_first_run_skips_row_count():
    assert check(NormaliseResult(obs(10), 10, 10), None, 0.25).passed

def test_row_count_outside_tolerance_fails():
    r = check(NormaliseResult(obs(70), 70, 70), previous_rows=100, tolerance=0.25)
    assert not r.passed and "row count" in r.failures[0]

def test_low_match_rate_fails():
    assert not check(NormaliseResult(obs(10), 97, 100), None, 0.25).passed

def test_out_of_range_value_fails():
    bad = Observation("10001", "owner_occupier_share", Period.year(2021), 1.4, "fake", "SAL")
    assert not check(NormaliseResult([bad], 1, 1), None, 0.25).passed

def test_successful_run_writes_and_logs(db_url, seeded_suburbs, tmp_path):
    out = run_source("fake", db_url=db_url, raw_store=LocalRawStore(tmp_path), http=None,
                     today=date(2026, 9, 29), config=CFG)
    assert out.status == "success" and count_observations(db_url) == 3
    assert run_row(db_url, out.run_id)["raw_keys"] == ["raw/fake/2026-09-29/fake.csv"]

def test_rerun_is_idempotent(db_url, seeded_suburbs, tmp_path):
    run_source("fake", ...); out = run_source("fake", ...)
    assert out.status == "success" and count_observations(db_url) == 3

def test_failed_run_leaves_data_untouched(db_url, seeded_suburbs, tmp_path, monkeypatch):
    run_source("fake", ...)                                     # 3 rows, value 1.0
    def upsert_then_raise(conn, obs):
        db.upsert_observations(conn, [replace(o, value=99.0) for o in obs]); raise RuntimeError("boom")
    monkeypatch.setattr(runner, "upsert_observations", upsert_then_raise)
    out = run_source("fake", ..., options={"value": "99"})
    assert out.status == "failed" and all_values(db_url) == [1.0, 1.0, 1.0]
    assert "boom" in run_row(db_url, out.run_id)["error"]

def test_cli_exit_code_on_failure(...):
    assert main(["run", "fake", "--option", "raise_in_parse=1"]) == 1
```

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement** `adapters/base.py`, `quality.py`, the `db.py` additions, `sources.py`, `runner.py`, `cli.py`, `__main__.py`, and a `sources.yaml` skeleton with the `geo:` URLs. In production, `cli` builds the raw store as `SupabaseRawStore` from `Settings` and calls `ensure_bucket()` once.
- [ ] **Step 4: Run the tests to check they pass.** `uv run pytest -v` → all PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(pipeline): adapter contract, runner with quality gate, CLI"`

---

### Adapter tasks (7–14): shared pattern

Each adapter is a single file in `adapters/` with a `@register` class. For each one:

1. Download the real file once from the source in its `sources.yaml` entry.
2. Make a fixture in `tests/fixtures/<source>/` that keeps the **real header rows, sheet names and column layout**, with only the data rows listed in the test and those rows' numbers replaced by the test's values.
3. In each adapter's tests:
   - Assert `parse` output.
   - Assert `normalise` output against a hand-built `CorrespondenceIndex`/`SuburbMatcher` covering the fixture codes.
   - Assert that removing a required column raises `SourceLayoutError`.
4. Add the adapter's entry to `sources.yaml`.
5. Commit with `feat(pipeline): <source> adapter`.

Every parser locates its columns with `find_header_row` and `require_columns`, never with fixed positions. Every cell goes through `parse_number`. Rows whose value is `None` are dropped before normalising and don't count in `total`.

Each task below lists the source, what to extract, the tests, and the class name. The steps are the same five-step TDD cycle as Tasks 2–6.

### Task 7: `abs_census` (ABS Census 2021 GCP DataPack, SAL)

- **Source:** the zip at `url` (2021 GCP, all geographies or SAL, GDA2020) from `https://www.abs.gov.au/census/find-census-data/datapacks`. `row_count_tolerance = 0.25`.
- **Parse:** read `2021Census_G01_AUST_SAL.csv`, `…G02…` and `…G37…` from inside the zip. `SAL_CODE_2021` values look like `SAL10001`; strip the `SAL` prefix.
- **Output:** everything at `Period.year(2021)`, with `source_geography="SAL"`:
  - `population_census` = G01 `Tot_P_P`
  - `median_age` = G02 `Median_age_persons`
  - `median_household_income_weekly` = G02 `Median_tot_hhd_inc_weekly`
  - `avg_household_size` = G02 `Average_household_size`
  - `dwellings_total` = G37 `Total_Total`
  - `owner_occupier_share` = (`O_OR_Total` + `O_MTG_Total`) / `Total_Total`, skipped when the total is 0
- **Test:** `test_owner_occupier_share`: a fixture row with O_OR 200, O_MTG 300 and Total 1000 gives 0.5. `test_sal_prefix_stripped`.
- **Class:** `AbsCensusAdapter`.

### Task 8: `abs_erp` (ABS Estimated Resident Population, SA2)

- **Source:** the ABS Data API, dataflow `ABS_ANNUAL_ERP_ASGS2021`, requested as SDMX-CSV (`Accept: application/vnd.sdmx.data+csv`). The `url` in `sources.yaml` is the full data query filtered to the SA2 region type and total persons; take the dimension codes from the dataflow's structure (`…/rest/dataflow/ABS/ABS_ANNUAL_ERP_ASGS2021?references=all`).
- **Also create** the shared `adapters/abs_sdmx.py`, with `read_sdmx_csv(content: bytes, required: list[str]) -> pd.DataFrame`. It requires `TIME_PERIOD`, `OBS_VALUE` and the region column.
- **Output:** `population` at `Period.year(TIME_PERIOD)`, as `GeoValue("SA2", code, …)`, allocated with `allocate`.
- **Test:** `test_erp_allocated_additively`: an SA2 of 1000 split 0.75/0.25 gives 750 and 250.
- **Class:** `AbsErpAdapter`.

### Task 9: `abs_building_approvals` (ABS Building Approvals by SA2, monthly)

- **Source:** the ABS Data API dataflow for building approvals by SA2 (ASGS 2021), found by searching the `…/rest/dataflow/ABS` listing for "Building Approvals" and "SA2". Filter the query to: measure = number of dwelling units, sector = total, building type = total residential, adjustment = original.
- **Output:** `building_approvals_dwellings` at `Period.month`, from SA2, additive.
- **Test:** `test_monthly_period_parsed`: `TIME_PERIOD` `2025-03` gives `Period.month(2025, 3)`.
- **Class:** `AbsBuildingApprovalsAdapter`.

### Task 10: `jsa_salm` (Jobs and Skills Australia Small Area Labour Markets, SA2)

- **Source:** use `discover_link` on `https://www.jobsandskills.gov.au/data/small-area-labour-markets`, with `link_pattern` matching the smoothed SA2 (ASGS 2021) xlsx.
- **Parse:** read the sheets for unemployment (persons) and labour force. The header row contains `SA2 Code`, and the quarter columns are labelled like `Dec-24`, which maps to `Period.quarter(2024, 4)`.
- **Output:** `unemployed_count` and `labour_force_count`, from SA2, additive. The unemployment rate is derived later, in scoring.
- **Test:** `test_quarter_label_parsing`. `test_suppressed_cells_skipped`: a `-` cell produces no GeoValue and isn't counted in `total`.
- **Class:** `JsaSalmAdapter`.

### Task 11: `nsw_vg_sales` (NSW Valuer General bulk sales)

- **Source:** the weekly URL template `https://www.valuergeneral.nsw.gov.au/__psi/weekly/{YYYYMMDD}.zip`, where the date is a Monday. By default it fetches the 4 most recent Mondays up to `today`; a 404 for the newest Monday is skipped because it isn't published yet. With `--years A-B`, it fetches `…/__psi/yearly/{YYYY}.zip`. Confirm both templates on the Valuer General's bulk data page and record them in `sources.yaml`. `row_count_tolerance = 0.5`, since weekly volumes swing.
- **Parse:**
  - Open nested zips recursively and read every `.DAT` file.
  - Keep the semicolon-delimited `B` records. The field order (current format) is: record type; district code; property id; sale counter; download datetime; property name; unit number; house number; street name; locality; post code; area; area type; contract date; settlement date; purchase price; zoning; nature of property; primary purpose; strata lot number; component code; sale code; % interest; dealing number.
  - Keep a record only if nature of property = `R`, price > 0, and % interest is empty or 100.
  - `is_strata` = the strata lot number is present.
  - Dates are `YYYYMMDD`.
- **Normalise:**
  1. Match each sale to a SAL with `matcher.match(locality, "NSW", postcode)`.
  2. Upsert all kept records into `data.nsw_sales`, including unmatched ones, which have a null `sal_code`.
  3. Find the affected months: from the earliest contract month in the batch to the latest contract month + 11, capped at the month of `today`.
  4. For each affected month M, compute from `data.nsw_sales` with SQL `percentile_cont(0.5)`, per SAL and dwelling type (house = not strata, unit = strata):
     - `median_sale_price_{house,unit}_12m` and `sales_count_{house,unit}_12m` over contract months M−11..M
     - `median_sale_price_{house,unit}_3m` over M−2..M
     - all at `Period.month(M)`, with `source_geography="SAL"`
  5. `matched` / `total` = matched sales / kept sales in this batch.
- **Tests:**
  - `test_filters_non_residential_and_partial_interest`
  - `test_strata_is_unit`
  - `test_rolling_12m_median_and_count` (DB): 5 house sales in SAL 10001, all within M−11..M, priced 1, 2, 3, 4 and 10 ×100k, give a 12m median of 300 000 and a count of 5; a sale in M−12 is excluded.
  - `test_unmatched_sale_stored_with_null_sal`
- **Class:** `NswVgSalesAdapter`.

### Task 12: `nsw_rent` (NSW Rent and Sales Report, postcode)

- **Source:** use `discover_link` on the DCJ Rent and Sales Report page (`https://dcj.nsw.gov.au/about-us/families-and-communities-statistics/housing-rent-and-sales/rent-and-sales-report.html`), with `link_pattern` matching the rent tables xlsx.
- **Parse:** read the postcode sheet. The header row contains `Postcode`. Use dwelling types `Total`, `House` and `Flat/Unit`, with bedrooms `Total`, and the latest quarter's median weekly rent and new bonds lodged columns. Use every quarter's columns present in the file, mapping the quarter labels to `Period.quarter`.
- **Output:** from POA, allocated:
  - `median_weekly_rent_all_q` from Total, `median_weekly_rent_house_q` from House, `median_weekly_rent_unit_q` from Flat/Unit (all intensive)
  - `bonds_lodged_q` from Total (additive)
- **Test:** `test_suppressed_rent_skipped`: `s` produces no GeoValue. `test_rent_intensive_across_postcodes`: values 500 and 700 with weights 100/300 give 650.
- **Class:** `NswRentAdapter`.

### Task 13: `vic_vg_medians` (Victorian Valuer-General suburb medians)

- **Source:** use `discover_link` on `https://www.land.vic.gov.au/valuations/resources-and-reports/property-sales-statistics` for the quarterly "house by suburb" and "unit by suburb" files.
- **Parse:** the header row contains `Suburb`. Use the latest quarter's median and the 12-month median, plus the number of sales. **If the downloaded file has no number-of-sales column, stop and report to the owner** before writing the adapter, because the spec's thin-market rule needs counts.
- **Output:** `median_sale_price_{house,unit}_3m` (quarter median) and `median_sale_price_{house,unit}_12m` and `sales_count_{house,unit}_12m`, at `Period.month` of the quarter's last month, matched with `matcher.match(suburb, "VIC")` and `source_geography="SAL"`.
- **Test:** `test_vic_quarter_maps_to_last_month`: Q3 2025 maps to `Period.month(2025, 9)`. `test_unmatched_vic_suburb_counted`.
- **Class:** `VicVgMediansAdapter`.

### Task 14: `vic_dffh_rental` (Victorian DFFH Rental Report, moving annual rents by suburb group)

- **Source:** use `discover_link` on `https://www.dffh.vic.gov.au/publications/rental-report` for the "Moving annual rents by suburb" xlsx.
- **Parse:** read the sheet `All properties`. There are two header rows: quarter labels (e.g. `Sep 2025`), then `Count`/`Median` pairs. Use every `Median` column. The suburb group label is split on `-` into suburb names.
- **Output:** `median_weekly_rent_all_q`, with `source_geography="DFFH_GROUP"`. Each matched member suburb (`matcher.match(name, "VIC")`) gets the group's value. `total` = the number of member names, and `matched` = the number that matched.
- **Test:** `test_group_value_applied_to_each_member`: "Albert Park-Middle Park-West St Kilda" gives 3 observations with the same value.
- **Class:** `VicDffhRentalAdapter`.

---

### Task 15: CI, schedules, and runbook

**Files:**
- Create: `.github/workflows/pipeline-ci.yml`, `pipeline-weekly.yml`, `pipeline-monthly.yml`, `pipeline-manual.yml`
- Create: `pipeline/README.md`

**Interfaces:**
- Consumes: the CLI from Task 6 and the adapter ids from Tasks 7–14.

- [ ] **Step 1: `pipeline-ci.yml`.** Runs on pull requests and pushes that touch `pipeline/**` or `supabase/**`. It uses a service container `postgis/postgis:16-3.4`, sets up uv with Python 3.12, and runs `uv run ruff check` and `uv run pytest`, with `TEST_DATABASE_URL` pointing at the service.
- [ ] **Step 2: Scheduled workflows.** Each job runs `uv run python -m propapp_pipeline run <source>`, with `DATABASE_URL`, `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from repository secrets. A failed job triggers GitHub's standard failure email to the repo owner, which is the alert.

| Workflow | Trigger | Sources |
|---|---|---|
| `pipeline-weekly.yml` | `cron: "17 20 * * 1"` (Tue 06:17 AEST) | `nsw_vg_sales` |
| `pipeline-monthly.yml` | `cron: "23 19 3 * *"` | `abs_erp`, `abs_building_approvals`, `jsa_salm`, `nsw_rent`, `vic_vg_medians`, `vic_dffh_rental` (matrix, `fail-fast: false`) |
| `pipeline-manual.yml` | `workflow_dispatch` with input `command` (e.g. `run abs_census`, `run nsw_vg_sales --years 2015-2025`, `load-geo`) | any |

- [ ] **Step 3: Validate the workflows.** Run `actionlint` on `.github/workflows/`. Expected: no errors.
- [ ] **Step 4: `pipeline/README.md` runbook.** It covers:
  - Running tests locally with the docker command from Task 1.
  - Required secrets.
  - First deployment, in this order:
    1. Create the Supabase project.
    2. Apply migrations with `supabase db push`.
    3. Set the secrets.
    4. Run `load-geo`.
    5. Run `abs_census`.
    6. Run `nsw_vg_sales --years 2015-2025` for the backtest history.
    7. Run each remaining source once.
  - What to do when a run fails with `SourceLayoutError`: update the parser or the `link_pattern`, and add a fixture for the new layout.
- [ ] **Step 5: Commit.** `git commit -m "ci(pipeline): tests, schedules, runbook"`
