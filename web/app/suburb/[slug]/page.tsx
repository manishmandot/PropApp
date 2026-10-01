import type { Metadata } from "next";
import { notFound, permanentRedirect } from "next/navigation";
import { CoverageBadge, coverageLabel } from "@/components/CoverageBadge";
import { Disclaimer } from "@/components/Disclaimer";
import { ScoreBadge } from "@/components/ScoreBadge";
import { ScoreHistory } from "@/components/ScoreHistory";
import { SuburbMapLazy as SuburbMap } from "@/components/SuburbMapLazy";
import { getEntitlements } from "@/lib/entitlements";
import { formatDate, formatMonth, formatPct, formatPrice, formatScore } from "@/lib/format";
import { getFreshness, getHistory, getShape, getSuburb } from "@/lib/queries";
import { parseSuburbParam, suburbPath } from "@/lib/slug";
import type { SuburbRow } from "@/lib/types";

export const revalidate = 86400;
export const dynamicParams = true;

export async function generateStaticParams() {
  return []; // rendered on first request, then cached for a day
}

type Props = { params: Promise<{ slug: string }> };

async function load(slug: string): Promise<SuburbRow> {
  const parsed = parseSuburbParam(slug);
  if (!parsed) notFound();
  const suburb = await getSuburb(parsed.code);
  if (!suburb) notFound();
  if (suburb.slug !== slug) permanentRedirect(suburbPath(suburb.slug));
  return suburb;
}

function displayName(s: SuburbRow) {
  return `${s.name.replace(/\s*\([^)]*\)/, "")}, ${s.state}`;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const suburb = await load((await params).slug);
  const name = displayName(suburb);
  const description =
    suburb.propapp_score == null
      ? `${name}: suburb profile and data coverage on PropApp.`
      : `${name} scores ${formatScore(suburb.propapp_score)}/100 on PropApp (${coverageLabel(suburb.coverage)}). See what drives the score.`;
  return {
    title: `${name} suburb score — PropApp`,
    description,
    alternates: { canonical: suburbPath(suburb.slug) },
  };
}

export default async function SuburbPage({ params }: Props) {
  const suburb = await load((await params).slug);
  const [history, shape, sources, entitlements] = await Promise.all([
    getHistory(suburb.sal_code),
    getShape(suburb.sal_code),
    getFreshness(),
    getEntitlements(),
  ]);
  const name = displayName(suburb);
  const scored = suburb.coverage != null && suburb.coverage !== "insufficient";
  const figures = [
    suburb.median_price != null && [
      `Median ${suburb.dwelling_type ?? "dwelling"} price (12 months to ${formatMonth(suburb.median_price_month)})`,
      formatPrice(suburb.median_price),
    ],
    suburb.gross_yield != null && ["Gross rental yield", formatPct(suburb.gross_yield)],
    suburb.population_growth_3y != null && ["Population growth (a year, 3 years)", formatPct(suburb.population_growth_3y, true)],
    suburb.supply_pressure != null && ["New dwellings approved per 1,000 homes", suburb.supply_pressure.toFixed(1)],
  ].filter((f): f is [string, string] => scored && Boolean(f));

  return (
    <article className="space-y-10">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold">{name}</h1>
        <div className="flex flex-wrap items-center gap-3 text-sm text-ink-2">
          <CoverageBadge coverage={suburb.coverage} />
          {suburb.as_of && <span>Updated {formatDate(suburb.as_of)}</span>}
        </div>
      </header>

      {suburb.coverage == null && (
        <p className="text-ink-2">Scores are being prepared for this suburb.</p>
      )}
      {suburb.coverage === "insufficient" && (
        <p className="text-ink-2">Not enough data to score this suburb yet.</p>
      )}

      {scored && (
        <section aria-label="Scores" className="grid gap-4 sm:grid-cols-3">
          <Score title="PropApp score" value={suburb.propapp_score} large />
          <Score title="Fundamentals" value={suburb.fundamentals_score} />
          {suburb.market_score != null && entitlements.marketDetail ? (
            <Score title="Market" value={suburb.market_score} />
          ) : (
            <div className="rounded-lg border border-line p-4">
              <div className="text-sm text-ink-3">Market</div>
              <p className="mt-1 text-sm text-ink-2">{suburb.market_reason}</p>
            </div>
          )}
        </section>
      )}

      {scored && (suburb.top_drivers.length > 0 || suburb.watch_outs.length > 0) && (
        <section className="grid gap-6 md:grid-cols-2">
          <List title="What lifts the score" items={suburb.top_drivers} />
          <List title="Watch-outs" items={suburb.watch_outs} />
        </section>
      )}

      {scored && (
        <section className="space-y-2">
          <h2 className="text-xl font-semibold">Score history</h2>
          <ScoreHistory points={history} />
        </section>
      )}

      {figures.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-xl font-semibold">Key figures</h2>
          <dl className="grid gap-3 sm:grid-cols-2">
            {figures.map(([label, value]) => (
              <div key={label} className="rounded-lg border border-line p-3">
                <dt className="text-sm text-ink-3">{label}</dt>
                <dd className="text-lg tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {shape && (
        <section className="space-y-2">
          <h2 className="text-xl font-semibold">Map</h2>
          <SuburbMap geometry={shape} label={name} />
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-xl font-semibold">Sources</h2>
        <ul className="space-y-1 text-sm text-ink-2">
          {sources.map((s) => (
            <li key={s.id}>
              <span className="text-ink">{s.name}</span> — last updated{" "}
              {formatDate(s.last_success)}
              {s.is_stale && " (overdue)"}. {s.attribution}
            </li>
          ))}
        </ul>
      </section>

      <Disclaimer long />
    </article>
  );
}

function Score({ title, value, large = false }: { title: string; value: number | null; large?: boolean }) {
  return (
    <div className="rounded-lg border border-line p-4">
      <div className="text-sm text-ink-3">{title}</div>
      <div className={large ? "text-4xl font-semibold" : "text-2xl"}>
        <ScoreBadge score={value} label={title} />
      </div>
    </div>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h2 className="mb-2 text-xl font-semibold">{title}</h2>
      <ul className="list-disc space-y-1 pl-5 text-ink-2">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
