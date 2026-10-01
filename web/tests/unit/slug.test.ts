import { describe, expect, it } from "vitest";
import { parseSuburbParam, suburbSlug } from "@/lib/slug";

describe("slug", () => {
  it("builds canonical slugs", () => {
    expect(suburbSlug("10060", "Paddington (NSW)", "NSW")).toBe("10060-paddington-nsw");
    expect(suburbSlug("20001", "St Kilda East", "VIC")).toBe("20001-st-kilda-east-vic");
  });
  it("parses suburb params", () => {
    expect(parseSuburbParam("10060-anything")).toEqual({ code: "10060" });
    expect(parseSuburbParam("10060")).toEqual({ code: "10060" });
    expect(parseSuburbParam("../etc")).toBeNull();
    expect(parseSuburbParam("1006-x")).toBeNull();
    expect(parseSuburbParam("10060-UPPER")).toBeNull();
  });
});
