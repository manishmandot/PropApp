import { describe, expect, it } from "vitest";
import { parseFilters, toSearchParams } from "@/lib/filters";

describe("parseFilters", () => {
  it("drops, swaps and clamps hostile input", () => {
    expect(
      parseFilters({ priceMin: "abc", scoreMin: "90", scoreMax: "10", sort: "drop table", page: "999999" }),
    ).toEqual({ scoreMin: 10, scoreMax: 90, sort: "propapp", page: 1000 });
  });

  it("accepts only known enums", () => {
    expect(parseFilters({ state: "XX", coverage: "all" })).toEqual({ sort: "propapp", page: 1 });
    expect(parseFilters({ state: "VIC", coverage: "fundamentals", sort: "name" })).toEqual({
      state: "VIC",
      coverage: "fundamentals",
      sort: "name",
      page: 1,
    });
  });

  it("reads yield as a percentage and ignores out-of-range numbers", () => {
    expect(parseFilters({ yieldMin: "4", priceMax: "900000", scoreMin: "-5" })).toEqual({
      yieldMin: 0.04,
      priceMax: 900000,
      sort: "propapp",
      page: 1,
    });
  });

  it("uses the first value of repeated params and round-trips", () => {
    const f = parseFilters({ state: ["NSW", "VIC"], page: "0", scoreMin: "55" });
    expect(f).toEqual({ state: "NSW", scoreMin: 55, sort: "propapp", page: 1 });
    expect(toSearchParams({ ...f, yieldMin: 0.045, page: 3 }).toString()).toBe(
      "state=NSW&yieldMin=4.5&scoreMin=55&page=3",
    );
  });
});
