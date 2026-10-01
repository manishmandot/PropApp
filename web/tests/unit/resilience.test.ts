import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/queries", () => ({
  getFreshness: vi.fn().mockRejectedValue(new Error("connection refused")),
}));

import { StaleBanner } from "@/components/StaleBanner";
import { basemapStyle } from "@/lib/basemap";

describe("StaleBanner", () => {
  it("renders nothing instead of failing the page when freshness can't load", async () => {
    await expect(StaleBanner()).resolves.toBeNull();
  });
});

describe("basemapStyle", () => {
  it("defaults to OpenStreetMap and honours configured tiles", () => {
    const osm = basemapStyle({});
    expect(JSON.stringify(osm)).toContain("tile.openstreetmap.org");
    const custom = basemapStyle({
      NEXT_PUBLIC_BASEMAP_TILES: "https://tiles.example/{z}/{x}/{y}.png",
      NEXT_PUBLIC_BASEMAP_ATTRIBUTION: "© Example",
    });
    const source = custom.sources.basemap as { tiles: string[]; attribution: string };
    expect(source.tiles).toEqual(["https://tiles.example/{z}/{x}/{y}.png"]);
    expect(source.attribution).toBe("© Example");
  });
});
