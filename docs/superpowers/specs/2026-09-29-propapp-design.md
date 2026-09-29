# PropApp — Design Spec

- **Date:** 2026-09-29
- **Status:** Draft — awaiting review
- **Scope:** Whole-product design. Implementation is split into four sub-projects (below), each getting its own implementation plan, built in order.

## 1. Summary

PropApp is a commercial SaaS that helps Australian property investors shortlist suburbs. Every suburb in Australia gets a national **fundamentals score**; where free price/rent data exists (NSW and VIC at launch) it also gets a **market score**. Every suburb shows a **coverage badge** stating which layers its score is built from. The product launches on free public data only, behind swappable source adapters so paid data can be added later without redesign.

### Agreed decisions

| Decision | Choice |
|---|---|
| Product | Commercial SaaS for property investors, similar in purpose to boomscore.com.au |
| Data budget at launch | Free data only; source adapters make paid sources a drop-in |
| Coverage | All of Australia |
| Score structure | Two layers: national fundamentals + market layer where available, with coverage badge |
| Team | Primarily the owner with Claude; favour managed services and few moving parts |
| Architecture | Supabase (Postgres + PostGIS) + Python batch pipeline on GitHub Actions + Next.js on Vercel + Stripe |
| Scoring method | Transparent weighted percentile model, backtested on NSW history. ML prediction deferred. |
| Mobile | Out of v1. A later Expo app would reuse the same Supabase backend. |

### Success criteria

1. Every Australian SAL suburb has a fundamentals score; NSW and VIC suburbs with sufficient sales also have a market score.
2. The NSW backtest shows a positive rank correlation between score and subsequent 12–24 month median price growth on held-out years, and the top decile outgrows the median suburb. The results are published in summary on the landing page.
3. Every score is explainable: the suburb page lists the factors that drove it and when each source was last refreshed.
4. Users can sign up, start a trial, pay, and be correctly limited by plan without manual intervention.

## 2. Sub-projects and build order

1. **Data pipeline:** ingests, normalises and stores all source data.
2. **Scoring engine:** turns observations into versioned, explainable scores, plus a backtest.
3. **Web app:** finder, suburb pages, compare, map, watchlist and alerts.
4. **Accounts and billing:** auth, plans, Stripe and entitlements.

Each depends on the one before it. Implementation planning starts with sub-project 1.

## 3. Architecture overview

```
 Public data sources ──► Python adapters (GitHub Actions cron)
                              │  raw files ──► Supabase Storage (immutable, dated)
                              ▼
                    Supabase Postgres + PostGIS
                    suburbs · observations · ingestion_runs
                              │
                              ▼
                    Scoring job (Python, after each ingest)
                    scores · score_factors · model versions
                              │  read-only views / RPC
                              ▼
                    Next.js (Vercel, ISR) ◄──► Supabase Auth
                              │
                              ▼
                           Stripe (Checkout, Portal, webhooks)
```

All persistent state lives in one Postgres database. Python is used for data work and TypeScript for the app. The two meet only at database tables and views.

## 4. Data pipeline

### 4.1 Geographic spine

- The canonical unit is ABS **Suburbs and Localities (SAL), ASGS Edition 3 (2021)**, stored in `suburbs` (`sal_code` PK, `name`, `state`, `geom` as a PostGIS MultiPolygon, `area_sqkm`).
- Data published at other geographies (SA2, postcode/POA) is allocated to SAL using ABS correspondence files, weighted by population where available and by area otherwise.
- Every allocated value records its `source_geography` so precise and estimated values can be told apart.

### 4.2 Adapter contract

Each source is one Python module that implements:

1. `fetch()`: downloads the source and stores the unmodified file in Supabase Storage under `raw/<source>/<YYYY-MM-DD>/`.
2. `parse(raw)`: produces typed rows.
3. `normalise(rows)`: produces rows for `observations`.

`observations` is long-format:

| Column | Notes |
|---|---|
| `suburb_code` | FK → `suburbs.sal_code` |
| `metric` | Controlled vocabulary, e.g. `median_sale_price_house`, `population`, `building_approvals` |
| `period` | Period start date and granularity (month / quarter / year) |
| `value` | numeric |
| `source` | adapter id |
| `source_geography` | `SAL`, `SA2`, `POA`, … |
| `ingested_at` | timestamp |

The unique key is (`source`, `metric`, `suburb_code`, `period`). Loads are upserts, so re-runs are idempotent. The scoring engine reads only `observations` and never touches source-specific tables.

### 4.3 v1 sources

