import type { Coverage } from "@/lib/types";

const LABELS: Record<Coverage, string> = {
  fundamentals_market: "Fundamentals + Market",
  fundamentals: "Fundamentals only",
  insufficient: "Not enough data",
};

export function coverageLabel(coverage: Coverage | null): string {
  return coverage ? LABELS[coverage] : "Not scored yet";
}

export function CoverageBadge({ coverage }: { coverage: Coverage | null }) {
  return (
    <span className="inline-block rounded-full border border-line px-2 py-0.5 text-xs text-ink-2">
      {coverageLabel(coverage)}
    </span>
  );
}
