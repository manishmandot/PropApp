"use client";

import dynamic from "next/dynamic";

export const ExplorerMapLazy = dynamic(() => import("./ExplorerMap").then((m) => m.ExplorerMap), {
  ssr: false,
  loading: () => <div className="h-[70vh] w-full rounded-lg border border-line bg-surface-2" />,
});
