"use client";

import type { Geometry } from "geojson";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { basemapStyle } from "@/lib/basemap";
import { useEffect, useRef } from "react";


function bounds(geometry: Geometry): maplibregl.LngLatBoundsLike {
  const coords: number[][] = JSON.stringify(geometry)
    .match(/-?\d+\.?\d*,-?\d+\.?\d*/g)!
    .map((pair) => pair.split(",").map(Number));
  const lngs = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  return [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)];
}

/** A small map with the suburb's outline. */
export function SuburbMap({ geometry, label }: { geometry: Geometry; label: string }) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: basemapStyle(),
      bounds: bounds(geometry),
      fitBoundsOptions: { padding: 24 },
      cooperativeGestures: true,
    });
    map.on("load", () => {
      map.addSource("suburb", { type: "geojson", data: { type: "Feature", geometry, properties: {} } });
      map.addLayer({ id: "fill", type: "fill", source: "suburb", paint: { "fill-color": "#2a78d6", "fill-opacity": 0.15 } });
      map.addLayer({ id: "line", type: "line", source: "suburb", paint: { "line-color": "#1c5cab", "line-width": 2 } });
    });
    return () => map.remove();
  }, [geometry]);
  return <div ref={container} role="img" aria-label={`Map of ${label}`} className="h-64 w-full rounded-lg border border-line" />;
}