| Source | Layer | Native geography | Cadence |
|---|---|---|---|
| ABS Census 2021 (median household income, age, tenure/owner-occupier share, household size) | Fundamentals | SAL | 5-yearly |
| ABS Regional Population (ERP) | Fundamentals | SA2 | Annual |
| ABS Building Approvals | Fundamentals | SA2 | Monthly |
| Jobs and Skills Australia Small Area Labour Markets | Fundamentals | SA2 | Quarterly |
| NSW Valuer General Bulk Property Sales Information | Market | Address → SAL | Weekly |
| NSW Rent and Sales Report (rental bonds) | Market | Postcode | Quarterly |
| VIC Valuer-General median prices | Market | Suburb | Quarterly |
| VIC DFFH Rental Report | Market | Suburb group | Quarterly |

Infrastructure project data is out of v1 because there is no clean national free dataset.

### 4.4 Scheduling, logging and quality checks

- Each adapter has its own GitHub Actions schedule, matched to its cadence.
- Each run writes an `ingestion_runs` row: source, start/end, status, row counts and error summary.
- Quality checks run before commit: row count within ±25% of the previous run (configurable per source), values within plausible ranges, and more than 98% of rows matched to a suburb. A failing check marks the run `failed`, keeps the previous data live, and sends an alert through a GitHub Actions failure notification.

### 4.5 Licensing and privacy

- NSW sales records include addresses. They are stored for aggregation only. Nothing below suburb level is ever exposed through the app.
- A `sources` table records each source's licence, attribution text and commercial-use status. Commercial-use terms for every source must be confirmed before public launch, and attribution is shown on suburb pages.

## 5. Scoring engine

### 5.1 Factors

| Layer | Factor | Direction |
|---|---|---|
| Fundamentals | Population growth, 3-year CAGR | Higher is better |
| Fundamentals | Building approvals per 1,000 dwellings (supply pressure), trailing 12 months | Lower is better |
| Fundamentals | Median household income | Higher is better |
| Fundamentals | Unemployment rate, level and 12-month change | Lower / falling is better |
| Fundamentals | Owner-occupier share | Higher is better |
| Market | 12-month median price growth | Higher is better |
| Market | Momentum: annualised 3-month growth vs 12-month growth | Higher is better |
| Market | Gross rental yield (median annual rent / median price) | Higher is better |
| Market | 12-month rent growth | Higher is better |
| Market | 12-month change in sales volume | Higher is better |

Vacancy rate and days on market are excluded in v1 because no free national or state source provides them.

### 5.2 Normalisation and thresholds

- Factor values are winsorised at the 1st and 99th percentiles, then converted to percentile ranks from 0 to 100, inverted where lower is better.
- Fundamentals factors are ranked against all scored suburbs nationally. Market factors are ranked against suburbs that have market data.
- **Thin markets:** a suburb with fewer than 20 sales in the trailing 12 months gets no market layer.

### 5.3 Combination

- Layer score = weighted mean of that layer's factor percentiles. Weights live in a versioned config file (`scoring/weights/vN.yaml`).
- Missing factors are handled by reweighting the rest proportionally. If more than 30% of a layer's weight is missing, that layer is null for the suburb.
- **PropApp score** = fundamentals score when there is no market layer, or 0.5 × fundamentals + 0.5 × market when both exist.
- The coverage badge has three values: `Fundamentals only`, `Fundamentals + Market`, `Insufficient data`. The last one applies when the fundamentals layer is null.
- The finder can rank on the fundamentals score alone for a like-for-like national comparison.

### 5.4 Outputs and explainability

- `scores`: `suburb_code`, `model_version`, `as_of`, `propapp_score`, `fundamentals_score`, `market_score`, `coverage`.
- `score_factors`: per suburb, per factor: raw value, percentile, weight, and contribution to the layer score.
- "Top drivers" and "watch-outs" are the three highest and three lowest weighted contributions, rendered from templates in plain English.
- All historical score runs are retained to power score-history charts.
- The scoring job runs automatically after any successful ingestion and can also be triggered manually.

### 5.5 Backtest

- Using NSW sales history, scores are recomputed **as of past dates**, using only observations whose `period` ends on or before that date.
- The outcome measure is median price growth over the following 12 and 24 months.
- The metrics are Spearman rank correlation between score and outcome, and the growth of the top-decile suburbs vs the median suburb.
- Weights are tuned on a training span of years and evaluated on held-out later years. Only held-out results are reported.
- Known limitation: Census and population figures get revised after release, so the backtest uses current releases and may slightly overstate what was knowable at the time. This is documented alongside the published results.

### 5.6 Compliance

Scores are presented as **general information, not financial product advice**. Disclaimers appear on the landing page, on suburb pages, and at sign-up. A legal review of AFSL / general-advice exposure is required before accepting payments.

## 6. Web app

### 6.1 Stack and rendering

- Next.js (App Router) on Vercel, with Supabase JS for auth and data.
- Suburb and landing pages use ISR, revalidated after each scoring run and at least daily. Public suburb pages are indexable and are the primary organic acquisition channel.

