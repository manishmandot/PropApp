import type { Metadata } from "next";
import Link from "next/link";
import { CoverageBadge } from "@/components/CoverageBadge";
import { FinderFilters } from "@/components/FinderFilters";
import { ScoreBadge } from "@/components/ScoreBadge";
import { getEntitlements } from "@/lib/entitlements";
import { PAGE_SIZE, parseFilters, toSearchParams } from "@/lib/filters";
import { formatPct, formatPrice } from "@/lib/format";
import { searchSuburbs } from "@/lib/queries";
import { suburbPath } from "@/lib/slug";

export const metadata: Metadata = {
  title: "Suburb finder — PropApp",
  description: "Filter and rank every Australian suburb by PropApp score, price and yield.",
};

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function Finder({ searchParams }: Props) {
  const filters = parseFilters(await searchParams);
  const [{ rows, total }] = await Promise.all([searchSuburbs(filters), getEntitlements()]);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageHref = (page: number) => `/suburbs?${toSearchParams({ ...filters, page })}`;

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold">Suburb finder</h1>
      <FinderFilters filters={filters} />
      <p className="text-sm text-ink-2" aria-live="polite">
        {total.toLocaleString("en-AU")} suburbs
      </p>
      {rows.length === 0 ? (
        <p className="text-ink-2">
          No suburbs match these filters yet. Scores are being prepared, or the filters are too
          narrow.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" aria-label="Suburbs">
            <thead className="text-left text-ink-3">
              <tr>
                <th className="py-2 pr-4 font-normal">Suburb</th>
                <th className="py-2 pr-4 font-normal">State</th>
                <th className="py-2 pr-4 font-normal">PropApp</th>
                <th className="py-2 pr-4 font-normal">Fundamentals</th>
                <th className="py-2 pr-4 font-normal">Market</th>
                <th className="py-2 pr-4 font-normal">Coverage</th>
                <th className="py-2 pr-4 text-right font-normal">Median price</th>
                <th className="py-2 text-right font-normal">Gross yield</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.sal_code} className="border-t border-line">
                  <td className="py-2 pr-4">
                    <Link href={suburbPath(r.slug)}>{r.name.replace(/\s*\([^)]*\)/, "")}</Link>
                  </td>
                  <td className="py-2 pr-4">{r.state}</td>
                  <td className="py-2 pr-4"><ScoreBadge score={r.propapp_score} /></td>
                  <td className="py-2 pr-4"><ScoreBadge score={r.fundamentals_score} /></td>
                  <td className="py-2 pr-4"><ScoreBadge score={r.market_score} /></td>
                  <td className="py-2 pr-4"><CoverageBadge coverage={r.coverage} /></td>
                  <td className="py-2 pr-4 text-right">{formatPrice(r.median_price)}</td>
                  <td className="py-2 text-right">{formatPct(r.gross_yield)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {pages > 1 && (
        <nav className="flex gap-4 text-sm" aria-label="Pages">
          {filters.page > 1 && <Link href={pageHref(filters.page - 1)}>Previous</Link>}
          <span className="text-ink-3">
            Page {filters.page} of {pages}
          </span>
          {filters.page < pages && <Link href={pageHref(filters.page + 1)}>Next</Link>}
        </nav>
      )}
    </div>
  );
}
