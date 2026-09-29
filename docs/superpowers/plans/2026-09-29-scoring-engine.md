# Scoring Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `data.observations` into versioned, explainable suburb scores (a fundamentals layer, a market layer, and a blended PropApp score with a coverage badge), refresh them after every ingestion, and backtest the weights against NSW sales history.

**Architecture:** A `scoring` subpackage inside the existing `pipeline/` package:
- It loads observations once into a pandas frame and takes a point-in-time view for any `as_of` date.
- It computes raw factor values, converts them to percentile ranks, and combines them with weights from a versioned YAML file.
- It writes `scores` and `score_factors` in one transaction.

The backtest reuses the same factor code at past dates. Only the weights change between tuning candidates, so percentiles are computed once per date.

**Tech Stack:** Python 3.12, pandas, numpy, psycopg 3, PyYAML, pytest, the existing Postgres 16 + PostGIS schema, and GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-29-propapp-design.md` (§5 is the part this plan implements; §4 describes the observations it reads). The data pipeline this builds on is in `pipeline/` and `docs/superpowers/plans/2026-09-29-data-pipeline.md`.

## Global Constraints

- Factor keys, layers and directions. These are the complete v1 set:

| Layer | Key | Direction |
|---|---|---|
| fundamentals | `population_growth_3y` | higher |
| fundamentals | `supply_pressure` | lower |
| fundamentals | `median_household_income` | higher |
| fundamentals | `unemployment_rate` | lower |
| fundamentals | `unemployment_change` | lower |
| fundamentals | `owner_occupier_share` | higher |
| market | `price_growth_12m` | higher |
| market | `momentum` | higher |
| market | `gross_yield` | higher |
| market | `rent_growth_12m` | higher |
| market | `sales_volume_change` | higher |

- **Normalisation:** winsorise at the 1st and 99th percentiles, then percentile rank = (average rank − 1) / (n − 1) × 100. The rank is 50 when n = 1, and 100 − rank for `lower` factors. Fundamentals are ranked against every suburb with a value; market factors only against suburbs eligible for the market layer.
- **Market eligibility:** a suburb needs at least **20** sales (house + unit) in the trailing 12 months, and its latest market month must be no more than **6 months** before `as_of`. Otherwise it has no market layer.
- **Combination:** layer score = Σ wᵢpᵢ / Σ wᵢ over the factors present. A layer is null if more than **30%** of its weight is missing. PropApp score = fundamentals where there's no market layer, otherwise **0.5 × fundamentals + 0.5 × market**.
- **Coverage values:** `fundamentals_market`, `fundamentals`, `insufficient` (the last when the fundamentals layer is null; its PropApp score is null).
- **Point in time:** an observation is usable at `as_of` only if its period **ends** on or before `as_of`.
  - Month periods end on their last day, quarters on the quarter's last day, years on 31 December.
  - A backtest can use later observations only to compute outcomes.
- **Weights:** stored at `pipeline/scoring/weights/v<N>.yaml`. `model_version` is the file stem (`v1`). The weights in each layer must sum to 1, within 1e-9.
- **Tables:** all scoring tables live in schema `data`, with no API grants, like the pipeline tables.
- **Backtests never write to `scores` or `score_factors`.**
- Secrets come from the environment only, as in the pipeline.
- **Out of scope** (web app sub-project): showing disclaimers (spec §5.6), app-facing views over `scores`, and rendering the score history.

## Review Focus

1. **Partial coverage.** Examples: a VIC suburb with a market layer but no JSA unemployment data, or a remote suburb missing ERP. Expected: the remaining factors are reweighted, and the layer is null only above 30% missing weight. Test: Task 6 `test_missing_weight_threshold`.
2. **Zero or missing bases for growth factors** (population 0 three years ago, no median 12 months ago, labour force 0). Expected: the factor is missing for that suburb, never inf or NaN, and nothing downstream crashes. Tests: Task 4 `test_growth_with_zero_base_is_missing`, Task 5 `test_price_growth_needs_prior_year`.
3. **Stale market data**, e.g. a VIC file that stops updating. Expected: no market layer once the latest market month is more than 6 months old, and the coverage drops to `fundamentals`. Test: Task 5 `test_stale_market_not_eligible`.
4. **The same metric from two sources for one suburb** (e.g. `median_weekly_rent_all_q` from `nsw_rent` and `vic_dffh_rental` near a border). Expected: the latest period wins, ties go to the alphabetically first source, and the result is the same on every run. Test: Task 3 `test_latest_value_prefers_newest_then_source`.
5. **Re-scoring the same `as_of` and model version.** Expected: the rows are replaced with no duplicates, and a backtest writes no `scores` rows. Tests: Task 8 `test_rescore_replaces`, Task 9 `test_backtest_does_not_write_scores`.

---

## File Structure

```
supabase/migrations/20260930000100_scoring_schema.sql
pipeline/scoring/weights/v1.yaml
pipeline/src/propapp_pipeline/scoring/
  __init__.py
  factors.py        # FACTORS registry: key, layer, direction
  weights.py        # Weights model + loader/validator
  observations.py   # load_observations, period_end, point-in-time helpers
  fundamentals.py   # fundamentals raw factor values
  market.py         # market raw factor values + eligibility
  combine.py        # winsorise/percentile, layer scores, contributions, coverage
  explain.py        # plain-English drivers / watch-outs
  engine.py         # score_as_of (pure) + run_scoring (DB write, score_runs log)
  backtest.py       # outcomes, metrics, evaluate, tune, persist results
