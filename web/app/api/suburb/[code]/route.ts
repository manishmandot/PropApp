import { NextResponse } from "next/server";
import { getEntitlements } from "@/lib/entitlements";
import { getSuburb } from "@/lib/queries";

const CODE = /^\d{5}$/;

/** Hover details for the map explorer. Exact scores pass through plan entitlements. */
export async function GET(_request: Request, { params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  if (!CODE.test(code)) return NextResponse.json({ error: "bad suburb code" }, { status: 400 });
  const [suburb, entitlements] = await Promise.all([getSuburb(code), getEntitlements()]);
  if (!suburb) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json(
    {
      code: suburb.sal_code,
      name: suburb.name,
      state: suburb.state,
      slug: suburb.slug,
      propapp_score: entitlements.exactScores ? suburb.propapp_score : null,
      coverage: suburb.coverage,
    },
    { headers: { "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=86400" } },
  );
}
