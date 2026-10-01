/** Canonical suburb URL segment: `<sal_code>-<name-slug>-<state>` (matches api.suburbs.slug). */
export function suburbSlug(code: string, name: string, state: string): string {
  const namePart = name
    .replace(/\s*\([^)]*\)/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `${code}-${namePart}-${state.toLowerCase()}`;
}

const PARAM = /^(\d{5})(-[a-z0-9-]+)?$/;

/** The SAL code from a URL segment, or null if the segment is malformed. */
export function parseSuburbParam(param: string): { code: string } | null {
  const match = PARAM.exec(param);
  return match ? { code: match[1] } : null;
}

export function suburbPath(slug: string): string {
  return `/suburb/${slug}`;
}
