import { expect, test } from "@playwright/test";
import { EMPTY_PORT } from "../../playwright.config";

test("empty database renders", async ({ page, request }) => {
  const base = `http://localhost:${EMPTY_PORT}`;
  for (const path of ["/", "/suburbs", "/map", "/compare", "/sitemap.xml", "/robots.txt"]) {
    const response = await request.get(`${base}${path}`);
    expect(response.status(), path).toBe(200);
  }
  await page.goto(`${base}/`);
  await expect(page.getByText("Validation results will appear")).toBeVisible();
  await page.goto(`${base}/suburbs`);
  await expect(page.getByText(/Scores are being prepared/)).toBeVisible();
});

test("unscored suburb shows it is being prepared", async ({ page }) => {
  await page.goto("/suburb/20004-delta-vic");
  await expect(page.getByText("Scores are being prepared for this suburb.")).toBeVisible();
});

test("stale banner", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("status")).toContainText("NSW Valuer General sales");
});
