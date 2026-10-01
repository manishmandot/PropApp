const DASH = "—";

export function formatPrice(n: number | null | undefined): string {
  if (n == null) return DASH;
  if (n >= 1_000_000) return `A$${trim((n / 1_000_000).toFixed(2))}m`;
  return `A$${Math.round(n / 1_000)}k`;
}

export function formatPct(x: number | null | undefined, signed = false): string {
  if (x == null) return DASH;
  const text = `${Math.abs(x * 100).toFixed(1)}%`;
  if (!signed) return x < 0 ? `−${text}` : text;
  return `${x < 0 ? "−" : "+"}${text}`;
}

export function formatScore(n: number | null | undefined): string {
  return n == null ? DASH : String(Math.round(n));
}

export function formatDate(d: string | Date | null | undefined): string {
  if (!d) return DASH;
  return new Date(d).toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" });
}

function trim(fixed: string): string {
  return fixed.replace(/\.?0+$/, "");
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Sep 2025" from an ISO date (read as UTC, so the month never shifts by time zone). */
export function formatMonth(isoDate: string | null | undefined): string {
  if (!isoDate) return DASH;
  const d = new Date(isoDate);
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}
