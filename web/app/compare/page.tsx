import type { Metadata } from "next";
import Link from "next/link";
import { CoverageBadge } from "@/components/CoverageBadge";
import { ScoreBadge } from "@/components/ScoreBadge";
import { getEntitlements } from "@/lib/entitlements";
import { FACTORS } from "@/lib/factors";
import { formatPct, formatPrice } from "@/lib/format";
import { findSuburbs, getFactorsFor, getSuburbs } from "@/lib/queries";
import { parseSuburbParam, suburbPath } from "@/lib/slug";
import type { SuburbRow } from "@/lib/types";

export const metadata: Metadata = {
  title: "Compare suburbs — PropApp",
  description: "Compare up to four Australian suburbs side by side, factor by factor.",
};

const MAX = 4;
type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

function codesFrom(value: string | string[] | undefined): string[] {
  const list = Array.isArray(value) ? value : value ? [value] : [];
  const codes = list.map((v) => parseSuburbParam(v)?.code).filter((c): c is string => !!c);
  return [...new Set(codes)].slice(0, MAX);
}

function href(codes: string[]) {
  return `/compare?${codes.map((c) => `s=${c}`).join("&")}`;
}

export default async function Compare({ searchParams }: Props) {
  const params = await searchParams;
  const codes = codesFrom(params.s);
  const query = typeof params.q === "string" ? params.q : "";
  const [found, factors, matches, entitlements] = await Promise.all([
    getSuburbs(codes),
    getFactorsFor(codes),
    codes.length < MAX ? findSuburbs(query) : Promise.resolve([]),
    getEntitlements(),
  ]);
  const suburbs = codes
    .map((c) => found.find((s) => s.sal_code === c))
    .filter((s): s is SuburbRow => !!s);
  const factor = (code: string, key: string) =>
    factors.find((f) => f.sal_code === code && f.factor === key);

  const rows: [string, (s: SuburbRow) => React.ReactNode][] = [
    ["PropApp score", (s) => <ScoreBadge score={s.propapp_score} />],
    ["Fundamentals", (s) => <ScoreBadge score={s.fundamentals_score} />],
    ["Market", (s) => (s.market_score == null ? <span className="text-ink-3">—</span> : <ScoreBadge score={s.market_score} />)],
    ["Coverage", (s) => <CoverageBadge coverage={s.coverage} />],
    ["Median price", (s) => formatPrice(s.median_price)],
    ["Gross yield", (s) => formatPct(s.gross_yield)],
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-semibold">Compare suburbs</h1>
      {codes.length < MAX && (
        <form method="get" action="/compare" className="flex flex-wrap items-end gap-2 text-sm">
          {codes.map((c) => (
            <input key={c} type="hidden" name="s" value={c} />
          ))}
          <label className="flex flex-col gap-1">
            Add a suburb (name or code)
            <input name="q" defaultValue={query} className="w-64 rounded-md border border-line bg-surface px-2 py-1" />
          </label>
          <button type="submit" className="rounded-md bg-accent px-4 py-1.5 text-white">
            Search
          </button>
        </form>
      )}
      {query && codes.length < MAX && (
        <ul className="flex flex-wrap gap-3 text-sm" aria-label="Matching suburbs">
          {matches.length === 0 && <li className="text-ink-2">No suburbs match “{query}”.</li>}
          {matches
            .filter((m) => !codes.includes(m.sal_code))
            .map((m) => (
              <li key={m.sal_code}>
                <Link href={href([...codes, m.sal_code])}>
                  Add {m.name}, {m.state}
                </Link>
              </li>
            ))}
        </ul>
      )}
      {suburbs.length === 0 ? (
        <p className="text-ink-2">Search for suburbs above to compare them side by side.</p>
      ) : !entitlements.compare ? null : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" aria-label="Suburb comparison">
            <thead>
              <tr>
                <th className="py-2 pr-4" />
                {suburbs.map((s) => (
                  <th key={s.sal_code} scope="col" className="py-2 pr-4 text-left">
                    <Link href={suburbPath(s.slug)}>
                      {s.name.replace(/\s*\([^)]*\)/, "")}, {s.state}
                    </Link>{" "}
                    <Link
                      href={href(codes.filter((c) => c !== s.sal_code))}
                      className="text-xs font-normal text-ink-3"
                      aria-label={`Remove ${s.name}`}
                    >
                      remove
                    </Link>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(([label, cell]) => (
                <tr key={label} className="border-t border-line">
                  <th scope="row" className="py-2 pr-4 text-left font-normal text-ink-2">{label}</th>
                  {suburbs.map((s) => (
                    <td key={s.sal_code} className="py-2 pr-4">{cell(s)}</td>
                  ))}
                </tr>
              ))}
              {FACTORS.map((f) => (
                <tr key={f.key} className="border-t border-line">
                  <th scope="row" className="py-2 pr-4 text-left font-normal text-ink-2">{f.label}</th>
                  {suburbs.map((s) => {
                    const row = factor(s.sal_code, f.key);
                    return (
                      <td key={s.sal_code} className="py-2 pr-4">
                        {row?.raw_value == null ? (
                          <span className="text-ink-3">—</span>
                        ) : (
                          <>
                            {f.format(row.raw_value)}{" "}
                            <span className="text-xs text-ink-3">(better than {Math.round(row.percentile)}%)</span>
                          </>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
