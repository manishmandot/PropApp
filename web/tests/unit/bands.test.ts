import { describe, expect, it } from "vitest";
import { scoreBand } from "@/lib/bands";
import { getEntitlements } from "@/lib/entitlements";

describe("bands", () => {
  it("matches the pipeline's bands", () => {
    expect([null, 0, 19.9, 20, 99.9, 100].map(scoreBand)).toEqual([0, 1, 1, 2, 5, 5]);
  });
  it("shows everything until plans exist", async () => {
    expect(Object.values(await getEntitlements()).every(Boolean)).toBe(true);
  });
});