pipeline/tests/scoring/…   # mirrors the modules
```

Modified: `pipeline/src/propapp_pipeline/cli.py` (new `score` and `backtest` commands), `.github/workflows/pipeline-{weekly,monthly,manual}.yml`, `pipeline/README.md`.

---

### Task 1: Scoring schema

**Files:**
- Create: `supabase/migrations/20260930000100_scoring_schema.sql`
- Modify: `pipeline/tests/conftest.py`, adding the new tables to the truncate list
- Test: `pipeline/tests/scoring/test_schema.py`

**Interfaces:**
- Produces these tables in schema `data`:

| Table | Columns |
|---|---|
| `score_runs` | `id bigserial pk`, `model_version text`, `as_of date`, `started_at timestamptz default now()`, `finished_at timestamptz`, `status text check in ('running','success','failed')`, `suburbs_scored int`, `error text` |
| `scores` | `suburb_code text fk → suburbs`, `model_version text`, `as_of date`, `run_id bigint fk → score_runs`, `propapp_score double precision null`, `fundamentals_score double precision null`, `market_score double precision null`, `coverage text check in ('fundamentals_market','fundamentals','insufficient')`, `top_drivers text[]`, `watch_outs text[]`; pk (`suburb_code`,`model_version`,`as_of`) |
| `score_factors` | `suburb_code`, `model_version`, `as_of`, `factor text`, `layer text check in ('fundamentals','market')`, `raw_value double precision`, `percentile double precision`, `weight double precision`, `contribution double precision`; pk (`suburb_code`,`model_version`,`as_of`,`factor`); fk (`suburb_code`,`model_version`,`as_of`) → `scores` on delete cascade |
| `backtest_results` | `id bigserial pk`, `run_at timestamptz default now()`, `model_version text`, `horizon_months int check in (12,24)`, `split text check in ('train','holdout')`, `spearman double precision`, `top_decile_excess double precision`, `n_dates int`, `mean_suburbs double precision` |

- [ ] **Step 1: Write the failing tests.** `test_scoring_tables_exist` checks that the four tables above exist in `data`. `test_score_factors_cascade` checks that deleting a `scores` row removes its `score_factors`.
- [ ] **Step 2: Run them to check they fail.** `cd pipeline && uv run pytest tests/scoring/test_schema.py -v` → FAIL
- [ ] **Step 3: Write the migration and extend the truncate list in `conftest.py`.**
- [ ] **Step 4: Run them to check they pass.** Also run the whole suite: `uv run pytest -q` → all pass.
- [ ] **Step 5: Commit.** `git commit -m "feat(scoring): scores, factors, runs and backtest tables"`

---

### Task 2: Factor registry and weights

**Files:**
- Create: `scoring/__init__.py`, `scoring/factors.py`, `scoring/weights.py` (under `pipeline/src/propapp_pipeline/`), and `pipeline/scoring/weights/v1.yaml`
- Test: `pipeline/tests/scoring/test_weights.py`

**Interfaces:**
- Produces:
  - `Factor(key: str, layer: Literal["fundamentals","market"], direction: Literal["higher","lower"])`
  - `FACTORS: dict[str, Factor]`, exactly the Global Constraints table
  - `Weights(model_version: str, fundamentals: dict[str, float], market: dict[str, float], blend_fundamentals: float, max_missing_weight: float, thin_market_min_sales: int, market_max_age_months: int)`
  - `load_weights(path: Path) -> Weights`, which raises `ValueError` if:
    - a key isn't in `FACTORS`, or is in the wrong layer
    - a layer's weights don't sum to 1 (±1e-9)
    - any weight is negative
  - `WEIGHTS_DIR = <repo>/pipeline/scoring/weights`
- `v1.yaml` has these starting weights, before any backtest:
  - **fundamentals:** `population_growth_3y` 0.30, `supply_pressure` 0.20, `median_household_income` 0.15, `owner_occupier_share` 0.15, `unemployment_rate` 0.10, `unemployment_change` 0.10
  - **market:** `price_growth_12m` 0.25, `gross_yield` 0.25, `momentum` 0.20, `rent_growth_12m` 0.15, `sales_volume_change` 0.15
  - **other settings:** `blend_fundamentals: 0.5`, `max_missing_weight: 0.30`, `thin_market_min_sales: 20`, `market_max_age_months: 6`

- [ ] **Step 1: Write the failing tests**

```python
def test_v1_loads():
    w = load_weights(WEIGHTS_DIR / "v1.yaml")
    assert w.model_version == "v1" and w.thin_market_min_sales == 20
    assert set(w.fundamentals) | set(w.market) == set(FACTORS)

