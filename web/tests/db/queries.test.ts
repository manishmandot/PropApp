import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { useDatabase } from "@/lib/db";
import {
  allSuburbSlugs,
  getBacktest,
  getFactors,
  getFreshness,
  getHistory,
  getShape,
  getSuburb,
  getSuburbs,
  searchSuburbs,
} from "@/lib/queries";
import { createTestDatabase, type TestDatabase } from "../setup-db";

let seeded: TestDatabase;
let empty: TestDatabase;

beforeAll(async () => {
  seeded = await createTestDatabase("propapp_web_test", true);
  empty = await createTestDatabase("propapp_web_empty", false);
  useDatabase(seeded.url);
});

afterAll(async () => {
  await useDatabase(null);
  await seeded.drop();
  await empty.drop();
});

describe("queries (seeded)", () => {
  it("reads a suburb with key figures", async () => {
    const s = await getSuburb("10001");
    expect(s?.coverage).toBe("fundamentals_market");
    expect(s?.slug).toBe("10001-alpha-nsw");
    expect(s?.median_price).toBe(1_250_000);
    expect(s?.dwelling_type).toBe("house");
    expect(s?.gross_yield).toBeCloseTo(0.038);
    expect(s?.top_drivers[0]).toMatch(/^Population grew/);
    expect(s?.as_of).toBe("2025-12-01");
    expect(await getSuburb("99999")).toBeNull();
  });

  it("reads history ascending, factors and shapes", async () => {
    const history = await getHistory("10001");
    expect(history.map((h) => h.as_of)).toEqual(["2025-11-01", "2025-12-01"]);
    expect((await getFactors("10001")).length).toBe(5);
    expect((await getShape("10001"))?.type).toMatch(/Polygon/);
    expect(await getShape("10002")).toBeNull();
  });

  it("searches and sorts", async () => {
    const { rows, total } = await searchSuburbs({ state: "NSW", sort: "propapp", page: 1 });
    expect(total).toBe(3);
    expect(rows.map((r) => r.sal_code)).toEqual(["10001", "10002", "10003"]);
    const vic = await searchSuburbs({ state: "VIC", sort: "propapp", page: 1 });
    expect(vic.rows.map((r) => r.market_reason)).toEqual(["No market data for this state yet"]);
    const filtered = await searchSuburbs({ scoreMin: 60, sort: "propapp", page: 1 });
    expect(filtered.rows.map((r) => r.sal_code)).toEqual(["10001"]);
    expect((await getSuburbs(["10002", "10001", "bad"])).map((r) => r.sal_code).sort()).toEqual([
      "10001",
      "10002",
    ]);
  });

  it("freshness flags overdue source", async () => {
    const freshness = await getFreshness();
    const stale = Object.fromEntries(freshness.map((f) => [f.id, f.is_stale]));
    expect(stale).toEqual({ abs_census: false, nsw_vg_sales: true });
  });

  it("reads backtest rows and slugs", async () => {
    expect((await getBacktest()).filter((r) => r.split === "holdout")).toHaveLength(2);
    expect((await allSuburbSlugs()).map((s) => s.slug)).toContain("10003-gamma-nsw");
  });
});

describe("queries return empty on an unscored database", () => {
  it("returns unscored rows and no results", async () => {
    useDatabase(empty.url);
    expect(await getBacktest()).toEqual([]);
    expect(await getFreshness()).toEqual([]);
    expect((await searchSuburbs({ sort: "propapp", page: 1 })).total).toBe(0);
    useDatabase(seeded.url);
  });
});
