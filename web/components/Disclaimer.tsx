export const DISCLAIMER =
  "PropApp scores are general information only, not financial product advice. " +
  "They do not consider your objectives, financial situation or needs.";

export function Disclaimer({ long = false }: { long?: boolean }) {
  return (
    <p className="text-sm text-ink-3">
      {DISCLAIMER}
      {long &&
        " Scores are built from public data that can be incomplete, delayed or revised, and past price growth does not predict future results. Consider getting independent advice before making an investment decision."}
    </p>
  );
}