def test_weights_must_sum_to_one(tmp_path): ...     # fundamentals sum 0.9 → ValueError "fundamentals"
def test_factor_in_wrong_layer_rejected(tmp_path): ...  # gross_yield under fundamentals → ValueError
```

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement `factors.py`, `weights.py` and `v1.yaml`.**
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(scoring): factor registry and versioned weights"`

---

### Task 3: Observations and point-in-time view

**Files:**
- Create: `pipeline/src/propapp_pipeline/scoring/observations.py`
- Test: `pipeline/tests/scoring/test_observations.py`

**Interfaces:**
- Consumes: `data.observations` (pipeline Task 1)
- Produces:
  - `period_end(start: date, granularity: str) -> date`
  - `load_observations(conn) -> pd.DataFrame`: one frame with the columns `suburb_code, metric, period_start (datetime64), granularity, period_end (datetime64), value, source`, loaded in a single query.
  - `as_of_view(obs: pd.DataFrame, as_of: date) -> pd.DataFrame`: the rows with `period_end <= as_of`. Then, for each (`suburb_code`, `metric`, `period_start`), it keeps one row: the alphabetically first `source`.
  - `latest(view, metric) -> pd.DataFrame`: indexed by `suburb_code`, with columns `period_start, value`. It gives each suburb's latest period of `metric`, with ties resolved by `as_of_view`.
  - `value_at(view, metric, period_start: pd.Series) -> pd.Series`: the value of `metric` at the given period start for each suburb (NaN if missing). Growth factors use it to look up the earlier value.

- [ ] **Step 1: Write the failing tests**

```python
def test_period_end():
    assert period_end(date(2025, 7, 1), "quarter") == date(2025, 9, 30)
    assert period_end(date(2024, 2, 1), "month") == date(2024, 2, 29)
    assert period_end(date(2021, 1, 1), "year") == date(2021, 12, 31)

def test_as_of_excludes_periods_ending_later(obs_frame):
    view = as_of_view(obs_frame, date(2025, 9, 29))     # a 2025-09 month row ends 09-30
    assert not ((view.metric == "median_sale_price_house_12m")
                & (view.period_start == "2025-09-01")).any()

def test_latest_value_prefers_newest_then_source(obs_frame):
    # 10001 rent: nsw_rent Q2 = 600, vic_dffh_rental Q2 = 650, nsw_rent Q1 = 580
    assert latest(as_of_view(obs_frame, date(2025, 12, 31)),
                  "median_weekly_rent_all_q").loc["10001", "value"] == 600

def test_load_observations_roundtrip(db_url): ...   # insert 2 rows via SQL; frame has period_end column
```

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement `observations.py`.** Load with `pd.read_sql`-style fetching through psycopg (no SQLAlchemy dependency). Use month arithmetic for `period_end`.
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(scoring): point-in-time observation views"`

