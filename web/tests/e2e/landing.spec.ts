import { expect, test } from "@playwright/test";

test("landing explains the score and shows validation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "How the score works" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Held-out backtest results" })).toBeVisible();
  await expect(page.getByText("not financial product advice").first()).toBeVisible();
});
