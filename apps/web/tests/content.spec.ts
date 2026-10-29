import { expect, test, type Page } from "@playwright/test";
import { captureThemes, setTheme } from "./theme";

const pdf = Buffer.concat([
  Buffer.from("%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"),
  Buffer.alloc(70000, 32),
  Buffer.from("\n%%EOF"),
]);

async function login(page: Page) {
  await page.goto("/admin/login");
  await page.getByLabel(/^Username/).fill(process.env.ADMIN_INITIAL_USERNAME!);
  await page
    .getByLabel("Password", { exact: true })
    .fill(process.env.ADMIN_INITIAL_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

async function markdownSource(page: Page, label: string) {
  const field = page.getByRole("group", { name: label, exact: true });
  await field.getByRole("button", { name: "Markdown", exact: true }).click();
  return field.getByRole("textbox", { name: `${label} Markdown`, exact: true });
}

test.beforeEach(async ({ page }) => {
  await login(page);
});

test("manages jobs, linked projects, and keywords", async ({ page }) => {
  await page.getByRole("link", { name: "Skills", exact: true }).click();
  await page.getByLabel("New skill keyword").fill("TypeScript");
  await page.getByRole("button", { name: "Add skill", exact: true }).click();
  await expect(page.getByText("TypeScript", { exact: true })).toBeVisible();
  await page.getByLabel("New skill keyword").fill(" typescript ");
  await page.getByRole("button", { name: "Add skill", exact: true }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "already exists",
  );
  await page.getByLabel("New skill keyword").fill("");
  await page.setViewportSize({ width: 390, height: 844 });
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await page.getByRole("button", { name: "Actions for TypeScript", exact: true }).click();
    await expect(page.getByRole("menuitem", { name: "Edit", exact: true })).toBeVisible();
    await page.screenshot({ path: `test-results/content-menu-mobile-${theme}.png`, fullPage: true, animations: "disabled" });
    await page.keyboard.press("Escape");
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByRole("button", { name: "Actions for TypeScript", exact: true })
    .click();
  await page.getByRole("menuitem", { name: "Edit", exact: true }).click();
  await page.getByLabel("Skill keyword", { exact: true }).fill("TypeScript 6");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("TypeScript 6", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await page.getByRole("link", { name: "Add job" }).click();
  await page.getByLabel("Role / title").fill("Software engineer");
  await page.getByLabel("Company").fill("Acme");
  await page.getByLabel("Location").fill("Paris");
  await page.getByLabel("Start month").fill("2022-01");
  await page.getByLabel("Ongoing").check();
  await expect(page.getByLabel("End month")).toBeDisabled();
  await (await markdownSource(page, "Responsibilities")).fill("Build useful products");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/jobs\/\d+$/);
  const jobUrl = page.url();
  await page.reload();
  await expect(await markdownSource(page, "Responsibilities")).toHaveValue(
    "Build useful products",
  );
  await (await markdownSource(page, "Achievements")).fill("Shipped a search platform");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Changes saved");

  await page.getByRole("link", { name: "Add project" }).click();
  await expect(page.getByLabel("Job", { exact: true })).toHaveValue(
    jobUrl.split("/").pop()!,
  );
  await page.getByLabel("Project name").fill("Search platform");
  await (await markdownSource(page, "Overview")).fill("Find relevant experience");
  await page.getByRole("checkbox", { name: "TypeScript 6" }).check();
  await page.getByLabel("Skills", { exact: true }).fill("PostgreSQL");
  await page.getByRole("button", { name: "Create “PostgreSQL”" }).click();
  await expect(
    page.getByRole("checkbox", { name: "PostgreSQL" }),
  ).toBeChecked();
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/projects\/\d+$/);
  const projectUrl = page.url();
  await page.reload();
  await expect(
    page.getByRole("checkbox", { name: "TypeScript 6" }),
  ).toBeChecked();
  await (await markdownSource(page, "Outcomes")).fill("Unsaved outcome");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await expect(page).toHaveURL(projectUrl);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(await markdownSource(page, "Outcomes")).toHaveValue("");
  await captureThemes(page, "project-editor");

  await page.goto(jobUrl);
  await expect(
    page.getByRole("link", { name: /Search platform/ }),
  ).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete Software engineer" }).click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText(
    "Reassign, unlink, or delete",
  );
  await page.goto(projectUrl);
  await page.getByLabel("Job", { exact: true }).selectOption("");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Changes saved");
  await page
    .getByRole("link", { name: "Projects", exact: true })
    .first()
    .click();
  await page
    .getByLabel("Project type", { exact: true })
    .selectOption("professional");
  await expect(page.getByText("No matching projects.")).toBeVisible();
  await page
    .getByLabel("Project type", { exact: true })
    .selectOption("personal");
  await expect(
    page.getByRole("link", { name: /Search platform/ }),
  ).toBeVisible();
  await page.getByLabel("Search projects").fill("absent");
  await expect(page.getByText("No matching projects.")).toBeVisible();
  await page.getByLabel("Search projects").fill("");
  await captureThemes(page, "projects");
  page.on("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Actions for Search platform" })
    .click();
  await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
  await expect(
    page.getByText("No projects yet.", { exact: false }),
  ).toBeVisible();
  await page.goto(jobUrl);
  await page.getByRole("button", { name: "Delete Software engineer" }).click();
  await expect(page).toHaveURL(/\/admin\/jobs$/);
  await page.getByRole("link", { name: "Skills", exact: true }).click();
  await page.getByRole("button", { name: "Actions for TypeScript 6" }).click();
  await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
  await expect(page.getByText("TypeScript 6", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Actions for PostgreSQL" }).click();
  await page.getByRole("menuitem", { name: "Delete", exact: true }).click();
  await expect(
    page.getByText("No skills yet.", { exact: false }),
  ).toBeVisible();
});

test("edits Markdown visually and as source without losing draft content", async ({ page }) => {
  await page.goto("/admin/projects/new");
  await page.getByLabel("Project name").fill("Markdown portfolio example");
  const overview = "## Platform\n\nI built **reliable search** and [documentation](https://example.com).\n\n- Search\n  - Nested detail\n- [x] Released\n\n| Area | Result |\n| --- | --- |\n| Search | Faster |\n\n```python\nprint('hello')\n```\n";
  await (await markdownSource(page, "Overview")).fill(overview);
  const field = page.getByRole("group", { name: "Overview", exact: true });
  await field.getByRole("button", { name: "Visual", exact: true }).click();
  await expect(field.locator("strong")).toHaveText("reliable search");
  await expect(field.getByRole("table")).toBeVisible();
  await expect(await markdownSource(page, "Overview")).toHaveValue(overview);

  await (await markdownSource(page, "Overview")).fill("");
  await field.getByRole("button", { name: "Visual", exact: true }).click();
  const visual = field.locator(".markdown-prose[contenteditable=true]");
  await visual.fill("A useful platform");
  await visual.press("ControlOrMeta+a");
  await field.getByRole("radio", { name: "Bold", exact: true }).click();
  await expect(await markdownSource(page, "Overview")).toHaveValue("**A useful platform**");
  const contribution = "    preserved indentation\n\nI delivered **retrieval** and *testing*.\n\n";
  await (await markdownSource(page, "My contribution")).fill(contribution);
  await page.getByLabel("Small Summary", { exact: true }).fill("Built a useful search platform.");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/projects\/\d+$/);
  const endpoint = `/api/admin/projects/${page.url().split("/").pop()}`;
  await page.reload();
  await expect(page.getByText("All changes saved", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeDisabled();
  await expect(await markdownSource(page, "My contribution")).toHaveValue(contribution);
  await expect(await markdownSource(page, "Overview")).toHaveValue("**A useful platform**");
  const saved = await (await page.request.get(endpoint)).json();
  expect(saved.contribution).toBe(contribution);
  expect(saved.small_summary).toBe("Built a useful search platform.");

  const contributionField = page.getByRole("group", { name: "My contribution", exact: true });
  await contributionField.getByRole("button", { name: "Visual", exact: true }).click();
  await expect(contributionField.locator(".cm-content")).toContainText("preserved indentation");
  const contributionParagraph = contributionField.locator(".markdown-prose > p").filter({ hasText: "I delivered" });
  await contributionParagraph.click();
  await page.keyboard.press("End");
  await page.keyboard.insertText(" Updated.");
  const editedContribution = await (await markdownSource(page, "My contribution")).inputValue();
  expect(editedContribution).toMatch(/^```[^\n]*\npreserved indentation\n```/);
  expect(editedContribution).toContain("Updated.");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(await markdownSource(page, "My contribution")).toHaveValue(contribution);

  await (await markdownSource(page, "Outcomes")).fill("x".repeat(8001));
  await expect(page.getByRole("button", { name: "Save changes", exact: true })).toBeDisabled();
  await expect(page.getByRole("group", { name: "Outcomes", exact: true }).getByRole("alert")).toContainText("shorten this field");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(await markdownSource(page, "Outcomes")).toHaveValue("");
  await expect(page.getByText("All changes saved", { exact: true })).toBeVisible();

  const unsupported = "![A diagram](https://example.com/diagram.png)";
  await (await markdownSource(page, "Description")).fill(unsupported);
  const description = page.getByRole("group", { name: "Description", exact: true });
  await description.getByRole("button", { name: "Visual", exact: true }).click();
  await expect(description.getByRole("alert")).toContainText("Your Markdown is preserved");
  await description.getByRole("button", { name: "Edit Markdown", exact: true }).click();
  await expect(description.getByRole("textbox")).toHaveValue(unsupported);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  expect((await page.request.delete(endpoint, { headers: { Origin: new URL(page.url()).origin } })).status()).toBe(204);
});

test("generates a bounded small summary from the current unsaved Overview", async ({ page }) => {
  await page.goto("/admin/jobs/new");
  const button = page.getByRole("button", { name: "AI Generation", exact: true });
  await expect(button).toBeDisabled();
  await (await markdownSource(page, "Overview")).fill("\n\n");
  await expect(button).toBeDisabled();
  const overview = "I built **search** and supported a team.";
  await (await markdownSource(page, "Overview")).fill(overview);
  await page.getByRole("group", { name: "Responsibilities", exact: true }).locator(".markdown-prose[contenteditable=true]").fill("Keep this unsaved responsibility");
  await page.getByLabel("Small Summary", { exact: true }).fill("Existing draft");
  let complete!: () => void;
  const responseReady = new Promise<void>((resolve) => { complete = resolve; });
  await page.route("**/api/admin/content/small-summary", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ overview });
    await responseReady;
    await route.fulfill({ json: { small_summary: "Built search and supported a team." } });
  });
  await button.click();
  await expect(page.getByRole("button", { name: "Generating…", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Create", exact: true })).toBeDisabled();
  await expect(page.getByRole("textbox", { name: "Overview Markdown", exact: true })).toBeDisabled();
  complete();
  await expect(page.getByLabel("Small Summary", { exact: true })).toHaveValue("Built search and supported a team.");
  await expect(await markdownSource(page, "Responsibilities")).toHaveValue("Keep this unsaved responsibility");
  await expect(page).toHaveURL(/\/admin\/jobs\/new$/);
  await expect(page.getByText("You have unsaved changes", { exact: true })).toBeVisible();
  await page.unroute("**/api/admin/content/small-summary");
  await page.route("**/api/admin/content/small-summary", (route) => route.fulfill({ status: 503, json: { detail: "Generation unavailable. Try again." } }));
  await button.click();
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Generation unavailable");
  await expect(page.getByLabel("Small Summary", { exact: true })).toHaveValue("Built search and supported a team.");
  await page.getByLabel("Small Summary", { exact: true }).fill("x".repeat(300));
  await expect(page.getByLabel("Small Summary", { exact: true })).toHaveValue("x".repeat(280));
  await page.getByLabel("Small Summary", { exact: true }).fill("🚀".repeat(280));
  await expect(page.getByLabel("Small Summary", { exact: true })).toHaveValue("🚀".repeat(280));
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByLabel("Small Summary", { exact: true })).toHaveValue("");
  await expect(button).toBeDisabled();
});

test("uploads, renames, replaces, downloads, and deletes PDFs", async ({
  page,
}) => {
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await page.getByRole("link", { name: "Add document" }).click();
  await page.getByLabel("Title", { exact: true }).fill("English resume");
  await page.getByLabel("Resume PDF").setInputFiles({
    name: "resume.pdf",
    mimeType: "application/pdf",
    buffer: pdf,
  });
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/documents\/\d+$/);
  const id = page.url().split("/").pop();
  const endpoint = `/api/admin/documents/${id}`;
  await page.reload();
  await expect(page.getByText("resume.pdf", { exact: true })).toBeVisible();
  await page.getByLabel("Title", { exact: true }).fill("Updated resume");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Document saved");
  expect(await (await page.request.get(`${endpoint}/file`)).body()).toEqual(
    pdf,
  );
  const headers = { Origin: new URL(page.url()).origin };
  const rejected = await page.request.put(endpoint, {
    headers,
    multipart: {
      title: "Rejected title",
      file: {
        name: "invalid.pdf",
        mimeType: "application/pdf",
        buffer: Buffer.from("invalid"),
      },
    },
  });
  expect(rejected.status()).toBe(422);
  expect((await (await page.request.get(endpoint)).json()).title).toBe(
    "Updated resume",
  );
  expect(await (await page.request.get(`${endpoint}/file`)).body()).toEqual(
    pdf,
  );
  for (const bytes of [10 * 1024 * 1024 + 1, 11 * 1024 * 1024 + 1]) {
    const oversized = await page.request.put(endpoint, {
      headers,
      multipart: {
        title: "Too large",
        file: {
          name: "large.pdf",
          mimeType: "application/pdf",
          buffer: Buffer.concat([
            Buffer.from("%PDF-"),
            Buffer.alloc(bytes - 5),
          ]),
        },
      },
    });
    expect(oversized.status()).toBe(413);
  }
  const replacement = Buffer.concat([pdf, Buffer.from("\n% updated")]);
  await page.getByLabel("Replace PDF").setInputFiles({
    name: "updated.pdf",
    mimeType: "application/pdf",
    buffer: replacement,
  });
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("updated.pdf", { exact: true })).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download PDF" }).click();
  const download = await downloaded;
  expect(download.suggestedFilename()).toBe("updated.pdf");
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream!) chunks.push(Buffer.from(chunk));
  expect(Buffer.concat(chunks)).toEqual(replacement);
  await captureThemes(page, "document-editor");
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete Updated resume" }).click();
  await expect(page).toHaveURL(/\/admin\/documents$/);
  expect((await page.request.get(`${endpoint}/file`)).status()).toBe(404);
});

test("content navigation and forms fit mobile screens", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const section of ["Jobs", "Projects", "Skills", "Documents"]) {
    await page.getByRole("button", { name: "Open navigation" }).click();
    await page.getByRole("link", { name: section, exact: true }).click();
    await expect(
      page.getByRole("heading", { name: section, exact: true }),
    ).toBeVisible();
    await expect(page.locator(".admin-topbar")).toContainText(section);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.goto("/admin/projects/new");
  for (const width of [390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await captureThemes(page, "content-mobile");
});
