import { expect, test, type Page } from "@playwright/test";
import { captureThemes, setTheme } from "./theme";
import type { AgentsSettings, RagSettings } from "../src/lib/admin";

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
  await expect(page.getByRole("link", { name: /Thibault Leveau/ }).locator("svg")).toHaveCount(1);
  await captureThemes(page, "login");
  await page.setViewportSize({ width: 390, height: 844 });
  await captureThemes(page, "login-mobile");
  await page.setViewportSize({ width: 1440, height: 1000 });
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
  await expect(page.getByRole("link", { name: /Thibault Leveau/ }).locator("svg")).toHaveCount(1);
  await captureThemes(page, "admin-home");
  await page.setViewportSize({ width: 390, height: 844 });
  await captureThemes(page, "admin-home-mobile");
  await page.setViewportSize({ width: 1440, height: 1000 });
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
  await captureThemes(page, "ai-settings");
  await chat
    .getByRole("combobox", { name: "Model", exact: true })
    .fill("unsaved-model");
  const themeDialogs: string[] = [];
  const onThemeDialog = async (dialog: import("@playwright/test").Dialog) => {
    themeDialogs.push(dialog.message());
    await dialog.dismiss();
  };
  page.on("dialog", onThemeDialog);
  await captureThemes(page, "ai-settings-unsaved");
  page.off("dialog", onThemeDialog);
  expect(themeDialogs).toEqual([]);
  await expect(chat.getByRole("combobox", { name: "Model", exact: true })).toHaveValue("unsaved-model");
  await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeEnabled();
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
  await captureThemes(page, "account-settings");
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
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.getByRole("button", { name: "Open navigation" }).click();
    await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
    await page.screenshot({ path: `test-results/admin-mobile-menu-${theme}.png`, fullPage: true, animations: "disabled" });
    await page.keyboard.press("Escape");
  }
  await page
    .getByRole("button", { name: "Open navigation", exact: true })
    .click();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
  await page.keyboard.press("Shift+Tab");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: /Thibault Leveau/ })).toBeFocused();
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
  await captureThemes(page, "admin-settings-mobile");
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

