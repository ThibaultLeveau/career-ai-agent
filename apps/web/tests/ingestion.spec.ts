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

test("queues content, shows failures and logs, and supports selective re-ingestion", async ({
  page,
}) => {
  await login(page);
  const headers = { Origin: new URL(page.url()).origin };
  await page.request.delete("/api/admin/providers/openai", { headers });
  await page.getByRole("link", { name: "Skills", exact: true }).click();
  await page.getByLabel("New skill keyword").fill("Ingestion browser test");
  await page.getByRole("button", { name: "Add skill", exact: true }).click();
  const row = page
    .locator(".skill-row")
    .filter({ hasText: "Ingestion browser test" });
  await expect(row.getByText("Failed", { exact: true })).toBeVisible({
    timeout: 20000,
  });
  await expect(row).toContainText("Add an OpenAI API key");
  const queued = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/reingest"),
  );
  await row.getByRole("button", { name: /Re-ingest skills item/ }).click();
  const newJob = await (await queued).json();
  await expect(row.getByRole("link")).toHaveAttribute(
    "href",
    `/admin/ingestion?job=${newJob.id}`,
  );
  await expect(row.getByText("Failed", { exact: true })).toBeVisible({
    timeout: 20000,
  });
  await row.getByRole("link", { name: "Failed", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ingestion Jobs", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".ingestion-logs")).toContainText(
    "Add an OpenAI API key",
  );
  await page.getByLabel("Content type").selectOption("skills");
  await page
    .getByRole("button", { name: "Re-ingest all", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Select all", { exact: true }).uncheck();
  await expect(
    dialog.getByRole("button", { name: "Start re-ingestion" }),
  ).toBeDisabled();
  await dialog.getByLabel("Skills", { exact: true }).check();
  await dialog.getByRole("button", { name: "Start re-ingestion" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole("status")).toContainText("Queued 1 items.");
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
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: "test-results/ingestion-jobs.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "Skills", exact: true }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Delete Ingestion browser test" })
    .click();
});

test("polling updates status without discarding an editor draft", async ({
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
  await page.goto(`/admin/projects/${item.id}`);
  await expect(
    page.getByRole("button", { name: /Re-ingest projects item/ }),
  ).toBeDisabled();
  await page
    .getByRole("textbox", { name: "Summary", exact: true })
    .fill("Keep this unsaved draft");
  status = "succeeded";
  await expect(page.getByText("Ingested", { exact: true })).toBeVisible({
    timeout: 10000,
  });
  await expect(
    page.getByRole("textbox", { name: "Summary", exact: true }),
  ).toHaveValue("Keep this unsaved draft");
  await expect(
    page.getByRole("button", { name: /Re-ingest projects item/ }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.request.delete(`/api/admin/projects/${item.id}`, { headers });
});
