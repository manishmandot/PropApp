import { expect, test } from "@playwright/test";

test("compares suburbs side by side and ignores a fifth", async ({ page }) => {
  await page.goto("/compare?s=10001&s=10002&s=10003&s=20004&s=10001-alpha-nsw&s=bad");
  const table = page.getByRole("table", { name: "Suburb comparison" });
  await expect(table.locator("thead th[scope=col]")).toHaveCount(4);
  await page.goto("/compare?s=10001&s=10002");
  await expect(table.locator("thead th[scope=col]")).toHaveCount(2);
  await expect(table).toContainText("Population growth");
});

test("adds a suburb by name", async ({ page }) => {
  await page.goto("/compare?s=10001");
  await page.getByLabel("Add a suburb").fill("Beta");
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name: /Add Beta Heights/ }).click();
  await expect(page.getByRole("table", { name: "Suburb comparison" }).locator("thead th[scope=col]")).toHaveCount(2);
});
