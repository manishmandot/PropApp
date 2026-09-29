import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";
import { middleware } from "@/middleware";

const run = (path: string) => middleware(new NextRequest(`http://site.test${path}`));

describe("suburb URL middleware", () => {
  it("redirects mixed case to lower case", () => {
    const response = run("/suburb/10001-Alpha-NSW");
    expect(response.status).toBe(308);
    expect(response.headers.get("location")).toBe("http://site.test/suburb/10001-alpha-nsw");
  });

  it("404s malformed or oversized segments before they reach the page cache", () => {
    expect(run("/suburb/abc").status).toBe(404);
    expect(run("/suburb/10001-" + "x".repeat(120)).status).toBe(404);
    expect(run("/suburb/10001_alpha").status).toBe(404);
  });

  it("passes well-formed URLs through", () => {
    expect(run("/suburb/10001-alpha-nsw").headers.get("x-middleware-next")).toBe("1");
    expect(run("/suburb/10001").headers.get("x-middleware-next")).toBe("1");
  });
});
