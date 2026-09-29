export type Band = 0 | 1 | 2 | 3 | 4 | 5;

/** 1 for 0–20 … 5 for 80–100 (100 included); 0 when unscored. Mirrors the pipeline. */
export function scoreBand(score: number | null | undefined): Band {
  if (score == null) return 0;
  return Math.min(Math.floor(score / 20) + 1, 5) as Band;
}

export const BAND_LABELS: Record<Band, string> = {
  0: "Not scored",
  1: "0–20",
  2: "20–40",
  3: "40–60",
  4: "60–80",
  5: "80–100",
};