test("agents settings persist independently and support prompt reset and unsaved changes", async ({ page }) => {
  await login(page);
  const original = await (await page.request.get("/api/admin/settings")).json() as RagSettings;
  const defaults = await (await page.request.get("/api/admin/agents/defaults")).json() as AgentsSettings;
  const origin = new URL(page.url()).origin;
  try {
    await page.goto("/admin/settings/agents");
    await expect(page.getByRole("link", { name: "Agents", exact: true })).toHaveAttribute("aria-current", "page");
    await expect(page.locator(".admin-topbar")).toContainText("Settings / Agents");
    const analyzer = page.getByRole("region", { name: "Query Analyzer", exact: true });
    await page.getByRole("switch", { name: "Enable agentic mode" }).setChecked(!original.agents.enabled);
    const customPrompt = `${defaults.query_analyzer.prompt}\nPrefer concise comparisons.`;
    await page.getByLabel("Query Analyzer prompt", { exact: true }).fill(customPrompt);
    await page.getByLabel("Use a different model for Query Analyzer", { exact: true }).check();
    await analyzer.getByRole("combobox", { name: "Provider", exact: true }).selectOption("openai");
    await analyzer.getByRole("combobox", { name: "Model", exact: true }).fill("test-agent-model");
    await analyzer.getByLabel("Maximum output tokens", { exact: true }).fill("4096");
    const patch = page.waitForRequest((request) => request.url().endsWith("/api/admin/settings") && request.method() === "PATCH");
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    expect(Object.keys((await patch).postDataJSON())).toEqual(["agents"]);
    await expect(page.getByRole("status")).toContainText("Agent settings saved.");
    await page.reload();
    await expect(page.getByRole("switch", { name: "Enable agentic mode" })).toBeChecked({ checked: !original.agents.enabled });
    await expect(page.getByLabel("Query Analyzer prompt", { exact: true })).toHaveValue(customPrompt);
    await expect(analyzer.getByRole("combobox", { name: "Model", exact: true })).toHaveValue("test-agent-model");
    const updated = await (await page.request.get("/api/admin/settings")).json() as RagSettings;
    expect(updated.chat).toEqual(original.chat);
    expect(updated.retrieval).toEqual(original.retrieval);
    expect(updated.agents.query_analyzer.generation?.max_output_tokens).toBe(4096);
    await page.getByRole("button", { name: "Reset Query Analyzer prompt", exact: true }).click();
    await expect(page.getByLabel("Query Analyzer prompt", { exact: true })).toHaveValue(defaults.query_analyzer.prompt);
    page.once("dialog", (dialog) => dialog.dismiss());
    await page.getByRole("link", { name: "RAG", exact: true }).click();
    await expect(page).toHaveURL(/\/admin\/settings\/agents$/);
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByLabel("Query Analyzer prompt", { exact: true })).toHaveValue(customPrompt);
    await page.getByLabel("Use a different model for Query Analyzer", { exact: true }).uncheck();
    await page.getByRole("button", { name: "Save changes", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("Agent settings saved.");
    const inherited = await (await page.request.get("/api/admin/settings")).json() as RagSettings;
    expect(inherited.agents.query_analyzer.generation).toBeNull();
    await captureThemes(page, "agents-settings");
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await captureThemes(page, "agents-settings-mobile");
  } finally {
    await page.request.patch("/api/admin/settings", { headers: { Origin: origin }, data: { agents: original.agents } });
  }
});

test("agent connection tests use draft prompts and models without saving", async ({ page }) => {
  await login(page);
  await page.goto("/admin/settings/agents");
  const original = await (await page.request.get("/api/admin/settings")).json() as RagSettings;
  const roles = [
    ["query_analyzer", "Query Analyzer"], ["database", "Database"],
    ["rag", "RAG"], ["representative", "Thibault Representative"],
  ] as const;
  for (const [id, name] of roles) {
    let draft: RagSettings | undefined;
    await page.route(`**/api/admin/test/${id}`, async (route) => {
      draft = route.request().postDataJSON().settings as RagSettings;
      await route.fulfill({ json: { ok: true, message: `${name} model connected.` } });
    });
    const section = page.getByRole("region", { name, exact: true });
    await page.getByLabel(`${name} prompt`, { exact: true }).fill(`Draft instructions for ${name}.`);
    await page.getByLabel(`Use a different model for ${name}`, { exact: true }).check();
    await section.getByRole("combobox", { name: "Model", exact: true }).fill("draft-model");
    await page.getByRole("button", { name: `Test ${name}`, exact: true }).click();
    await expect(section.getByRole("status")).toHaveText(`${name} model connected.`);
    expect(draft?.agents[id].prompt).toBe(`Draft instructions for ${name}.`);
    expect(draft?.agents[id].generation?.model).toBe("draft-model");
  }
  const after = await (await page.request.get("/api/admin/settings")).json() as RagSettings;
  expect(after.agents).toEqual(original.agents);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeDisabled();
});

test("chat component page sizes persist independently without changing other settings", async ({ page }) => {
  await login(page);
  const original = await (await page.request.get("/api/admin/settings")).json() as RagSettings;
  const origin = new URL(page.url()).origin;
  try {
    await page.goto("/admin/settings/chat-components");
    await expect(page.getByRole("heading", { name: "Chat components", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Chat components", exact: true })).toHaveAttribute("aria-current", "page");
    await page.getByLabel("Projects per page").fill("3");
    await page.getByLabel("Jobs per page").fill("7");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status")).toContainText("Chat component settings saved.");
    await page.reload();
    await expect(page.getByLabel("Projects per page")).toHaveValue("3");
    await expect(page.getByLabel("Jobs per page")).toHaveValue("7");
    const after = await (await page.request.get("/api/admin/settings")).json() as RagSettings;
    expect(after).toEqual({ ...original, chat_components: { project_list_page_size: 3, job_list_page_size: 7 } });
    await page.getByLabel("Projects per page").fill("21");
    expect(await page.getByLabel("Projects per page").evaluate((node: HTMLInputElement) => node.validity.valid)).toBe(false);
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await captureThemes(page, "chat-components-settings");
    await page.setViewportSize({ width: 390, height: 844 });
    await captureThemes(page, "chat-components-settings-mobile");
  } finally {
    await page.request.patch("/api/admin/settings", { headers: { Origin: origin }, data: { chat_components: original.chat_components } });
  }
});
