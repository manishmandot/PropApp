import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));

import { revalidatePath } from "next/cache";
import { POST } from "@/app/api/revalidate/route";
import robots from "@/app/robots";
import sitemap from "@/app/sitemap";
import { useDatabase } from "@/lib/db";
import { createTestDatabase, type TestDatabase } from "../setup-db";

let database: TestDatabase;

beforeAll(async () => {
  database = await createTestDatabase("propapp_web_seo", true);
  await useDatabase(database.url);
  process.env.NEXT_PUBLIC_SITE_URL = "https://propapp.test";
});

afterAll(async () => {
  await useDatabase(null);
  await database.drop();
});

const post = (auth?: string) =>
  POST(new Request("http://test/api/revalidate", {
    method: "POST",
    headers: auth ? { authorization: auth } : {},
  }));

describe("revalidate", () => {
  it("rejects missing or wrong tokens, and everything when no secret is set", async () => {
    delete process.env.REVALIDATE_SECRET;
    expect((await post("Bearer anything")).status).toBe(401);
    process.env.REVALIDATE_SECRET = "s3cret";
    expect((await post()).status).toBe(401);
    expect((await post("Bearer wrong")).status).toBe(401);
    expect(revalidatePath).not.toHaveBeenCalled();
  });

  it("revalidates the whole site with the right token", async () => {
    process.env.REVALIDATE_SECRET = "s3cret";
    const response = await post("Bearer s3cret");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ revalidated: true });
    expect(revalidatePath).toHaveBeenCalledWith("/", "layout");
  });
});

describe("sitemap and robots", () => {
  it("lists every suburb page", async () => {
    const urls = (await sitemap()).map((e) => e.url);
    expect(urls).toContain("https://propapp.test/suburb/10001-alpha-nsw");
    expect(urls).toContain("https://propapp.test/suburbs");
    expect(urls.filter((u) => u.includes("/suburb/"))).toHaveLength(4);
  });

  it("keeps crawlers out of the API", () => {
    const r = robots();
    expect(JSON.stringify(r.rules)).toContain("/api/");
    expect(r.sitemap).toBe("https://propapp.test/sitemap.xml");
  });
});
