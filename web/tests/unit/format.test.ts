import { describe, expect, it } from "vitest";
import { formatPct, formatPrice, formatScore } from "@/lib/format";

describe("format", () => {
  it("formats prices", () => {
    expect(formatPrice(1_250_000)).toBe("A$1.25m");
    expect(formatPrice(2_000_000)).toBe("A$2m");
    expect(formatPrice(850_000)).toBe("A$850k");
    expect(formatPrice(null)).toBe("—");
  });
  it("formats percentages and scores", () => {
    expect(formatPct(0.041)).toBe("4.1%");
    expect(formatPct(0.023, true)).toBe("+2.3%");
    expect(formatPct(-0.01, true)).toBe("−1.0%");
    expect(formatPct(null)).toBe("—");
    expect(formatScore(72.6)).toBe("73");
    expect(formatScore(null)).toBe("—");
  });
});