---

### Task 4: Fundamentals factors

**Files:**
- Create: `pipeline/src/propapp_pipeline/scoring/fundamentals.py`
- Test: `pipeline/tests/scoring/test_fundamentals.py`

**Interfaces:**
- Consumes: `as_of_view`, `latest` and `value_at` (Task 3)
- Produces: `compute_fundamentals(view: pd.DataFrame) -> pd.DataFrame`, indexed by `suburb_code`, with one column per fundamentals key. A suburb has NaN wherever its inputs are missing or invalid.

| Key | Definition |
|---|---|
| `population_growth_3y` | Latest `population` year Y and year Y−3: (pop_Y / pop_{Y−3})^(1/3) − 1. NaN if pop_{Y−3} ≤ 0 or missing. |
| `supply_pressure` | Sum of `building_approvals_dwellings` over the 12 months ending at the suburb's latest approvals month, scaled by 12/n when 10 ≤ n < 12 months are present (NaN below 10), divided by the latest `dwellings_total` × 1000. NaN if dwellings ≤ 0. |
| `median_household_income` | Latest `median_household_income_weekly`. |
| `unemployment_rate` | Latest quarter: `unemployed_count` / `labour_force_count` × 100. NaN if labour force ≤ 0. |
| `unemployment_change` | `unemployment_rate` at the latest quarter minus the rate 4 quarters earlier. NaN if either is missing. |
| `owner_occupier_share` | Latest `owner_occupier_share`. |

- [ ] **Step 1: Write the failing tests.** Build a small observations frame with a helper `obs(rows)`.

```python
def test_population_growth_cagr():
    f = compute_fundamentals(view_of([("10001","population",2021,1000), ("10001","population",2024,1331)]))
    assert f.loc["10001","population_growth_3y"] == pytest.approx(0.10)

def test_growth_with_zero_base_is_missing():
    f = compute_fundamentals(view_of([("10001","population",2021,0), ("10001","population",2024,50)]))
    assert np.isnan(f.loc["10001","population_growth_3y"])

def test_supply_pressure_scales_partial_year():
    # 11 months × 10 approvals, dwellings 1000 → 110 × 12/11 / 1000 × 1000 = 120
    assert f.loc["10001","supply_pressure"] == pytest.approx(120)

def test_unemployment_rate_and_change():
    # Q4-2024 32/800 = 4.0%; Q4-2023 40/800 = 5.0% → change −1.0
    ...
```

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement `compute_fundamentals`** with vectorised pandas (group by suburb, never a per-suburb Python loop).
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(scoring): fundamentals factors"`

---

### Task 5: Market factors and eligibility

**Files:**
- Create: `pipeline/src/propapp_pipeline/scoring/market.py`
- Test: `pipeline/tests/scoring/test_market.py`

**Interfaces:**
- Consumes: Task 3 helpers, and `Weights.thin_market_min_sales` and `Weights.market_max_age_months` (Task 2)
- Produces: `compute_market(view, as_of: date, weights: Weights) -> MarketResult(values: pd.DataFrame, eligible: pd.Index, dwelling_type: pd.Series)`, where:
  - **L** is the suburb's latest month with `sales_count_house_12m` or `sales_count_unit_12m`.
  - The suburb is **eligible** when house + unit 12-month count at L ≥ `thin_market_min_sales`, **and** L is no more than `market_max_age_months` months before `as_of`'s month.
  - **Dominant type** (`house` or `unit`) is whichever has the larger 12-month count at L; a tie goes to `house`. The median metrics below use the dominant type.
  - `values` holds only eligible suburbs, one column per market key:

| Key | Definition |
|---|---|
| `price_growth_12m` | `median_sale_price_<t>_12m` at L / the same at L−12 months − 1 |
| `momentum` | (`median_sale_price_<t>_3m` at L / the same at L−3)^4 − 1 − `price_growth_12m` |
| `gross_yield` | Latest `median_weekly_rent_<t>_q` (falling back to `median_weekly_rent_all_q`) × 52 / `median_sale_price_<t>_12m` at L |
| `rent_growth_12m` | The same rent metric at its latest quarter Q / its value at Q−4 quarters − 1 |
| `sales_volume_change` | (house + unit 12-month count at L) / (the same at L−12) − 1. NaN if the earlier count is 0 |

  Any ratio whose base is missing or ≤ 0 is NaN.

