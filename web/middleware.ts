import { type NextRequest, NextResponse } from "next/server";

// A 5-digit SAL code, optionally followed by a lower-case slug of sensible length.
const SEGMENT = /^\d{5}(-[a-z0-9-]{1,80})?$/;

/**
 * Normalises suburb URLs before they reach the page (and its cache): mixed case redirects
 * to lower case, and malformed segments 404 here instead of each becoming a cache entry.
 */
export function middleware(request: NextRequest) {
  const segment = request.nextUrl.pathname.slice("/suburb/".length);
  const lower = segment.toLowerCase();
  if (lower !== segment && SEGMENT.test(lower)) {
    const url = request.nextUrl.clone();
    url.pathname = `/suburb/${lower}`;
    return NextResponse.redirect(url, 308);
  }
  if (!SEGMENT.test(segment)) {
    return new NextResponse("Not found", { status: 404, headers: { "x-robots-tag": "noindex" } });
  }
  return NextResponse.next();
}

export const config = { matcher: "/suburb/:slug" };
