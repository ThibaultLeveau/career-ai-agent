import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { captureThemes, setTheme } from "./theme";

const prefix = "Public browse";
const jobs: { id: number; title: string; company: string }[] = [];
const projects: { id: number; name: string }[] = [];
const skills: { id: number; keyword: string }[] = [];
let admin: APIRequestContext;

async function create<T>(collection: string, data: object): Promise<T> {
  const response = await admin.post(`/api/admin/${collection}`, { data });
  expect(response.status(), await response.text()).toBe(201);
  return response.json();
}

function cards(page: Page, collection: "jobs" | "projects") {
  return page.locator(`main a[href^="/${collection}/"]`);
}

function recordLink(page: Page, collection: "jobs" | "projects", id: number) {
  return page.locator(`main a[href="/${collection}/${id}"], main a[href^="/${collection}/${id}?"]`);
}

async function expectQuery(page: Page, name: string, value: string | null) {
  await expect.poll(() => new URL(page.url()).searchParams.get(name)).toBe(value);
}

test.beforeAll(async ({ playwright, baseURL }) => {
  admin = await playwright.request.newContext({
    baseURL,
    extraHTTPHeaders: { Origin: new URL(baseURL!).origin },
  });
  const login = await admin.post("/api/admin/login", {
    data: {
      username: process.env.ADMIN_INITIAL_USERNAME!,
      password: process.env.ADMIN_INITIAL_PASSWORD!,
    },
  });
  expect(login.ok()).toBe(true);
  for (const keyword of [`${prefix} TypeScript`, `${prefix} Python`]) {
    skills.push(await create("skills", { keyword }));
  }
  for (let index = 1; index <= 14; index++) {
    const start = index === 1 ? null : `${2023 + Math.floor((index - 1) / 12)}-${String((index - 1) % 12 + 1).padStart(2, "0")}`;
    const ongoing = index % 2 === 0;
    const job = await create<(typeof jobs)[number]>("jobs", {
      title: `${prefix} role ${String(index).padStart(2, "0")}`,
      company: `${prefix} ${index % 3 === 0 ? "studio" : "lab"}`,
      location: "Paris",
      start_month: start,
      ongoing,
      small_summary: "Built useful engineering tools and supported a team.",
      summary: index === 1 ? "" : "An **engineering** overview.\n\n[Documentation](https://example.com/docs)",
      responsibilities: index === 1 ? "search-only-responsibility" : "- Built the **search pipeline**\n- Supported delivery",
      achievements: index === 1 ? "" : "Improved reliability.",
    });
    jobs.push(job);
    projects.push(await create("projects", {
      name: `${prefix} project ${String(index).padStart(2, "0")}`,
      role: "Software engineer",
      start_month: start,
      ongoing,
      job_id: job.id,
      skill_ids: [skills[ongoing ? 0 : 1].id],
      small_summary: "Delivered reliable engineering tools and searchable documentation. ".repeat(4).slice(0, 280),
      summary: "A **reliable platform** for the team.",
      description: "| Area | Result |\n| --- | --- |\n| Search | Faster |",
      contribution: "Built **retrieval** and [documentation](https://example.com/docs).\n\n<script>alert(1)</script>\n\n[unsafe](javascript:alert(1))",
      outcomes: "",
      website_url: "https://example.com",
      repository_url: "https://github.com/example/project",
    }));
  }
  projects.push(await create("projects", {
    name: `${prefix} side project`,
    skill_ids: [skills[0].id],
  }));
});

test.afterAll(async () => {
  if (!admin) return;
  for (const [collection, records] of [["projects", projects], ["jobs", jobs], ["skills", skills]] as const) {
    for (const record of records) {
      const response = await admin.delete(`/api/admin/${collection}/${record.id}`);
      expect([204, 404]).toContain(response.status());
    }
  }
  await admin.dispose();
});

