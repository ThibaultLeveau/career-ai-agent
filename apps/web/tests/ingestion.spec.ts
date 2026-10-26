import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/admin/login");
  await page.getByLabel(/^Username/).fill(process.env.ADMIN_INITIAL_USERNAME!);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.ADMIN_INITIAL_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

test("compact rows expose failures, context actions, and dense history with logs", async ({
  page,
}) => {
  await login(page);
  const headers = { Origin: new URL(page.url()).origin };
  await page.request.delete("/api/admin/providers/openai", { headers });
  const created = await page.request.post("/api/admin/projects", {
    headers,
    data: { name: "Ingestion browser test" },
  });
  const item = await created.json();
  await page.goto("/admin/projects");
  const row = page
    .locator(".content-row")
    .filter({ hasText: "Ingestion browser test" });
  const failed = row.getByRole("link", { name: /^Failed:/ });
  await expect(failed).toBeVisible({ timeout: 20000 });
  await expect(row.getByText("Ingested", { exact: true })).toHaveCount(0);
  await failed.hover();
  await expect(page.getByRole("tooltip")).toContainText(
    "Add an OpenAI API key",
  );
  await row.click({ button: "right" });
  const menu = page.getByRole("menu");
  await expect(menu.getByRole("menuitem")).toHaveText([
    "Edit",
    "Re-ingest",
    "Delete",
  ]);
  await expect(
    menu.getByRole("menuitem", { name: "Edit", exact: true }),
  ).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(menu.getByRole("menuitem", { name: "Re-ingest" })).toBeFocused();
  const queued = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/reingest"),
  );
  await page.keyboard.press("Enter");
  const newJob = await (await queued).json();
  await expect(row.locator(".status-icon")).toHaveAttribute(
    "href",
    `/admin/ingestion?job=${newJob.id}`,
  );
  await expect(failed).toBeVisible({ timeout: 20000 });
  await failed.click();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.locator(".ingestion-logs")).toContainText(
    "Add an OpenAI API key",
  );
  await page
    .getByRole("button", { name: `Hide logs for ingestion ${newJob.id}` })
    .click();
  await expect(page.locator(".ingestion-logs")).toHaveCount(0);
  await page.getByLabel("Content type").selectOption("projects");
  await page
    .getByRole("combobox", { name: "Status", exact: true })
    .selectOption("failed");
  await page
    .getByRole("button", { name: "Re-ingest all", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("checkbox")).toHaveCount(4);
  await expect(dialog.getByRole("checkbox", { name: "Skills" })).toHaveCount(0);
  await dialog.getByLabel("Select all", { exact: true }).uncheck();
  await expect(
    dialog.getByRole("button", { name: "Start re-ingestion" }),
  ).toBeDisabled();
  await dialog.getByLabel("Projects", { exact: true }).check();
  await dialog.getByRole("button", { name: "Start re-ingestion" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("status")).toContainText("Queued 1 items.");
  await page.screenshot({
    path: "test-results/ingestion-jobs.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/ingestion-mobile.png",
    fullPage: true,
  });
  await page.goto("/admin/projects");
  await row
    .getByRole("button", { name: "Actions for Ingestion browser test" })
    .click();
  await menu.getByRole("menuitem", { name: "Edit", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/admin/projects/${item.id}$`));
  await page.request.delete(`/api/admin/projects/${item.id}`, { headers });
});

test("polling updates icons and disabled menu controls without discarding an editor draft", async ({
  page,
}) => {
  await login(page);
  const headers = { Origin: new URL(page.url()).origin };
  const response = await page.request.post("/api/admin/projects", {
    headers,
    data: { name: "Polling project" },
  });
  const item = await response.json();
  let status = "running";
  await page.route(
    "**/api/admin/ingestion/status?source_type=projects",
    (route) =>
      route.fulfill({
        json: {
          [item.id]: {
            status,
            job_id: item.ingestion.job_id,
            stage: "embedding",
            error: null,
            total_chunks: 1,
            completed_chunks: status === "succeeded" ? 1 : 0,
          },
        },
      }),
  );
  await page.goto("/admin/projects");
  const row = page
    .locator(".content-row")
    .filter({ hasText: "Polling project" });
  await expect(
    row.getByRole("link", { name: "Processing", exact: true }),
  ).toBeVisible();
  await row
    .getByRole("button", { name: "Actions for Polling project" })
    .focus();
  await page.keyboard.press("Shift+F10");
  await expect(
    page.getByRole("menuitem", { name: "Re-ingest" }),
  ).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(row.getByRole("button")).toBeFocused();
  await expect(page.getByRole("menu")).toHaveCount(0);
  await row.getByRole("button").click();
  await page.getByRole("heading", { name: "Projects", exact: true }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
  await page.goto(`/admin/projects/${item.id}`);
  await expect(
    page.getByRole("link", { name: "Processing", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Actions for ingestion" }).click();
  await expect(
    page.getByRole("menuitem", { name: "Re-ingest" }),
  ).toBeDisabled();
  await page.keyboard.press("Escape");
  await page
    .getByRole("textbox", { name: "Summary", exact: true })
    .fill("Keep this unsaved draft");
  status = "succeeded";
  await expect(
    page.getByRole("link", { name: "Ingested", exact: true }),
  ).toBeVisible({ timeout: 10000 });
  await expect(
    page.getByRole("textbox", { name: "Summary", exact: true }),
  ).toHaveValue("Keep this unsaved draft");
  await page.getByRole("button", { name: "Actions for ingestion" }).click();
  await expect(page.getByRole("menuitem", { name: "Re-ingest" })).toBeEnabled();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.request.delete(`/api/admin/projects/${item.id}`, { headers });
});

test("home counts content and refreshes the current ingestion funnel", async ({
  page,
}) => {
  await login(page);
  const headers = { Origin: new URL(page.url()).origin };
  const before = await (await page.request.get("/api/admin/overview")).json();
  const skill = await (
    await page.request.post("/api/admin/skills", {
      headers,
      data: { keyword: "Dashboard skill" },
    })
  ).json();
  expect(skill.ingestion).toBeUndefined();
  const overview = await (await page.request.get("/api/admin/overview")).json();
  expect(overview.counts.skills).toBe(before.counts.skills + 1);
  expect(
    Object.values(overview.ingestion).reduce(
      (sum: number, value) => sum + Number(value),
      0,
    ),
  ).toBe(
    overview.counts.jobs + overview.counts.projects + overview.counts.documents,
  );
  let successful = false;
  await page.route("**/api/admin/overview", (route) =>
    route.fulfill({
      json: {
        active: !successful,
        counts: { jobs: 5, projects: 8, skills: 49, documents: 2 },
        ingestion: successful
          ? { pending: 0, ongoing: 0, failed: 0, successful: 15 }
          : { pending: 3, ongoing: 2, failed: 1, successful: 9 },
      },
    }),
  );
  await page.goto("/admin");
  await expect(page.locator(".overview-card strong")).toHaveText([
    "5",
    "8",
    "49",
    "2",
  ]);
  await expect(
    page.getByRole("img", { name: /Current ingestion: 3 pending/ }),
  ).toBeVisible();
  await page.screenshot({ path: "test-results/overview.png", fullPage: true });
  successful = true;
  await expect(page.getByRole("img", { name: /15 successful/ })).toBeVisible({
    timeout: 10000,
  });
  await expect(
    page.getByText("15 of 15 items are up to date.", { exact: false }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/overview-mobile.png",
    fullPage: true,
  });
  await page.goto("/admin/skills");
  const row = page.locator(".skill-row").filter({ hasText: "Dashboard skill" });
  await expect(row.locator(".status-icon")).toHaveCount(0);
  await row.click({ button: "right" });
  await expect(page.getByRole("menuitem")).toHaveText(["Edit", "Delete"]);
  await page.getByRole("menuitem", { name: "Edit", exact: true }).click();
  await page
    .getByLabel("Skill keyword", { exact: true })
    .fill("Dashboard renamed");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    page.getByText("Dashboard renamed", { exact: true }),
  ).toBeVisible();
  await page.request.delete(`/api/admin/skills/${skill.id}`, { headers });
});
