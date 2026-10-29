import { expect, test } from "@playwright/test";
import { expectTheme } from "./theme";

test("public chat and admin share the complete dark palette while keeping their light themes", async ({ page }) => {
  const palette = async (selector: string) => page.locator(selector).evaluate((element) => {
    const styles = getComputedStyle(element);
    return Object.fromEntries([
      "background", "background-transparent", "surface", "surface-raised", "surface-subtle",
      "surface-hover", "text", "text-secondary", "text-muted", "border", "border-strong",
      "accent", "accent-hover", "accent-soft", "on-accent", "focus", "danger", "danger-soft",
      "success", "success-soft", "warning", "warning-soft", "info", "info-soft", "overlay", "shadow",
    ].map((name) => [name, styles.getPropertyValue(`--${name}`).trim()]));
  });
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await expectTheme(page, "dark");
  const chat = await palette(".portfolio");
  expect(chat.background).toBe("#101114");
  expect(chat.accent).toBe("#b0b8ff");
  await page.goto("/admin");
  await expectTheme(page, "dark");
  expect(await palette(".admin")).toEqual(chat);
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  expect((await palette(".admin")).accent).toBe("#505bc5");
  await page.goto("/");
  await expectTheme(page, "light");
  expect((await palette(".portfolio")).accent).toBe("#376456");
});

test("follows system changes until a manual choice and keeps that choice across navigation", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/");
  await expectTheme(page, "dark");
  expect(await page.evaluate(() => localStorage.getItem("career-theme"))).toBeNull();

  await page.emulateMedia({ colorScheme: "light" });
  await expectTheme(page, "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expectTheme(page, "dark");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expectTheme(page, "light");
  expect(await page.evaluate(() => localStorage.getItem("career-theme"))).toBe("light");
  await page.emulateMedia({ colorScheme: "light" });
  await page.emulateMedia({ colorScheme: "dark" });
  await expectTheme(page, "light");

  await page.goto("/admin/login");
  await expectTheme(page, "light");
  const brand = page.getByRole("link", { name: /Thibault Leveau/ });
  await expect(brand.locator("svg")).toHaveCount(1);
  await brand.click();
  await expect(page).toHaveURL(/\/$/);
  await expectTheme(page, "light");
  await page.reload();
  await expectTheme(page, "light");
});

test("synchronizes explicit choices between portfolio and login tabs", async ({ page, context }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const other = await context.newPage();
  await other.emulateMedia({ colorScheme: "light" });
  await other.goto("/admin/login");
  await expectTheme(other, "light");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expectTheme(page, "dark");
  await expectTheme(other, "dark");
  await other.getByRole("button", { name: "Switch to light theme" }).click();
  await expectTheme(other, "light");
  await expectTheme(page, "light");
  await other.close();
});

test("ignores invalid stored preferences and continues following the system", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.addInitScript(() => localStorage.setItem("career-theme", "invalid"));
  await page.goto("/");
  await expectTheme(page, "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expectTheme(page, "light");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  expect(await page.evaluate(() => localStorage.getItem("career-theme"))).toBe("dark");
});

test("theme controls remain usable without access to local storage", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.emulateMedia({ colorScheme: "light" });
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() {
        throw new DOMException("Storage unavailable", "SecurityError");
      },
    });
  });
  await page.goto("/");
  await expectTheme(page, "light");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expectTheme(page, "dark");
  await page.emulateMedia({ colorScheme: "dark" });
  await page.emulateMedia({ colorScheme: "light" });
  await expectTheme(page, "dark");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expectTheme(page, "light");
  expect(errors).toEqual([]);
});

test("applies the stored theme before hydration scripts can run", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.addInitScript(() => localStorage.setItem("career-theme", "dark"));
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  let scripts = 0;
  await page.route(/\/_next\/static\/.*\.js(?:\?.*)?$/, async (route) => {
    scripts += 1;
    await blocked;
    await route.continue();
  });
  try {
    await page.goto("/", { waitUntil: "commit" });
    await expect(page.getByRole("heading", { name: /Hi, I’m Thibault/ })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect.poll(() => scripts).toBeGreaterThan(0);
  } finally {
    release();
  }
  await page.waitForLoadState("load");
  await expectTheme(page, "dark");
  await page.getByRole("button", { name: "Switch to light theme" }).click();
  await expectTheme(page, "light");
});
