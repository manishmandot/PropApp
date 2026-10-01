import { COVERAGES, type Coverage, STATES, type State } from "@/lib/types";

export type Sort = "propapp" | "fundamentals" | "name";

export type Filters = {
  state?: State;
  priceMin?: number;
  priceMax?: number;
  yieldMin?: number;
  scoreMin?: number;
  scoreMax?: number;
  coverage?: Coverage;
  sort: Sort;
  page: number;
};

export const PAGE_SIZE = 50;

type Params = Record<string, string | string[] | undefined>;

const SORTS: Sort[] = ["propapp", "fundamentals", "name"];
const MAX_PAGE = 1000;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function number(value: string | string[] | undefined, min: number, max: number) {
  const text = first(value)?.trim();
  if (!text) return undefined;
  const n = Number(text);
  return Number.isFinite(n) && n >= min && n <= max ? n : undefined;
}

function ordered(lo: number | undefined, hi: number | undefined) {
  return lo != null && hi != null && lo > hi ? [hi, lo] : [lo, hi];
}

/** Finder filters from URL search params. Anything invalid is dropped, never passed on. */
export function parseFilters(params: Params): Filters {
  const state = first(params.state) as State | undefined;
  const coverage = first(params.coverage) as Coverage | undefined;
  const sort = first(params.sort) as Sort | undefined;
  const [priceMin, priceMax] = ordered(
    number(params.priceMin, 0, 50_000_000),
    number(params.priceMax, 0, 50_000_000),
  );
  const [scoreMin, scoreMax] = ordered(number(params.scoreMin, 0, 100), number(params.scoreMax, 0, 100));
  const yieldPct = number(params.yieldMin, 0, 20);
  const page = Math.trunc(number(params.page, -Infinity, Infinity) ?? 1);

  const filters: Filters = {
    sort: sort && SORTS.includes(sort) ? sort : "propapp",
    page: Math.min(Math.max(page, 1), MAX_PAGE),
  };
  if (state && STATES.includes(state)) filters.state = state;
  if (coverage && COVERAGES.includes(coverage)) filters.coverage = coverage;
  if (priceMin != null) filters.priceMin = priceMin;
  if (priceMax != null) filters.priceMax = priceMax;
  if (yieldPct != null) filters.yieldMin = yieldPct / 100;
  if (scoreMin != null) filters.scoreMin = scoreMin;
  if (scoreMax != null) filters.scoreMax = scoreMax;
  return filters;
}

/** The URL params for `filters` (defaults omitted); yield goes back out as a percentage. */
export function toSearchParams(filters: Filters): URLSearchParams {
  const out = new URLSearchParams();
  const set = (key: string, value: string | number | undefined) => {
    if (value != null) out.set(key, String(value));
  };
  set("state", filters.state);
  set("coverage", filters.coverage);
  set("priceMin", filters.priceMin);
  set("priceMax", filters.priceMax);
  set("yieldMin", filters.yieldMin == null ? undefined : Number((filters.yieldMin * 100).toFixed(2)));
  set("scoreMin", filters.scoreMin);
  set("scoreMax", filters.scoreMax);
  if (filters.sort !== "propapp") set("sort", filters.sort);
  if (filters.page > 1) set("page", filters.page);
  return out;
}
