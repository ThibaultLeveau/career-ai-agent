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
  await page.getByLabel("Responsibilities").fill("Build useful products");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/jobs\/\d+$/);
  const jobUrl = page.url();
  await page.reload();
  await expect(page.getByLabel("Responsibilities")).toHaveValue(
    "Build useful products",
  );
  await page.getByLabel("Achievements").fill("Shipped a search platform");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Changes saved");

  await page.getByRole("link", { name: "Add project" }).click();
  await expect(page.getByLabel("Job", { exact: true })).toHaveValue(
    jobUrl.split("/").pop()!,
  );
  await page.getByLabel("Project name").fill("Search platform");
  await page
    .getByLabel("Summary", { exact: true })
    .fill("Find relevant experience");
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
  await page.getByLabel("Outcomes").fill("Unsaved outcome");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: "Jobs", exact: true }).click();
  await expect(page).toHaveURL(projectUrl);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByLabel("Outcomes")).toHaveValue("");
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
