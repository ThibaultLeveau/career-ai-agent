import { expect, type Page } from "@playwright/test";

export type Theme = "light" | "dark";

export async function expectTheme(page: Page, theme: Theme) {
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  await expect(
    page.getByRole("button", {
      name: `Switch to ${theme === "light" ? "dark" : "light"} theme`,
      exact: true,
    }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => getComputedStyle(document.documentElement).colorScheme),
  ).toBe(theme);
}

export async function setTheme(page: Page, theme: Theme) {
  const current = await page.locator("html").getAttribute("data-theme");
  if (current !== theme) {
    await page.getByRole("button", {
      name: `Switch to ${theme} theme`,
      exact: true,
    }).click();
  }
  await expectTheme(page, theme);
}

export async function captureThemes(page: Page, name: string) {
  const previous = await page.locator("html").getAttribute("data-theme") as Theme;
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.screenshot({
      path: `test-results/${name}-${theme}.png`,
      fullPage: true,
      animations: "disabled",
    });
  }
  await setTheme(page, previous);
}
