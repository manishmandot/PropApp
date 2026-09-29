import type { MetadataRoute } from "next";
import { allSuburbSlugs } from "@/lib/queries";
import { siteUrl } from "@/lib/site";
import { suburbPath } from "@/lib/slug";

export const revalidate = 86400;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = siteUrl();
  const pages = ["", "/suburbs", "/map", "/compare"].map((path) => ({ url: `${base}${path}` }));
  const suburbs = (await allSuburbSlugs()).map((s) => ({
    url: `${base}${suburbPath(s.slug)}`,
    ...(s.as_of ? { lastModified: s.as_of } : {}),
  }));
  return [...pages, ...suburbs];
}
