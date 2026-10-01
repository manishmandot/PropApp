import Link from "next/link";
import { Disclaimer } from "@/components/Disclaimer";
import { formatPct } from "@/lib/format";
import { getBacktest } from "@/lib/queries";

export const revalidate = 86400;

const FUNDAMENTALS = [
  ["Population growth", "3-year average yearly growth"],
  ["Supply pressure", "new dwellings approved per 1,000 homes (less is better)"],
  ["Household income", "median weekly household income"],
  ["Unemployment", "the rate, and how it moved over 12 months (lower is better)"],
  ["Owner-occupiers", "share of homes lived in by their owners"],
];
const MARKET = [
  ["Price growth", "12-month change in the median price"],
  ["Momentum", "recent growth compared with the 12-month trend"],
  ["Gross yield", "annual rent as a share of the median price"],
  ["Rent growth", "12-month change in median rent"],
  ["Sales volume", "12-month change in the number of sales"],
];

export default async function Home() {
  const holdout = (await getBacktest()).filter((r) => r.split === "holdout");
  return (
    <div className="space-y-12">
      <section className="space-y-4">
        <h1 className="max-w-3xl text-4xl font-semibold tracking-tight">
          Find Australian suburbs worth a closer look
        </h1>
        <p className="max-w-2xl text-lg text-ink-2">
          PropApp scores every suburb in Australia on the fundamentals that drive long-term
          demand — population, supply, income and jobs — and, where the data exists, on what
          the market is doing now: prices, rents and sales.
        </p>
        <div className="flex gap-3">
          <Link href="/suburbs" className="rounded-md bg-accent px-4 py-2 text-white no-underline">
            Open the suburb finder
          </Link>
          <Link href="/map" className="rounded-md border border-line px-4 py-2 no-underline">
            Explore the map
          </Link>
        </div>
      </section>

      <section id="methodology" className="space-y-4">
        <h2 className="text-2xl font-semibold">How the score works</h2>
        <p className="max-w-3xl text-ink-2">
          Each factor is ranked from 0 to 100 against other suburbs and combined with fixed
          weights. The <strong>fundamentals score</strong> ranks every suburb nationally. The{" "}
          <strong>market score</strong> ranks suburbs within their own state, because each
          state publishes different market data. Where a suburb has both, the PropApp score is
          an even blend of the two.
        </p>
        <div className="grid gap-6 md:grid-cols-2">
          <FactorList title="Fundamentals (every suburb)" items={FUNDAMENTALS} />
          <FactorList title="Market (where data exists)" items={MARKET} />
        </div>
        <p className="max-w-3xl text-ink-2">
          Every suburb carries a coverage badge: <em>Fundamentals + Market</em>,{" "}
          <em>Fundamentals only</em> (no market data for that state yet, or fewer than 20 sales
          in a year), or <em>Not enough data</em>.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">How well it has worked</h2>
        {holdout.length === 0 ? (
          <p className="text-ink-2">
            Validation results will appear after the first backtest against past NSW sales.
          </p>
        ) : (
          <>
            <p className="max-w-3xl text-ink-2">
              We recompute scores as they would have been at past dates and compare them with
              the price growth that followed. These results are from years held back from any
              tuning.
            </p>
            <table aria-label="Held-out backtest results" className="text-sm">
              <thead className="text-left text-ink-3">
                <tr>
                  <th className="py-2 pr-6 font-normal">Horizon</th>
                  <th className="py-2 pr-6 font-normal">Rank correlation with later growth</th>
                  <th className="py-2 pr-6 font-normal">Top 10% vs typical suburb</th>
                  <th className="py-2 font-normal">Dates tested</th>
                </tr>
              </thead>
              <tbody>
                {holdout.map((r) => (
                  <tr key={r.horizon_months} className="border-t border-line">
                    <td className="py-2 pr-6">{r.horizon_months} months</td>
                    <td className="py-2 pr-6">{r.spearman == null ? "—" : r.spearman.toFixed(2)}</td>
                    <td className="py-2 pr-6">{formatPct(r.top_decile_excess, true)}</td>
                    <td className="py-2">{r.n_dates}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      <section className="max-w-3xl">
        <Disclaimer long />
      </section>
    </div>
  );
}

function FactorList({ title, items }: { title: string; items: string[][] }) {
  return (
    <div className="rounded-lg border border-line p-4">
      <h3 className="mb-2 font-medium">{title}</h3>
      <ul className="space-y-1 text-sm text-ink-2">
        {items.map(([name, what]) => (
          <li key={name}>
            <span className="text-ink">{name}</span> — {what}
          </li>
        ))}
      </ul>
    </div>
  );
}
