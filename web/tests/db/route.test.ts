import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { GET } from "@/app/api/suburb/[code]/route";
import { useDatabase } from "@/lib/db";
import { createTestDatabase, type TestDatabase } from "../setup-db";

let database: TestDatabase;

beforeAll(async () => {
  database = await createTestDatabase("propapp_web_route", true);
  await useDatabase(database.url);
});

afterAll(async () => {
  await useDatabase(null);
  await database.drop();
});

const call = (code: string) =>
  GET(new Request(`http://test/api/suburb/${code}`), { params: Promise.resolve({ code }) });

describe("GET /api/suburb/[code]", () => {
  it("returns the hover payload", async () => {
    const response = await call("10001");
    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toContain("s-maxage=3600");
    expect(await response.json()).toEqual({
      code: "10001",
      name: "Alpha",
      state: "NSW",
      slug: "10001-alpha-nsw",
      propapp_score: 72.4,
      coverage: "fundamentals_market",
    });
  });

  it("404s unknown and 400s malformed codes", async () => {
    expect((await call("99999")).status).toBe(404);
    expect((await call("abc")).status).toBe(400);
  });
});
