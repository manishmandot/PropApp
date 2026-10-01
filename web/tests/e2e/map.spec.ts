import { expect, test } from "@playwright/test";

test("map page renders without tiles configured", async ({ page }) => {
  const response = await page.goto("/map");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Suburb score map" })).toBeVisible();
  await expect(page.getByText("Map data is not available yet.")).toBeVisible();
});

test("suburb hover endpoint", async ({ request }) => {
  const response = await request.get("/api/suburb/10001");
  expect(response.ok()).toBe(true);
  expect((await response.json()).slug).toBe("10001-alpha-nsw");
});
