import { scoreBand } from "@/lib/bands";
import { formatScore } from "@/lib/format";

/** A score with its band colour as a small swatch; the number is always shown as text. */
export function ScoreBadge({ score, label }: { score: number | null; label?: string }) {
  const band = scoreBand(score);
  return (
    <span className="inline-flex items-center gap-1.5 tabular-nums" title={label}>
      <span
        aria-hidden
        className="inline-block h-2.5 w-2.5 rounded-sm"
        style={{ background: `var(--band-${band})` }}
      />
      {formatScore(score)}
    </span>
  );
}
