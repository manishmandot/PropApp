import type { Metadata } from "next";
import Link from "next/link";
import { ExplorerMapLazy } from "@/components/ExplorerMapLazy";

export const metadata: Metadata = {
  title: "Suburb score map — PropApp",
  description: "Every Australian suburb coloured by its PropApp score.",
};

export default function MapPage() {
  const tilesUrl = process.env.NEXT_PUBLIC_TILES_URL;
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold">Suburb score map</h1>
      <p className="text-ink-2">
        Hover a suburb for its score, click to open it. Prefer a table? Use the{" "}
        <Link href="/suburbs">suburb finder</Link>.
      </p>
      {tilesUrl ? (
        <ExplorerMapLazy tilesUrl={tilesUrl} />
      ) : (
        <p className="rounded-lg border border-line p-6 text-ink-2">Map data is not available yet.</p>
      )}
    </div>
  );
}
