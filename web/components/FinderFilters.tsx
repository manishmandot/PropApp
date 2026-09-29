import type { Filters } from "@/lib/filters";
import { COVERAGES, STATES } from "@/lib/types";
import { coverageLabel } from "@/components/CoverageBadge";

const input = "w-28 rounded-md border border-line bg-surface px-2 py-1";

/** A plain GET form, so filtering works without JavaScript. */
export function FinderFilters({ filters }: { filters: Filters }) {
  return (
    <form method="get" action="/suburbs" className="flex flex-wrap items-end gap-3 text-sm">
      <label className="flex flex-col gap-1">
        State
        <select name="state" defaultValue={filters.state ?? ""} className={input}>
          <option value="">All</option>
          {STATES.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        Min price (A$)
        <input name="priceMin" type="number" min={0} step={10000} defaultValue={filters.priceMin} className={input} />
      </label>
      <label className="flex flex-col gap-1">
        Max price (A$)
        <input name="priceMax" type="number" min={0} step={10000} defaultValue={filters.priceMax} className={input} />
      </label>
      <label className="flex flex-col gap-1">
        Min yield (%)
        <input
          name="yieldMin"
          type="number"
          min={0}
          max={20}
          step={0.1}
          defaultValue={filters.yieldMin == null ? undefined : filters.yieldMin * 100}
          className={input}
        />
      </label>
      <label className="flex flex-col gap-1">
        Min score
        <input name="scoreMin" type="number" min={0} max={100} defaultValue={filters.scoreMin} className={input} />
      </label>
      <label className="flex flex-col gap-1">
        Max score
        <input name="scoreMax" type="number" min={0} max={100} defaultValue={filters.scoreMax} className={input} />
      </label>
      <label className="flex flex-col gap-1">
        Coverage
        <select name="coverage" defaultValue={filters.coverage ?? ""} className={input}>
          <option value="">Any</option>
          {COVERAGES.map((c) => (
            <option key={c} value={c}>
              {coverageLabel(c)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        Sort by
        <select name="sort" defaultValue={filters.sort} className={input}>
          <option value="propapp">PropApp score</option>
          <option value="fundamentals">Fundamentals score</option>
          <option value="name">Name</option>
        </select>
      </label>
      <button type="submit" className="rounded-md bg-accent px-4 py-1.5 text-white">
        Apply
      </button>
    </form>
  );
}
