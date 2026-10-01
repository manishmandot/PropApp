import { expect, test } from "@playwright/test";

test("finder filters and sorts", async ({ page }) => {
  await page.goto("/suburbs");
  const rows = page.getByRole("table", { name: "Suburbs" }).locator("tbody tr");
  await expect(rows.first()).toContainText("Alpha");
  await page.getByLabel("State").selectOption("VIC");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page).toHaveURL(/state=VIC/);
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Delta");
});

test("hostile finder parameters never error", async ({ page }) => {
  const response = await page.goto("/suburbs?scoreMin=abc&sort=drop%20table&page=-4&state=XX");
  expect(response?.status()).toBe(200);
});
