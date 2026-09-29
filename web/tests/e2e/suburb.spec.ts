import { expect, test } from "@playwright/test";

test("coverage states render", async ({ page }) => {
  await page.goto("/suburb/10001-alpha-nsw");
  await expect(page.getByRole("heading", { name: "Alpha, NSW" })).toBeVisible();
  await expect(page.getByText("Fundamentals + Market")).toBeVisible();
  await expect(page.getByText("What lifts the score")).toBeVisible();
  await expect(page.getByText("A$1.25m")).toBeVisible();

  await page.goto("/suburb/10002-beta-heights-nsw");
  await expect(page.getByText("Fundamentals only")).toBeVisible();
  await expect(page.getByText(/Fewer than 20 sales/)).toBeVisible();

  await page.goto("/suburb/10003-gamma-nsw");
  await expect(page.getByText(/Not enough data to score/)).toBeVisible();
});

test("canonical redirect", async ({ page }) => {
  await page.goto("/suburb/10001-wrong");
  await expect(page).toHaveURL(/\/suburb\/10001-alpha-nsw$/);
});

test("unknown suburb 404", async ({ page }) => {
  expect((await page.goto("/suburb/99999"))?.status()).toBe(404);
  expect((await page.goto("/suburb/abc"))?.status()).toBe(404);
});
