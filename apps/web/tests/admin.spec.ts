import { expect, test, type Page } from "@playwright/test";

const username = process.env.ADMIN_INITIAL_USERNAME!;
const password = process.env.ADMIN_INITIAL_PASSWORD!;

async function login(page: Page, name = username, secret = password) {
  await page.goto("/admin/login");
  await page.getByLabel(/^Username/).fill(name);
  await page.getByLabel("Password", { exact: true }).fill(secret);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.locator(".admin-topbar")).toContainText("Home");
}

test("protects the panel and supports login/logout", async ({ page }) => {
  await page.goto("/admin/settings/ai");
  await expect(page).toHaveURL(/\/admin\/login$/);
  expect((await page.request.get("/api/admin/settings")).status()).toBe(401);
  await page.screenshot({ path: "test-results/login.png" });
  await login(page);
  const navigation = page.getByRole("navigation", { name: "Main navigation" });
  await expect(navigation.getByRole("link")).toHaveText([
    "Home",
    "Jobs",
    "Projects",
    "Skills",
    "Documents",
    "Ingestion Jobs",
  ]);
  await expect(navigation.getByRole("link", { name: "Home" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(
    page.getByRole("heading", { name: "Overview", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Settings navigation" }),
  ).toHaveCount(0);
  await expect(page.getByRole("link", { name: "View portfolio" })).toHaveCount(
    0,
  );
  await page.screenshot({ path: "test-results/home.png" });
  const cookies = await page.context().cookies();
  expect(
    cookies.find((cookie) => cookie.name === "career_admin")?.httpOnly,
  ).toBe(true);
  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/login$/);
  expect((await page.request.get("/api/admin/settings")).status()).toBe(401);
});

test("saves configuration, masks keys, and preserves unsaved changes", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByRole("link", { name: "AI Provider", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/settings\/ai$/);
  await expect(
    page.getByRole("link", { name: "Settings", exact: true }),
  ).toHaveAttribute("aria-current", "location");
  const navigation = page.getByRole("navigation", {
    name: "Settings navigation",
  });
  await expect(
    navigation.getByRole("link", { name: "AI Provider" }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    navigation.getByRole("link", { name: "Account & security" }),
  ).not.toHaveAttribute("aria-current");
  await page.goto("/admin/ai");
  await expect(page).toHaveURL(/\/admin\/settings\/ai$/);
  await page
    .getByLabel("OpenAI API key", { exact: true })
    .fill("sk-browser-test-secret");
  await page
    .getByRole("button", { name: "Save key", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "OpenAI key saved." }),
  ).toBeVisible();
  await expect(page.getByLabel("OpenAI API key", { exact: true })).toHaveValue(
    "",
  );
  const chat = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Chat model", exact: true }),
  });
  await chat
    .getByRole("combobox", { name: "Provider", exact: true })
    .selectOption("anthropic");
  await chat
    .getByRole("combobox", { name: "Model", exact: true })
    .fill("claude-haiku-5-5");
  await page.getByRole("switch", { name: "Enable reranking" }).check();
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "AI settings saved." }),
  ).toBeVisible();
  await page.reload();
  await expect(
    chat.getByRole("combobox", { name: "Model", exact: true }),
  ).toHaveValue("claude-haiku-5-5");
  await expect(
    page.getByRole("switch", { name: "Enable reranking" }),
  ).toBeChecked();
  await expect(page.getByLabel("OpenAI API key", { exact: true })).toHaveValue(
    "",
  );
  await page.screenshot({
    path: "test-results/ai-settings.png",
    fullPage: true,
  });
  await chat
    .getByRole("combobox", { name: "Model", exact: true })
    .fill("unsaved-model");
  page.once("dialog", (dialog) => dialog.dismiss());
  await navigation.getByRole("link", { name: "Account & security" }).click();
  await expect(page).toHaveURL(/\/admin\/settings\/ai$/);
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: "Home", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/settings\/ai$/);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    chat.getByRole("combobox", { name: "Model", exact: true }),
  ).toHaveValue("claude-haiku-5-5");
  await page.request.delete("/api/admin/providers/openai", {
    headers: { Origin: new URL(page.url()).origin },
  });
  await page.getByRole("link", { name: "RAG", exact: true }).click();
  await page.getByLabel("Search mode", { exact: true }).selectOption("semantic");
  await page.getByLabel("Expansion window", { exact: true }).fill("2");
  await page.getByLabel("Chunk size (tokens)", { exact: true }).fill("900");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("RAG settings saved.");
  await page.reload();
  await expect(page.getByLabel("Search mode", { exact: true })).toHaveValue("semantic");
  await expect(page.getByLabel("Expansion window", { exact: true })).toHaveValue("2");
  await expect(
    page.getByLabel("Chunk size (tokens)", { exact: true }),
  ).toHaveValue("900");
});

test("current password alone does not trigger unsaved changes", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  const dialogs: string[] = [];
  page.on("dialog", async (dialog) => {
    dialogs.push(dialog.message());
    await dialog.dismiss();
  });

  await page.getByLabel(/^Username/).fill(username);
  await page.getByLabel(/^Current password/).fill(password);
  await expect(
    page.getByRole("button", { name: "Save changes", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("Your account is up to date", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "AI Provider", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/settings\/ai$/);
  expect(dialogs).toEqual([]);

  await page.getByRole("link", { name: "Account & security" }).click();
  await page.getByLabel(/^Current password/).fill(password);
  await page.reload();
  expect(dialogs).toEqual([]);
  await page.getByLabel(/^Current password/).fill(password);
  await page.getByLabel(/^New password/).fill("unsaved-new-password");
  await page.getByRole("link", { name: "AI Provider", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/settings$/);
  expect(dialogs).toEqual(["Discard your unsaved changes?"]);

  await page.getByLabel(/^New password/).fill("");
  await page.getByRole("link", { name: "AI Provider", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/settings\/ai$/);
  expect(dialogs).toHaveLength(1);
});

test("credential changes require current password and invalidate old sessions", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Account & security" }),
  ).toHaveAttribute("aria-current", "page");
  await page.screenshot({ path: "test-results/account-settings.png" });
  await page.getByLabel(/^Username/).fill("updated-admin");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: "AI Provider", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/settings$/);
  await page.getByLabel(/^Current password/).fill("incorrect-password");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Current password is incorrect" }),
  ).toBeVisible();
  await page.getByLabel(/^Current password/).fill(password);
  await page.getByLabel(/^New password/).fill("updated-test-password");
  await page
    .getByLabel("Confirm new password", { exact: true })
    .fill("updated-test-password");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/login$/);
  await login(page, "updated-admin", "updated-test-password");
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await page.getByLabel(/^Username/).fill(username);
  await page.getByLabel(/^Current password/).fill("updated-test-password");
  await page.getByLabel(/^New password/).fill(password);
  await page.getByLabel("Confirm new password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/login$/);
});

test("mobile navigation opens, traps focus, and closes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Career AI" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toBeFocused();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeHidden();
  await expect(
    page.getByRole("navigation", { name: "Settings navigation" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "AI Provider", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "AI Provider", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
  for (const width of [390, 768, 1023, 1024, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    const sidebar = await page.locator(".settings-sidebar").boundingBox();
    const content = await page.locator(".admin-content").boundingBox();
    if (width < 1024) {
      expect(sidebar!.y + sidebar!.height).toBeLessThanOrEqual(content!.y);
    } else {
      expect(sidebar!.width).toBe(200);
      expect(sidebar!.x + sidebar!.width).toBe(content!.x);
    }
  }
});
