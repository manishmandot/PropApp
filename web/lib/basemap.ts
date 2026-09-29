import type { StyleSpecification } from "maplibre-gl";

type Env = Record<string, string | undefined>;

/**
 * The raster basemap under both maps. OpenStreetMap's public tiles are only for light
 * use; set NEXT_PUBLIC_BASEMAP_TILES (a {z}/{x}/{y} URL from a hosted provider) and
 * NEXT_PUBLIC_BASEMAP_ATTRIBUTION before launch.
 */
export function basemapStyle(env: Env = {
  NEXT_PUBLIC_BASEMAP_TILES: process.env.NEXT_PUBLIC_BASEMAP_TILES,
  NEXT_PUBLIC_BASEMAP_ATTRIBUTION: process.env.NEXT_PUBLIC_BASEMAP_ATTRIBUTION,
}): StyleSpecification {
  return {
    version: 8,
    sources: {
      basemap: {
        type: "raster",
        tiles: [env.NEXT_PUBLIC_BASEMAP_TILES || "https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: env.NEXT_PUBLIC_BASEMAP_ATTRIBUTION || "© OpenStreetMap contributors",
      },
    },
    layers: [{ id: "basemap", type: "raster", source: "basemap", paint: { "raster-saturation": -0.8 } }],
  };
}
