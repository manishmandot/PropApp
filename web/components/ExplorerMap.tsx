"use client";

import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { basemapStyle } from "@/lib/basemap";
import { BAND_LABELS, type Band } from "@/lib/bands";
import { formatScore } from "@/lib/format";

type Hover = { x: number; y: number; code: string; name: string; state: string; score?: number | null };

const AUSTRALIA: maplibregl.LngLatBoundsLike = [112, -44, 154, -10];
const BANDS: Band[] = [1, 2, 3, 4, 5];

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** `match` expression: band → the page's band colour (so light and dark modes both apply). */
function bandColours(): maplibregl.ExpressionSpecification {
  const pairs = BANDS.flatMap((b) => [b, cssVar(`--band-${b}`)]);
  return ["match", ["get", "band"], ...pairs, cssVar("--band-0")] as unknown as maplibregl.ExpressionSpecification;
}

/** Suburbs coloured by score band from the PMTiles file; exact scores load on hover. */
export function ExplorerMap({ tilesUrl }: { tilesUrl: string }) {
  const container = useRef<HTMLDivElement>(null);
  const router = useRouter();
  const [hover, setHover] = useState<Hover | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const protocol = new Protocol();
    maplibregl.addProtocol("pmtiles", protocol.tile);
    const cache = new Map<string, number | null>();
    let timer: ReturnType<typeof setTimeout> | undefined;

    const map = new maplibregl.Map({
      container: container.current,
      bounds: AUSTRALIA,
      style: {
        ...basemapStyle(),
        sources: {
          ...basemapStyle().sources,
          suburbs: { type: "vector", url: `pmtiles://${tilesUrl}` },
        },
        layers: [
          ...basemapStyle().layers,
          {
            id: "fill",
            type: "fill",
            source: "suburbs",
            "source-layer": "suburbs",
            paint: {
              "fill-color": bandColours(),
              "fill-opacity": 0.75,
            },
          },
          {
            id: "outline",
            type: "line",
            source: "suburbs",
            "source-layer": "suburbs",
            minzoom: 9,
            paint: { "line-color": cssVar("--surface"), "line-width": 1 },
          },
        ],
      },
    });

    map.on("mousemove", "fill", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const p = f.properties as { code: string; name: string; state: string };
      map.getCanvas().style.cursor = "pointer";
      const base = { x: e.point.x, y: e.point.y, code: p.code, name: p.name, state: p.state };
      setHover({ ...base, score: cache.get(p.code) });
      clearTimeout(timer);
      if (cache.has(p.code)) return;
      timer = setTimeout(async () => {
        const res = await fetch(`/api/suburb/${p.code}`);
        const score = res.ok ? ((await res.json()).propapp_score as number | null) : null;
        cache.set(p.code, score);
        setHover((h) => (h && h.code === p.code ? { ...h, score } : h));
      }, 150);
    });
    map.on("mouseleave", "fill", () => {
      map.getCanvas().style.cursor = "";
      setHover(null);
    });
    map.on("click", "fill", (e) => {
      const slug = e.features?.[0]?.properties?.slug;
      if (slug) router.push(`/suburb/${slug}`);
    });

    return () => {
      clearTimeout(timer);
      map.remove();
      maplibregl.removeProtocol("pmtiles");
    };
  }, [tilesUrl, router]);

  return (
    <div className="space-y-3">
      <div className="relative">
        <div ref={container} role="img" aria-label="Map of suburb scores" className="h-[70vh] w-full rounded-lg border border-line" />
        {hover && (
          <div
            className="pointer-events-none absolute z-10 rounded-md border border-line bg-surface px-3 py-2 text-sm shadow"
            style={{ left: hover.x + 12, top: hover.y + 12 }}
          >
            <div className="font-medium">{hover.name.replace(/\s*\([^)]*\)/, "")}, {hover.state}</div>
            <div className="text-ink-2">
              PropApp score: {hover.score === undefined ? "…" : formatScore(hover.score)}
            </div>
          </div>
        )}
      </div>
      <ul className="flex flex-wrap gap-4 text-sm text-ink-2" aria-label="Legend">
        {([...BANDS, 0] as Band[]).map((b) => (
          <li key={b} className="flex items-center gap-1.5">
            <span aria-hidden className="inline-block h-3 w-3 rounded-sm" style={{ background: `var(--band-${b})` }} />
            {BAND_LABELS[b]}
          </li>
        ))}
      </ul>
    </div>
  );
}
