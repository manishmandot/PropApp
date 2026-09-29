"use client";

import dynamic from "next/dynamic";

/** Loads the map library only in the browser, after the page itself. */
export const SuburbMapLazy = dynamic(() => import("./SuburbMap").then((m) => m.SuburbMap), {
  ssr: false,
  loading: () => <div className="h-64 w-full rounded-lg border border-line bg-surface-2" />,
});