- [ ] **Step 1: Write the failing tests**

```python
def test_thin_market_not_eligible(): ...            # 12 + 7 = 19 sales → not in eligible
def test_stale_market_not_eligible():               # L = 2025-01, as_of 2025-09-29 → 8 months old
    assert "10001" not in compute_market(view, date(2025, 9, 29), W).eligible
def test_dominant_type_and_growth():                # units 30, houses 25 → unit medians used
    # unit 12m median 500k now, 400k a year ago → 0.25
def test_price_growth_needs_prior_year(): ...       # no L−12 median → NaN, still eligible
def test_gross_yield_falls_back_to_all_rent():      # no unit rent; all rent 500/wk, 12m median 520k → 0.05
def test_momentum():                                # 3m 440k at L, 400k at L−3; 12m growth 0.25 → 1.1**4−1−0.25
```

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement `compute_market`.**
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(scoring): market factors and thin/stale market eligibility"`

---

### Task 6: Normalise and combine

**Files:**
- Create: `pipeline/src/propapp_pipeline/scoring/combine.py`
- Test: `pipeline/tests/scoring/test_combine.py`

**Interfaces:**
- Consumes: `FACTORS`, `Weights`
- Produces:
  - `percentiles(raw: pd.DataFrame) -> pd.DataFrame`: the same shape as `raw`, with each column winsorised at 1/99 and ranked per the Global Constraints (NaN stays NaN; a `lower` factor gets 100 − rank).
  - `combine(pct_fund: pd.DataFrame, pct_market: pd.DataFrame, weights: Weights) -> Combined`, where `Combined` has:
    - `scores: pd.DataFrame`, indexed by suburb (every suburb in `pct_fund` ∪ `pct_market`), with columns `fundamentals_score, market_score, propapp_score, coverage`
    - `factors: pd.DataFrame`, in long format with columns `suburb_code, factor, layer, percentile, weight, contribution`, for the factors present only. `weight` is the reweighted share within the layer (a suburb's weights in each layer sum to 1), and `contribution` = weight × percentile, so contributions sum to the layer score.
  - A suburb that appears only in `pct_market` (market data but no fundamentals) gets `coverage="insufficient"` and a null PropApp score.

- [ ] **Step 1: Write the failing tests**

```python
def test_percentile_rank_and_direction():
    p = percentiles(pd.DataFrame({"supply_pressure": [1.0, 2.0, 3.0]}, index=list("abc")))
    assert p["supply_pressure"].tolist() == [100.0, 50.0, 0.0]

def test_single_value_is_50(): ...
def test_winsorised_tails_tie(): ...                   # 200 values, top 1% tie at the top rank

def test_missing_weight_threshold():
    # fundamentals present: 0.30+0.20+0.15+0.10 = 0.75 → score; drop population too → 0.45 → null
    ...

def test_blend_and_coverage():
    # fund 80, market 40 → propapp 60, coverage fundamentals_market; fund only → propapp == fund
    ...

def test_contributions_sum_to_layer_score(): ...
```

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement `combine.py`.** Rank with `rank(method="average")`; winsorise with `clip` at `quantile(0.01)` and `quantile(0.99)`.
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(scoring): percentile normalisation and layer combination"`

---

### Task 7: Drivers and watch-outs

**Files:**
- Create: `pipeline/src/propapp_pipeline/scoring/explain.py`
- Test: `pipeline/tests/scoring/test_explain.py`

**Interfaces:**
- Consumes: `Combined.factors` (Task 6) and the raw values from Tasks 4–5
- Produces: `explain(factors: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame`, indexed by suburb, with columns `top_drivers: list[str]` and `watch_outs: list[str]`.
  - **Effect** = weight × (percentile − 50), where weight is the within-layer weight from `Combined.factors`.
  - **Drivers** are the up to 3 factors with the largest positive effect; **watch-outs** are the up to 3 with the most negative effect. Factors with an effect of 0 appear in neither list.
  - Text comes from one template per factor, filled with the raw value and the percentile, e.g.:
    - `population_growth_3y`: "Population grew {raw:.1%} a year over 3 years (higher than {pct:.0f}% of suburbs)"
    - `supply_pressure` (a `lower` factor, so its percentile is already inverted): "{raw:.0f} new dwellings approved per 1,000 homes in 12 months (less new supply than {pct:.0f}% of suburbs)"

  All 11 templates live in a `TEMPLATES` dict keyed by factor. A test checks that every factor has one and that each formats without error.

- [ ] **Step 1: Write the failing tests.** `test_every_factor_has_template`, `test_drivers_and_watch_outs_ordered` (3 positive and 2 negative effects give 3 drivers in effect order and 2 watch-outs), and `test_neutral_factor_excluded`.
- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement `explain.py`.**
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(scoring): plain-English drivers and watch-outs"`

---

### Task 8: Engine, persistence, and `score` command

**Files:**
- Create: `pipeline/src/propapp_pipeline/scoring/engine.py`
- Modify: `pipeline/src/propapp_pipeline/cli.py`
- Test: `pipeline/tests/scoring/test_engine.py`

**Interfaces:**
- Consumes: Tasks 2–7
- Produces:
  - `score_as_of(obs: pd.DataFrame, as_of: date, weights: Weights) -> ScoreResult(scores: pd.DataFrame, factors: pd.DataFrame)`. It is pure: it takes the view, computes fundamentals and market factors, then `percentiles` → `combine` → `explain`. `factors` gains a `raw_value` column.
  - `run_scoring(db_url: str, as_of: date, weights: Weights) -> int`:
    - It records a `score_runs` row (`running`, then `success`/`failed`) on its own autocommit connection.
    - In one transaction, it deletes existing `scores` for (`model_version`, `as_of`) (which cascades to their factors) and inserts the new ones with `COPY`.
    - It returns the number of suburbs scored and re-raises on failure after logging.
  - CLI: `python -m propapp_pipeline score [--as-of YYYY-MM-DD] [--weights v1]`. `--as-of` defaults to today, and `--weights` defaults to the highest-numbered `v*.yaml` in `WEIGHTS_DIR`. It exits 1 on failure. `score` only needs `DATABASE_URL`, so `Settings` gets a `database_only()` constructor that reads just that variable.

- [ ] **Step 1: Write the failing tests** (DB). Seed `suburbs` and a small `observations` set covering all three coverage states.

```python
def test_run_scoring_writes_scores_and_factors(db_url, seeded):
    n = run_scoring(db_url, date(2025, 12, 31), load_weights(WEIGHTS_DIR / "v1.yaml"))
    assert n == 3
    assert coverage(db_url) == {"10001": "fundamentals_market", "10002": "fundamentals",
                                "10003": "insufficient"}

def test_rescore_replaces(db_url, seeded):
    run_scoring(...); run_scoring(...)
    assert count(db_url, "scores") == 3 and count(db_url, "score_runs") == 2

def test_failed_scoring_keeps_previous_scores(db_url, seeded, monkeypatch): ...   # patch explain to raise
def test_cli_score_exit_codes(db_url, seeded, monkeypatch): ...
```

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement `engine.py`, the `score` CLI command and `Settings.database_only`.**
- [ ] **Step 4: Run the tests to check they pass.** `uv run pytest -q` → all pass
- [ ] **Step 5: Commit.** `git commit -m "feat(scoring): scoring engine, persistence and score command"`

---

### Task 9: Backtest and tuning

**Files:**
- Create: `pipeline/src/propapp_pipeline/scoring/backtest.py`
- Modify: `pipeline/src/propapp_pipeline/cli.py`
- Test: `pipeline/tests/scoring/test_backtest.py`

**Interfaces:**
- Consumes: `as_of_view`, `compute_fundamentals`, `compute_market`, `percentiles`, `combine` and `load_weights`
- Produces:
  - `backtest_dates(first_year: int, last_year: int) -> list[date]`: 30 June and 31 December of each year.
  - `outcomes(obs, as_of: date, dwelling_type: pd.Series, horizon_months: int) -> pd.Series`: per suburb, the growth of `median_sale_price_<type>_12m` from the as-of month L to L + horizon, using **all** observations (the future is allowed here only). NaN if either value is missing.
  - `rank_metrics(score: pd.Series, outcome: pd.Series) -> tuple[float, float, int]`:
    - Spearman correlation, computed as the Pearson correlation of the average ranks (no scipy).
    - Top-decile excess: the median outcome of the top 10% by score, minus the median outcome of all suburbs.
    - n: the number of suburbs with both values.
  - `evaluate(obs, dates, weights, horizon_months) -> list[DateMetrics]`. It scores only suburbs with **NSW** codes (SAL codes starting `1`), since sales history exists only there.
  - `tune(obs, train_dates, weights, samples: int = 200, seed: int = 7) -> Weights`:
    - Keeps the settings and draws per-layer Dirichlet(1) weights.
    - Picks the draw with the highest mean 12-month Spearman over `train_dates`.
    - Computes `percentiles` once per date and reuses them for every draw.
    - Returns the best draw as a new `Weights` with `model_version` = the next unused `vN`.
  - `run_backtest(db_url, first_year, last_year, holdout_from, weights, tune_samples: int | None) -> BacktestReport`:
    - Splits the dates into train (< `holdout_from`) and holdout.
    - If `tune_samples` is set, tunes on train and writes the tuned weights to `WEIGHTS_DIR/v<N>.yaml`.
    - Evaluates the chosen weights on both splits at 12 and 24 months.
    - Inserts 4 rows into `backtest_results` and writes a Markdown report to `pipeline/scoring/reports/<model_version>-backtest.md`. The report includes the §5.5 revision-lag limitation note.
  - CLI: `python -m propapp_pipeline backtest --years 2016-2024 --holdout-from 2022 [--weights v1] [--tune 200]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_rank_metrics_perfect_order():
    s = pd.Series(range(20), dtype=float); o = s * 0.01
    rho, excess, n = rank_metrics(s, o)
    assert rho == pytest.approx(1.0) and n == 20 and excess > 0

def test_outcomes_use_future_values(): ...          # L=2023-06 → value at 2024-06 used
def test_evaluate_uses_only_past_data(): ...        # a factor input dated after as_of changes nothing
def test_tune_is_deterministic_and_valid(): ...     # same seed → same weights; sums to 1 per layer
def test_backtest_does_not_write_scores(db_url, seeded_history, tmp_path, monkeypatch):
    run_backtest(db_url, 2022, 2023, 2023, W, tune_samples=None)
    assert count(db_url, "scores") == 0 and count(db_url, "backtest_results") == 4
```

- [ ] **Step 2: Run the tests to check they fail.** → FAIL
- [ ] **Step 3: Implement `backtest.py` and the `backtest` CLI command.** `run_backtest` takes a `reports_dir` and `weights_dir`, both defaulting to the repo paths, so tests can point them at `tmp_path`.
- [ ] **Step 4: Run the tests to check they pass.** → PASS
- [ ] **Step 5: Commit.** `git commit -m "feat(scoring): NSW backtest with held-out evaluation and weight tuning"`

---

### Task 10: Schedule scoring after ingestion, and runbook

**Files:**
- Modify: `.github/workflows/pipeline-weekly.yml`, `pipeline-monthly.yml`, `pipeline-manual.yml`, and `pipeline/README.md`

**Interfaces:**
- Consumes: the `score` and `backtest` CLI commands (Tasks 8–9)

- [ ] **Step 1: Weekly and monthly workflows.** Add a `score` job with:
  - `needs: ingest`
  - `if: ${{ !cancelled() }}`, so scoring still runs when one matrix source fails, using the data that did load
  - the same concurrency, permissions and secrets
  - the command `uv run python -m propapp_pipeline score`
- [ ] **Step 2: Manual workflow.** Update the input description to list `score`, `score --as-of 2025-12-31` and `backtest --years 2016-2024 --holdout-from 2022 --tune 200`.
- [ ] **Step 3: Validate the workflows.** Run `actionlint`. Expected: clean.
- [ ] **Step 4: README "Scoring" section.** It covers:
  - What the score is and where the weights live.
  - Running `score` by hand.
  - Running the first backtest (after the NSW backfill): `backtest --years 2016-2024 --holdout-from 2022 --tune 200`.
  - Reviewing `scoring/reports/v2-backtest.md` and committing `weights/v2.yaml` if the held-out Spearman is positive. The next scheduled `score` then uses `v2` automatically.
  - Where results are stored.
- [ ] **Step 5: Commit.** `git commit -m "ci(scoring): score after every ingestion; runbook"`
