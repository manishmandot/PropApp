import { formatDate, formatScore } from "@/lib/format";
import type { HistoryPoint } from "@/lib/types";

const W = 560;
const H = 180;
const PAD = { top: 12, right: 16, bottom: 28, left: 32 };

/** PropApp score over monthly snapshots: one series, server-rendered SVG. */
export function ScoreHistory({ points }: { points: HistoryPoint[] }) {
  const scored = points.filter((p) => p.propapp_score != null);
  if (scored.length < 2) {
    return <p className="text-sm text-ink-2">Score history appears after two monthly updates.</p>;
  }
  const x = (i: number) => PAD.left + (i * (W - PAD.left - PAD.right)) / (scored.length - 1);
  const y = (v: number) => PAD.top + ((100 - v) * (H - PAD.top - PAD.bottom)) / 100;
  const line = scored.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.propapp_score!)}`).join(" ");

  return (
    <figure className="space-y-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-xl" role="img" aria-labelledby="history-title">
        <title id="history-title">PropApp score by month</title>
        {[0, 50, 100].map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth={1} />
            <text x={PAD.left - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill="var(--ink-3)">
              {v}
            </text>
          </g>
        ))}
        <path d={line} fill="none" stroke="var(--band-4)" strokeWidth={2} strokeLinejoin="round" />
        {scored.map((p, i) => (
          <g key={p.as_of}>
            <circle cx={x(i)} cy={y(p.propapp_score!)} r={4} fill="var(--band-4)" stroke="var(--surface)" strokeWidth={2} />
            {/* Larger invisible hit target carrying the tooltip. */}
            <circle cx={x(i)} cy={y(p.propapp_score!)} r={12} fill="transparent">
              <title>{`${monthLabel(p.as_of)}: ${formatScore(p.propapp_score)}`}</title>
            </circle>
          </g>
        ))}
        {[0, scored.length - 1].map((i) => (
          <text
            key={i}
            x={x(i)}
            y={H - 8}
            textAnchor={i === 0 ? "start" : "end"}
            fontSize={11}
            fill="var(--ink-3)"
          >
            {monthLabel(scored[i].as_of)}
          </text>
        ))}
      </svg>
      <table className="sr-only">
        <caption>PropApp score by month</caption>
        <tbody>
          {scored.map((p) => (
            <tr key={p.as_of}>
              <th scope="row">{formatDate(p.as_of)}</th>
              <td>{formatScore(p.propapp_score)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

function monthLabel(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("en-AU", { month: "short", year: "numeric" });
}