test("jobs paginate and combine complete-catalog filters without a chat request", async ({ page, context }) => {
  const chatRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/chat")) chatRequests.push(request.url());
  });
  await page.goto(`/jobs?q=${encodeURIComponent(prefix)}`);
  expect((await context.cookies()).some((cookie) => cookie.name === "career_admin")).toBe(false);
  await expect(page.getByRole("heading", { level: 1, name: "The roles behind the work.", exact: true })).toBeVisible();
  await expect(cards(page, "jobs")).toHaveCount(12);
  await expect(recordLink(page, "jobs", jobs[13].id)).toBeVisible();
  await expect(recordLink(page, "jobs", jobs[0].id)).toHaveCount(0);
  await page.getByRole("link", { name: /^Next/ }).click();
  await expectQuery(page, "page", "2");
  await expect(cards(page, "jobs")).toHaveCount(2);
  const listUrl = page.url();
  await recordLink(page, "jobs", jobs[0].id).click();
  await expect(page.getByRole("heading", { level: 1, name: jobs[0].title })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Achievements", exact: true })).toHaveCount(0);
  await expect(page.getByRole("main")).not.toContainText("Invalid Date");
  await page.getByRole("link", { name: "Back to jobs", exact: true }).click();
  await expect(page).toHaveURL(listUrl);
  await expect(cards(page, "jobs")).toHaveCount(2);
  await recordLink(page, "jobs", jobs[0].id).click();
  await expect(page.getByRole("heading", { level: 1, name: jobs[0].title })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(listUrl);
  await page.getByLabel("Search jobs", { exact: true }).fill("search-only-responsibility");
  await expectQuery(page, "q", "search-only-responsibility");
  await expectQuery(page, "page", null);
  await expect(cards(page, "jobs")).toHaveCount(1);
  await expect(recordLink(page, "jobs", jobs[0].id)).toBeVisible();
  await expect(page.getByLabel("Search jobs", { exact: true })).toBeFocused();
  await page.keyboard.insertText("-missing");
  await expectQuery(page, "q", "search-only-responsibility-missing");
  await expect(cards(page, "jobs")).toHaveCount(0);
  await expect(page.getByLabel("Search jobs", { exact: true })).toBeFocused();

  await page.goto("/jobs");
  await page.getByLabel("Search jobs", { exact: true }).fill(prefix);
  await page.getByLabel("Company", { exact: true }).selectOption(`${prefix} studio`);
  await expectQuery(page, "q", prefix);
  await expectQuery(page, "company", `${prefix} studio`);
  await page.getByLabel("Status", { exact: true }).selectOption("ongoing");
  await expectQuery(page, "status", "ongoing");
  await page.getByLabel("Skill", { exact: true }).selectOption(String(skills[0].id));
  await expectQuery(page, "skill_id", String(skills[0].id));
  await expect(cards(page, "jobs")).toHaveCount(2);
  await expect(page.getByLabel("Company", { exact: true }).locator("option")).toContainText(["All companies", `${prefix} lab`, `${prefix} studio`]);
  await expect(page.getByLabel("Skill", { exact: true }).locator(`option[value="${skills[1].id}"]`)).toHaveCount(1);
  await page.getByLabel("Skill", { exact: true }).selectOption(String(skills[1].id));
  await expect(cards(page, "jobs")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "No jobs match these filters.", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByLabel("Skill", { exact: true })).toHaveValue(String(skills[0].id));
  await expect(cards(page, "jobs")).toHaveCount(2);
  await page.goForward();
  await expect(page.getByLabel("Skill", { exact: true })).toHaveValue(String(skills[1].id));
  await expect(cards(page, "jobs")).toHaveCount(0);
  await page.getByRole("button", { name: "Clear filters", exact: true }).click();
  await expectQuery(page, "q", null);
  await expectQuery(page, "company", null);
  await expect(page.getByLabel("Search jobs", { exact: true })).toHaveValue("");
  expect(chatRequests).toEqual([]);
});

test("projects filter by type, experience, skill, and status across pages", async ({ page }) => {
  await page.goto(`/projects?q=${encodeURIComponent(prefix)}`);
  await expect(page.getByRole("heading", { level: 1, name: "Ideas, built into something real.", exact: true })).toBeVisible();
  await expect(cards(page, "projects")).toHaveCount(12);
  await page.getByRole("link", { name: /^Next/ }).click();
  await expectQuery(page, "page", "2");
  await expect(cards(page, "projects")).toHaveCount(3);
  await expect(recordLink(page, "projects", projects[14].id)).toBeVisible();
  await page.getByLabel("Type", { exact: true }).selectOption("professional");
  await expectQuery(page, "kind", "professional");
  await expectQuery(page, "page", null);
  await page.getByLabel("Experience", { exact: true }).selectOption(String(jobs[13].id));
  await expectQuery(page, "job_id", String(jobs[13].id));
  await page.getByLabel("Skill", { exact: true }).selectOption(String(skills[0].id));
  await expectQuery(page, "skill_id", String(skills[0].id));
  await page.getByLabel("Status", { exact: true }).selectOption("ongoing");
  await expectQuery(page, "status", "ongoing");
  await expect(cards(page, "projects")).toHaveCount(1);
  await expect(recordLink(page, "projects", projects[13].id)).toBeVisible();
  await expect(page.getByLabel("Experience", { exact: true }).locator(`option[value="${jobs[0].id}"]`)).toHaveCount(1);
  const filteredUrl = page.url();
  await recordLink(page, "projects", projects[13].id).click();
  await page.getByRole("link", { name: "Back to projects", exact: true }).click();
  await expect.poll(() => [...new URL(page.url()).searchParams].sort()).toEqual([...new URL(filteredUrl).searchParams].sort());
  await page.getByLabel("Type", { exact: true }).selectOption("personal");
  await expect(cards(page, "projects")).toHaveCount(0);
  await page.getByLabel("Experience", { exact: true }).selectOption("");
  await expectQuery(page, "job_id", null);
  await page.getByLabel("Status", { exact: true }).selectOption("past");
  await expect(cards(page, "projects")).toHaveCount(1);
  await expect(recordLink(page, "projects", projects[14].id)).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Type", { exact: true })).toHaveValue("personal");
  await expect(recordLink(page, "projects", projects[14].id)).toBeVisible();
});

