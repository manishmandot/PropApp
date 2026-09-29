import "server-only";
import type { Geometry } from "geojson";
import { db } from "@/lib/db";
import { type Filters, PAGE_SIZE } from "@/lib/filters";
import type { BacktestRow, FactorRow, Freshness, HistoryPoint, SuburbRow } from "@/lib/types";

// Dates come back as ISO strings so they serialise cleanly into pages.
const SUBURB_COLUMNS = `sal_code, name, state, slug, propapp_score, fundamentals_score,
  market_score, coverage, top_drivers, watch_outs, as_of::text as as_of, median_price,
  dwelling_type, gross_yield, population_growth_3y, supply_pressure, market_reason`;

const ORDER_BY: Record<Filters["sort"], string> = {
  propapp: "propapp_score desc nulls last, name",
  fundamentals: "fundamentals_score desc nulls last, name",
  name: "name, state",
};

export async function getSuburb(code: string): Promise<SuburbRow | null> {
  const sql = db();
  const rows = await sql<SuburbRow[]>`
    select ${sql.unsafe(SUBURB_COLUMNS)} from api.suburbs where sal_code = ${code}`;
  return rows[0] ?? null;
}

export async function getSuburbs(codes: string[]): Promise<SuburbRow[]> {
  if (codes.length === 0) return [];
  const sql = db();
  return sql<SuburbRow[]>`
    select ${sql.unsafe(SUBURB_COLUMNS)} from api.suburbs where sal_code = any(${codes})`;
}

export async function getHistory(code: string): Promise<HistoryPoint[]> {
  return db()<HistoryPoint[]>`
    select as_of::text as as_of, propapp_score, fundamentals_score, market_score
    from api.score_history where sal_code = ${code} order by as_of`;
}

export async function getFactors(code: string): Promise<FactorRow[]> {
  return db()<FactorRow[]>`
    select sal_code, factor, layer, raw_value, percentile, weight
    from api.suburb_factors where sal_code = ${code} order by layer, weight desc`;
}

export async function getFactorsFor(codes: string[]): Promise<FactorRow[]> {
  if (codes.length === 0) return [];
  return db()<FactorRow[]>`
    select sal_code, factor, layer, raw_value, percentile, weight
    from api.suburb_factors where sal_code = any(${codes})`;
}

export async function getShape(code: string): Promise<Geometry | null> {
  const rows = await db()<{ geojson: Geometry }[]>`
    select geojson from api.suburb_shapes where sal_code = ${code}`;
  return rows[0]?.geojson ?? null;
}

/** Filters must come from `parseFilters`; sort is mapped through a fixed allow-list. */
export async function searchSuburbs(
  filters: Filters,
): Promise<{ rows: SuburbRow[]; total: number }> {
  const sql = db();
  const conditions = [sql`true`];
  if (filters.state) conditions.push(sql`state = ${filters.state}`);
  if (filters.coverage) conditions.push(sql`coverage = ${filters.coverage}`);
  if (filters.priceMin != null) conditions.push(sql`median_price >= ${filters.priceMin}`);
  if (filters.priceMax != null) conditions.push(sql`median_price <= ${filters.priceMax}`);
  if (filters.yieldMin != null) conditions.push(sql`gross_yield >= ${filters.yieldMin}`);
  if (filters.scoreMin != null) conditions.push(sql`propapp_score >= ${filters.scoreMin}`);
  if (filters.scoreMax != null) conditions.push(sql`propapp_score <= ${filters.scoreMax}`);
  const where = conditions.reduce((acc, c) => sql`${acc} and ${c}`);
  const offset = (filters.page - 1) * PAGE_SIZE;
  const rows = await sql<(SuburbRow & { total: number })[]>`
    select ${sql.unsafe(SUBURB_COLUMNS)}, count(*) over ()::int as total
    from api.suburbs
    where ${where}
    order by ${sql.unsafe(ORDER_BY[filters.sort])}
    limit ${PAGE_SIZE} offset ${offset}`;
  return { rows, total: rows[0]?.total ?? 0 };
}

export async function getFreshness(): Promise<Freshness[]> {
  return db()<Freshness[]>`
    select id, name, attribution, licence, last_success::text as last_success, cadence_days,
           is_stale
    from api.source_freshness order by name`;
}

export async function getBacktest(): Promise<BacktestRow[]> {
  return db()<BacktestRow[]>`
    select model_version, horizon_months, split, spearman, top_decile_excess, n_dates,
           run_at::text as run_at
    from api.backtest_summary order by split desc, horizon_months`;
}

export async function allSuburbSlugs(): Promise<{ slug: string; as_of: string | null }[]> {
  return db()<{ slug: string; as_of: string | null }[]>`
    select slug, as_of::text as as_of from api.suburbs order by sal_code`;
}
