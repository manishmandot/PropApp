import { getFreshness } from "@/lib/queries";

/** Warns on every page when a source is overdue (older than 1.5 × its usual cadence). */
export async function StaleBanner() {
  let freshness;
  try {
    freshness = await getFreshness();
  } catch {
    return null; // a banner must never take the page down with it
  }
  const stale = freshness.filter((s) => s.is_stale);
  if (stale.length === 0) return null;
  return (
    <div
      role="status"
      className="border-b border-line bg-[var(--warning-bg)] px-4 py-2 text-sm text-[var(--warning-ink)]"
    >
      <div className="mx-auto max-w-6xl">
        Some data may be out of date: {stale.map((s) => s.name).join(", ")} hasn&apos;t
        refreshed on schedule. Scores use the latest data we have.
      </div>
    </div>
  );
}
