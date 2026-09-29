# PropApp web app

The public website: landing page, suburb finder, suburb pages, compare and the map
(spec §6). Plan: `docs/superpowers/plans/2026-09-29-web-app.md`.

Next.js (App Router) reads score data **on the server only**, as the read-only database
role `web_reader`, which can select from the `api` views and nothing else. Pages are
cached for a day and refreshed straight after every scoring run. Sign-in, watchlists,
saved searches, alerts and plan limits come with the accounts sub-project; every plan
check already goes through `lib/entitlements.ts`.

## Running locally

```bash
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgis/postgis:16-3.4
cd web
npm install
npx vitest run          # unit + database tests (builds throwaway databases)
npx playwright test     # end-to-end: seeded and empty databases, two builds
```

To click around, create a database from `supabase/migrations/*.sql` plus
`tests/seed.sql`, set `DATABASE_URL` to it as `web_reader`, and run `npm run dev`.
`tests/setup-db.ts` shows the steps.

## Environment variables

| Name | Value |
|---|---|
| `DATABASE_URL` | `web_reader` connection string through the Supabase pooler (see below) |
| `REVALIDATE_SECRET` | Long random string; the pipeline sends it to refresh the site |
| `NEXT_PUBLIC_TILES_URL` | Public URL of `suburbs.pmtiles`, printed by the pipeline's `build-tiles` |
| `NEXT_PUBLIC_SITE_URL` | The site's canonical URL, e.g. `https://propapp.com.au` |

## Deploying

1. **Database login.** The `api` migration creates `web_reader` without a password. In
   the Supabase SQL editor run:

   ```sql
   alter role web_reader with login password '<a long random password>';
   ```

   Use the pooler connection string with user `web_reader.<project-ref>` as
   `DATABASE_URL`.
2. **Map tiles.** Run the pipeline's `build-tiles` once (**pipeline-manual** with
   `build-tiles`). It prints the public URL of `tiles/suburbs.pmtiles`; use it as
   `NEXT_PUBLIC_TILES_URL`.
3. **Vercel.** Import the repository, set the project root to `web/`, and add the four
   variables above. The first build reads the database, so `DATABASE_URL` must work at
   build time.
4. **Refresh after scoring.** Add GitHub secrets `WEB_URL` (the site URL) and
   `REVALIDATE_SECRET` (same value as in Vercel). The weekly and monthly pipeline
   workflows then rebuild the tiles and refresh the site after every scoring run. Without
   those secrets, pages still refresh daily.

## Notes

- `api.suburbs` is a materialized view. The scoring run refreshes it, so a fresh
  `load-geo` shows new suburbs only after the next `score`.
- The map uses OpenStreetMap's public tiles as the basemap, which is fine for low
  traffic. At scale, switch to a hosted basemap per OpenStreetMap's tile usage policy.
