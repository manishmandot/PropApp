# PropApp data pipeline

Ingests the v1 public data sources into Supabase Postgres, normalised to ABS Suburbs and
Localities (SAL). Design: `docs/superpowers/specs/2026-09-29-propapp-design.md` §4.
Plan: `docs/superpowers/plans/2026-09-29-data-pipeline.md`.

## How it works

Each source is an adapter in `src/propapp_pipeline/adapters/` with three steps:
`fetch` (download), `parse` (read the file) and `normalise` (turn rows into suburb
observations). `run_source` stores every raw file unchanged in the private Storage bucket
`raw`, converts SA2/postcode data to suburbs using mesh-block correspondences, runs the
quality checks, and upserts into `data.observations` in one transaction. Every run is
logged in `data.ingestion_runs`. Source URLs, licences and cadences live in `sources.yaml`.

Quality checks: at least one observation produced; row count within ±25% of the last
successful run (skipped for `nsw_vg_sales`, whose output size depends on which months a
batch touches); at least 98% of rows matched to a suburb; and every value inside its
metric's range. A failed check keeps the previous data live and exits with code 1.

NSW sales: sales under $10,000 or over $50,000,000 (nominal transfers, outliers) are
dropped individually, and dealings covering several properties are left out of medians
and counts. The weekly job re-fetches every weekly file from two weeks before its last
successful run, so a stretch of failed runs is caught up automatically once fixed.

## Running tests locally

```bash
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgis/postgis:16-3.4
cd pipeline
uv sync
uv run ruff check
uv run pytest            # uses TEST_DATABASE_URL, default postgresql://postgres:postgres@localhost:5432/postgres
```

## Secrets

Set these as GitHub repository secrets (and as environment variables to run locally):

| Name | Value |
|---|---|
| `DATABASE_URL` | Supabase Postgres connection string (session pooler or direct) |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (Storage writes); never commit it |

## First deployment

1. Create the Supabase project.
2. Apply migrations: `supabase link --project-ref <ref> && supabase db push`.
3. Set the three secrets above.
4. Raise the project's global file upload limit (Storage settings) to at least 1 GB.
   The Census DataPack and NSW yearly zips exceed the 50 MB default; the pipeline creates
   the `raw` bucket with a 1 GB limit, but the project limit caps it. This needs a paid
   Supabase plan.
5. Run the **pipeline-manual** workflow with each command below, in order:
   1. `load-geo`: loads suburbs and builds the SA2/postcode correspondences.
   2. `run abs_census`
   3. `run nsw_vg_sales --years 2015-2025`: sales history for the scoring backtest. This
      is long, so run it a few years at a time if it approaches the 3-hour job limit.
   4. `run abs_erp`, `run abs_building_approvals`, `run jsa_salm`, `run nsw_rent`,
      `run vic_vg_medians`, `run vic_dffh_rental`
6. From then on, **pipeline-weekly** (NSW sales, Tuesdays 06:17 AEST) and
   **pipeline-monthly** (everything else, on the 3rd) run automatically. The Census
   only changes every five years, so it runs by hand. Ingestion workflows share one
   concurrency group, so a long backfill and a scheduled run never overlap.
   GitHub pauses scheduled workflows after 60 days without repository activity;
   re-enable them from the Actions tab if that happens.

The source URLs and file layouts in `sources.yaml` and the parsers were written from
the publishers' documented formats without access to the live files. Expect the first
run of each source to confirm or correct them.

## When a run fails

GitHub emails the repository owner when a scheduled job fails. Look at the job log and at
`data.ingestion_runs.error`:

- **`SourceLayoutError`**: the publisher changed a column, sheet or link. Update the
  parser or the `link_pattern`/`url` in `sources.yaml`, add a test fixture in the new
  layout, and re-run.
- **`QualityError: row count …`**: the output size moved more than ±25%. Check whether
  the source really changed (for example, a new geography) before loosening
  `row_count_tolerance` on that adapter.
- **`QualityError: match rate …`**: too many rows didn't match a suburb. The log names
  the counts; usually new or renamed localities.
- **HTTP errors**: 5xx responses are retried automatically, so check whether the URL
  has moved.

The previous data stays live until a run succeeds.

## Scoring

`python -m propapp_pipeline score` scores every suburb from the loaded observations
(spec §5) and stores this month's snapshot in `data.scores` (factor detail in
`data.score_factors`, kept for the latest snapshot only). Every run is logged in
`data.score_runs`. The weekly and monthly workflows run it automatically after
ingestion; run it by hand from **pipeline-manual** with `score` (or
`score --cutoff 2025-12-31`).

Weights live in `scoring/weights/v<N>.yaml`; the newest version is used unless
`--weights` says otherwise. `v1` holds starting weights that no backtest has checked yet.

### First backtest

After the NSW sales backfill (`run nsw_vg_sales --years 2015-2025`) and the ABS sources
have loaded:

1. Run **pipeline-manual** with `backtest --years 2016-2024 --holdout-from 2022 --tune 200`.
2. Download the `scoring-output` artifact from the run. It holds
   `reports/v2-backtest.md` and the tuned `weights/v2.yaml`.
3. Read the report. Quote only the held-out rows. If the held-out 12-month Spearman
   is positive and better than v1's, commit `weights/v2.yaml` (and the report). The next
   scheduled `score` then uses v2.

The backtest only uses data once it would have been published (fixed release lags per
source), and training dates whose outcome window reaches into the held-out years are
left out. A `--tune` run reports the starting weights next to the tuned ones and writes
no new version when the starting weights win. It also reports market-layer coverage;
without NSW rent history the market layer is missing for almost every backtest suburb, so
market weights are not tuned and the results validate the fundamentals layer only.

### Known launch gap: market history builds up slowly

Two market sources load only their current release: VIC Valuer-General medians (one
quarter per file) and NSW rents (one quarter per file). Price growth and sales-volume
change need the value from 12 months earlier, and rent growth needs rent from a year
earlier. So at launch, VIC suburbs show **Fundamentals only** for about five quarters,
and NSW rent growth is missing for four quarters. Thinner NSW suburbs may also drop to
Fundamentals only. Backfilling the publishers' archived quarterly files would close the
gap sooner; it isn't built yet.

Results are also stored in `data.backtest_results`. The report lists the known
limitations: the fixed 2021 Census, data revisions, and NSW late lodgements.

## Web app hooks

After scoring, the weekly and monthly workflows also:

- rebuild the map tiles (`build-tiles`: suburbs with 5-band scores as PMTiles in the
  public Storage bucket `tiles`, using `tippecanoe`)
- ask the website to refresh (`POST $WEB_URL/api/revalidate`, when the `WEB_URL` and
  `REVALIDATE_SECRET` secrets are set)

`score` also refreshes the `api.suburbs` materialized view the website reads. See
`web/README.md` for the web deployment.

## Before public launch

Every source except the ABS ones has `commercial_use: pending` in `sources.yaml`. Confirm
each licence allows commercial use and set it to `confirmed` (spec §4.5).