### 6.2 Pages

1. **Landing:** explains the score and methodology, and shows the backtest summary.
2. **Suburb finder:** a table of all suburbs with filters (state, median price range, gross yield, score range, coverage), sortable by PropApp or fundamentals score. Filters can be saved as named searches.
3. **Suburb page:**
   - PropApp, fundamentals and market scores, with the coverage badge
   - Top drivers and watch-outs
   - Score history chart
   - Key figures: median price, gross yield, population growth, supply pressure
   - Small map
   - Sources with their last-refreshed dates and attribution
4. **Compare:** up to 4 suburbs side by side, factor by factor.
5. **Map explorer:** MapLibre GL choropleth of scores. Suburb boundaries are simplified and pre-built as static vector tiles by the pipeline, hosted in Supabase Storage and regenerated after each scoring run.
6. **Watchlist and alerts:** save suburbs, and receive an email when a suburb's PropApp score changes by 5 or more points between scoring runs.
7. **Account:** profile, plan and billing (see §7).

### 6.3 Data access

- The app reads only through dedicated Postgres views and RPC functions, never raw tables.
- Row-level security protects user-owned tables (`watchlists`, `saved_searches`, `suburb_views`).
- Plan limits are enforced server-side in route handlers and server components, and in RLS via `get_entitlements`. They are never enforced only in the UI.

### 6.4 Error and empty states

- A stale-data banner appears when a source's latest successful run is older than 1.5× its expected cadence.
- A missing market layer shows its reason: "fewer than 20 sales in 12 months" or "no market data for this state yet".
- Alert email failures are logged and retried up to 3 times.

### 6.5 Testing

- Playwright end-to-end tests: search and filter, open a suburb page, compare, add to watchlist, plan-gated views.
- Unit tests for formatting and entitlement checks.
- A seeded test database containing a small fixed set of real suburbs covering all three coverage states.

### 6.6 Out of v1

Mobile app, individual property valuations, portfolio tracking, and AI chat.

## 7. Accounts and billing

### 7.1 Authentication

- Supabase Auth with email magic link and Google sign-in.
- Sign-up requires accepting the Terms, Privacy Policy and the general-information disclaimer. The accepted version and timestamp are stored.

### 7.2 Plans

| Capability | Free | Pro |
|---|---|---|
| Suburb finder | All suburbs; scores and ranks of the top 50 by the current sort are blurred | Full |
| Suburb page | Headline + fundamentals score; market detail, drivers and history for 5 distinct suburbs per billing month | Unlimited, full |
| Compare | — | Up to 4 suburbs |
| Map explorer | Coarse score bands (5 bands) | Full-resolution scores |
| Watchlist | Up to 3 suburbs, no alerts | Unlimited, with email alerts |
| Saved searches | — | Yes |
| CSV export of finder results | — | Yes |

For Free users, the "billing month" for view counts is the calendar month.

**Default pricing (owner to confirm before launch):** Pro at A$39/month or A$349/year, GST-inclusive, with a 7-day free trial. A buyer's-agent tier is deferred until customers ask for it.

### 7.3 Payments

- Stripe Checkout for purchase and Stripe Customer Portal for plan changes and cancellation. No card data touches PropApp.
- Stripe webhooks update the `subscriptions` table. Handlers verify signatures and are idempotent on Stripe event ID.
- Stripe Tax handles GST. The business needs an ABN, and GST registration once over the threshold.

### 7.4 Entitlements

A single Postgres function, `get_entitlements(user_id)`, maps plan and subscription status to limits. It is the only place plan rules are defined, and it is used by both server code and RLS policies.

### 7.5 Failure handling

- **Failed payment:** Stripe automatically retries. The user keeps Pro for a 7-day grace period, then drops to Free.
- **Downgrade:** watchlists and saved searches are retained. Items over the Free limits become read-only, and nothing is deleted.

### 7.6 Privacy

- The app follows the Australian Privacy Principles and stores only the minimum personal data: email, name and plan.
- Account deletion removes all user data and cancels any Stripe subscription.

### 7.7 Testing

- Stripe test-mode runs of the full cycle: trial → paid → failed payment → grace → downgrade → upgrade.
- Recorded webhook payloads are replayed to verify idempotency.
- Unit tests for `get_entitlements` across every plan and status.

## 8. Risks and open items

| Item | Owner / when |
|---|---|
| Confirm commercial-use licence terms for every v1 source | Before public launch |
| Legal review of general-advice positioning and disclaimers | Before accepting payments |
| Confirm Pro pricing and free-tier limits | Before billing sub-project |
| Market layer covers only NSW/VIC; competitors with paid data will be stronger elsewhere | Accepted for v1; revisit with a paid-data adapter |
| Backtest only possible where sales history exists (NSW) | Accepted; documented with published results |