test("detail pages render safe narratives, link relationships, and reflect current records", async ({ page }) => {
  const job = jobs[13];
  const project = projects[13];
  await page.goto(`/jobs/${job.id}`);
  await expect(page).toHaveTitle(new RegExp(job.title));
  await expect(page.getByRole("heading", { name: "Responsibilities", exact: true })).toBeVisible();
  await expect(page.getByRole("main").locator("strong").filter({ hasText: "search pipeline" })).toBeVisible();
  await expect(page.getByRole("main")).toContainText(skills[0].keyword);
  await recordLink(page, "projects", project.id).click();
  await expect(page.getByRole("heading", { level: 1, name: project.name })).toBeVisible();
  await page.reload();
  await expect(page).toHaveTitle(new RegExp(project.name));
  await expect(page.getByRole("heading", { level: 1, name: project.name })).toBeVisible();
  await expect(page.getByRole("main").locator("strong").filter({ hasText: "reliable platform" })).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("main").locator("strong").filter({ hasText: "retrieval" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Outcomes", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Visit website", exact: true })).toHaveAttribute("href", "https://example.com");
  await expect(page.getByRole("link", { name: "View repository", exact: true })).toHaveAttribute("href", "https://github.com/example/project");
  await expect(page.locator("main script, main a[href^='javascript:']")).toHaveCount(0);
  await recordLink(page, "jobs", job.id).click();
  await expect(page.getByRole("heading", { level: 1, name: job.title })).toBeVisible();

  const updated = await admin.put(`/api/admin/projects/${project.id}`, {
    data: { name: project.name, job_id: job.id, summary: "Freshly updated public overview.", skill_ids: [skills[0].id] },
  });
  expect(updated.ok()).toBe(true);
  await page.goto(`/projects/${project.id}`);
  await expect(page.getByText("Freshly updated public overview.", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "About the project", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Visit website", exact: true })).toHaveCount(0);
  for (const path of ["/jobs/not-an-id", "/projects/999999999"]) {
    const response = await page.goto(path);
    expect(response?.status()).toBe(404);
    await expect(page.getByRole("main")).toContainText(/not found|couldn.t find/i);
  }
});

test("public navigation supports keyboards and themes on narrow screens with reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const navigation = page.getByRole("navigation", { name: "Main navigation", exact: true });
  const experiences = navigation.getByRole("button", { name: "Experiences", exact: true });
  await experiences.focus();
  await page.keyboard.press("Enter");
  await expect(experiences).toHaveAttribute("aria-expanded", "true");
  await expect(navigation.getByRole("link", { name: /^Jobs/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(experiences).toHaveAttribute("aria-expanded", "false");
  await expect(experiences).toBeFocused();
  await experiences.click();
  await navigation.getByRole("link", { name: /^Jobs/ }).click();
  await expect(page).toHaveURL(/\/jobs$/);
  await experiences.click();
  await expect(navigation.getByRole("link", { name: /^Jobs/ })).toHaveAttribute("aria-current", "page");
  await navigation.getByRole("link", { name: /^Projects/ }).click();
  await expect(page).toHaveURL(/\/projects$/);

  for (const path of ["/jobs", "/projects", `/jobs/${jobs[13].id}`, `/projects/${projects[0].id}`]) {
    await page.goto(path);
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const theme of ["light", "dark"] as const) {
        await setTheme(page, theme);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await captureThemes(page, `public-${path.slice(1).replaceAll("/", "-")}`);
  }
});
