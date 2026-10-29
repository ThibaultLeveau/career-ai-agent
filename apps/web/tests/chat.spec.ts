import { expect, test, type Page } from "@playwright/test";
import { captureThemes, expectTheme, setTheme } from "./theme";

type ChatRequest = {
  message: string;
  history: { role: "user" | "assistant"; content: string; components?: { type: string; id: number; label: string }[] }[];
  action?: { type: string; token: string };
};
type Reply = {
  parts?: string[];
  delay?: number;
  fragmentBytes?: number;
  open?: boolean;
  status?: number;
  detail?: string;
};
type Harness = Window & {
  chatRequests: ChatRequest[];
  chatAborts: number;
};

function reply(text: string, sources: unknown[] = []): Reply {
  return {
    parts: [
      `event: delta\ndata: ${JSON.stringify({ text })}\n\n`,
      `event: done\ndata: ${JSON.stringify({ sources })}\n\n`,
    ],
  };
}

async function mockChat(page: Page, replies: Reply[]) {
  await page.addInitScript((responses) => {
    const harness = window as unknown as Harness;
    harness.chatRequests = [];
    harness.chatAborts = 0;
    const original = window.fetch.bind(window);
    window.fetch = async (url, init) => {
      if (String(url) !== "/api/chat") return original(url, init);
      const index = harness.chatRequests.length;
      harness.chatRequests.push(JSON.parse(String(init?.body)) as ChatRequest);
      const response = responses[index] ?? responses[responses.length - 1];
      if (response.status)
        return new Response(JSON.stringify({ detail: response.detail }), {
          status: response.status,
          headers: { "Content-Type": "application/json" },
        });
      const encoder = new TextEncoder();
      const bytes = encoder.encode((response.parts ?? []).join(""));
      const parts = response.fragmentBytes
        ? Array.from({ length: Math.ceil(bytes.length / response.fragmentBytes) }, (_, part) =>
            bytes.slice(part * response.fragmentBytes!, (part + 1) * response.fragmentBytes!),
          )
        : (response.parts ?? []).map((part) => encoder.encode(part));
      let timer: ReturnType<typeof setTimeout> | undefined;
      let closed = false;
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          let part = 0;
          function next() {
            if (closed) return;
            if (part < parts.length) {
              controller.enqueue(parts[part++]);
              timer = setTimeout(next, response.delay ?? 5);
            } else if (!response.open) {
              closed = true;
              controller.close();
            }
          }
          init?.signal?.addEventListener("abort", () => {
            harness.chatAborts += 1;
            clearTimeout(timer);
            if (!closed) {
              closed = true;
              controller.error(new DOMException("Aborted", "AbortError"));
            }
          }, { once: true });
          timer = setTimeout(next, response.delay ?? 5);
        },
        cancel() {
          closed = true;
          clearTimeout(timer);
        },
      });
      return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
    };
  }, replies);
}

async function requests(page: Page): Promise<ChatRequest[]> {
  return page.evaluate(() => (window as unknown as Harness).chatRequests);
}

test("public homepage makes the conversation clear on desktop and mobile", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/Thibault Leveau/);
  await expect(page.getByRole("heading", { name: "Hi, I’m Thibault. Let’s talk about my work." })).toBeVisible();
  await expect(page.getByText("AI assistant", { exact: true })).toHaveCount(0);
  const brand = page.getByRole("link", { name: "Thibault Leveau, home" });
  await expect(brand).toHaveText("Thibault Leveau");
  await expect(brand.locator("svg")).toHaveCount(1);
  await expect(page.locator(".portfolio-header small, .portfolio-footer, .chat-disclosure")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Send message" })).toBeDisabled();
  await expect(page.getByRole("combobox")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /admin/i })).toHaveCount(0);
  await captureThemes(page, "portfolio-desktop");
  for (const width of [320, 390, 768]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(page.getByRole("button", { name: "The career overview" })).toBeVisible();
    await expect(page.getByLabel("Ask about my career")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await captureThemes(page, "portfolio-mobile");
});

test("parses fragmented UTF-8 and CRLF streams, shows sources, and sends completed history", async ({ page }) => {
  const sources = [{ id: "S1", label: "Career résumé", source_type: "document", page_start: 1, page_end: 2 }];
  const first = reply("I build **useful tools** for café teams.", sources);
  first.parts = [": connected\r\n\r\n", ...first.parts!.map((part) => part.replaceAll("\n", "\r\n"))];
  first.fragmentBytes = 1;
  first.delay = 1;
  await mockChat(page, [first, reply("I worked closely with the team.")]);
  await page.goto("/");
  await page.getByRole("button", { name: "The career overview" }).click();
  await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
  await expect(page.locator(".answer-content")).toContainText("I build useful tools for café teams.");
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
  await page.getByText("Sources", { exact: false }).click();
  await expect(page.getByText("Career résumé", { exact: true })).toBeVisible();
  await expect(page.getByText("Pages 1–2")).toBeVisible();
  await page.getByLabel("Ask about my career").fill("How did you collaborate?");
  await page.getByLabel("Ask about my career").press("Enter");
  await expect(page.locator(".answer-content").last()).toHaveText("I worked closely with the team.");
  expect((await requests(page))[1]).toEqual({
    message: "How did you collaborate?",
    history: [
      { role: "user", content: "Give me an overview of your career." },
      { role: "assistant", content: "I build **useful tools** for café teams." },
    ],
  });
  await captureThemes(page, "portfolio-conversation");
  await page.setViewportSize({ width: 390, height: 844 });
  await captureThemes(page, "portfolio-conversation-mobile");
});

test("shows agent activity before the answer and keeps it out of completed history", async ({ page }) => {
  await mockChat(page, [{
    delay: 150,
    parts: [
      'event: status\ndata: {"stage":"database","message":"Searching for AI and PHP in the same project…"}\n\n',
      'event: status\ndata: {"stage":"fallback","message":"No combined match found. Searching AI and PHP separately…"}\n\n',
      ...reply("I found separate examples.").parts!,
    ],
  }, reply("Here is more detail.")]);
  await page.goto("/");
  await page.getByLabel("Ask about my career").fill("Show AI projects using PHP.");
  await page.getByLabel("Ask about my career").press("Enter");
  await expect(page.locator(".thinking")).toContainText("Searching for AI and PHP");
  await expect(page.locator(".thinking")).toContainText("No combined match found");
  await expect(page.locator(".answer-content")).toHaveText("I found separate examples.");
  await expect(page.locator(".thinking")).toHaveCount(0);
  await page.getByLabel("Ask about my career").fill("Tell me more.");
  await page.getByLabel("Ask about my career").press("Enter");
  await expect(page.locator(".answer-content").last()).toHaveText("Here is more detail.");
  expect((await requests(page))[1].history[1].content).toBe("I found separate examples.");
});

test("accepts fragmented UTF-8 status events and cancels before answer generation", async ({ page }) => {
  const status = 'event: status\r\ndata: {"stage":"database","message":"Recherche de projets café…"}\r\n\r\n';
  await mockChat(page, [{ parts: [status], fragmentBytes: 1, delay: 1, open: true }, reply("A fresh answer.")]);
  await page.goto("/");
  await page.getByRole("button", { name: "The career overview" }).click();
  await expect(page.locator(".thinking")).toContainText("Recherche de projets café…");
  await page.getByRole("button", { name: "Stop response" }).click();
  await expect(page.locator(".thinking")).toHaveCount(0);
  await expect(page.getByText("Response stopped.", { exact: true }).first()).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as Harness).chatAborts)).toBe(1);
  await page.getByLabel("Ask about my career").fill("A new question");
  await page.getByLabel("Ask about my career").press("Enter");
  await expect(page.locator(".answer-content")).toHaveText("A fresh answer.");
  expect((await requests(page))[1].history).toEqual([]);
});

test("renders safe markdown tables and lists within narrow screens", async ({ page }) => {
  const markdown = "## Python projects\n\n1. **Data platform**\n2. Automation tools\n\n| Project | Skills | Role | Impact | Period |\n| --- | --- | --- | --- | --- |\n| Data platform | Python, AI | Developer | Faster analysis | 2024 |\n\n- Grounded example\n- Another example\n\n[Project website](https://example.com/project) [Unsafe](javascript:alert%281%29) [Private](/admin/projects/1)\n\n<img src=x onerror=alert(1)>\n\n![Tracking image](https://example.com/tracker.png)\n\n<script>alert(1)</script>";
  await mockChat(page, [reply(markdown)]);
  await page.goto("/");
  await page.getByRole("button", { name: "The career overview" }).click();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.locator(".answer-content ol li")).toHaveCount(2);
  await expect(page.locator(".answer-content ul li")).toHaveCount(2);
  await expect(page.getByRole("link", { name: "Project website" })).toHaveAttribute("rel", "noopener noreferrer");
  await expect(page.locator(".answer-content a")).toHaveCount(1);
  await expect(page.locator(".answer-content img, .answer-content script")).toHaveCount(0);
  for (const width of [320, 390, 768]) {
    await page.setViewportSize({ width, height: 844 });
    for (const theme of ["light", "dark"] as const) {
      await setTheme(page, theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect(page.getByRole("region", { name: "Answer table" })).toBeVisible();
    }
  }
  await captureThemes(page, "portfolio-markdown");
});

test("theme changes preserve the draft and an active streamed reply", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await mockChat(page, [{
    parts: ['event: delta\ndata: {"text":"I built a useful platform."}\n\n'],
    open: true,
  }]);
  await page.goto("/");
  const input = page.getByLabel("Ask about my career");
  await input.fill("Tell me about your projects.");
  await setTheme(page, "dark");
  await expect(input).toHaveValue("Tell me about your projects.");
  expect(await requests(page)).toHaveLength(0);
  await input.press("Enter");
  await expect(page.locator(".answer-content")).toHaveText("I built a useful platform.");
  await input.fill("What was your role on that project?");
  for (const theme of ["light", "dark"] as const) {
    await setTheme(page, theme);
    await expectTheme(page, theme);
    await expect(input).toHaveValue("What was your role on that project?");
    await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
    await expect(page.locator(".answer-content")).toHaveText("I built a useful platform.");
    expect(await requests(page)).toHaveLength(1);
    expect(await page.evaluate(() => (window as unknown as Harness).chatAborts)).toBe(0);
  }
  await page.getByRole("button", { name: "Stop response" }).click();
  expect(await page.evaluate(() => (window as unknown as Harness).chatAborts)).toBe(1);
  expect(await requests(page)).toHaveLength(1);
  await expect(input).toHaveValue("What was your role on that project?");
});

test("interrupted and error responses stay out of history and can be retried", async ({ page }) => {
  await mockChat(page, [
    { parts: ['event: delta\ndata: {"text":"A partial answer."}\n\n'] },
    { parts: ['event: error\ndata: {"message":"Please try again shortly."}\n\n'] },
    reply("A complete answer."),
    reply("A follow-up answer."),
  ]);
  await page.goto("/");
  await page.getByLabel("Ask about my career").fill("Tell me about your projects.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByRole("log").getByRole("alert")).toContainText("connection was interrupted");
  await expect(page.locator(".answer-content")).toHaveText("A partial answer.");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("log").getByRole("alert")).toHaveText("Please try again shortly.");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator(".answer-content")).toHaveText("A complete answer.");
  expect((await requests(page)).map((request) => request.history)).toEqual([[], [], []]);
  await page.getByLabel("Ask about my career").fill("What did you learn?");
  await page.getByLabel("Ask about my career").press("Enter");
  await expect(page.locator(".answer-content").last()).toHaveText("A follow-up answer.");
  expect((await requests(page))[3].history).toEqual([
    { role: "user", content: "Tell me about your projects." },
    { role: "assistant", content: "A complete answer." },
  ]);
});

test("stop and reset cancel streaming without leaking partial conversation into later requests", async ({ page }) => {
  const pending = { parts: ['event: delta\ndata: {"text":"Work in progress."}\n\n'], open: true };
  await mockChat(page, [pending, pending, reply("A fresh answer.")]);
  await page.goto("/");
  await page.getByRole("button", { name: "Projects & impact" }).click();
  await expect(page.locator(".answer-content")).toHaveText("Work in progress.");
  await page.getByRole("button", { name: "Stop response" }).click();
  await expect(page.getByText("Response stopped.", { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel("Ask about my career")).toBeFocused();
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator(".answer-content")).toHaveText("Work in progress.");
  await page.getByRole("button", { name: "New conversation" }).click();
  await expect(page.getByRole("heading", { name: /Hi, I’m Thibault/ })).toBeVisible();
  await expect(page.getByRole("log")).toHaveCount(0);
  await page.getByLabel("Ask about my career").fill("A new question");
  await page.getByLabel("Ask about my career").press("Enter");
  await expect(page.locator(".answer-content")).toHaveText("A fresh answer.");
  expect((await requests(page)).every((request) => request.history.length === 0)).toBe(true);
  expect(await page.evaluate(() => (window as unknown as Harness).chatAborts)).toBe(2);
});

test("keyboard composition preserves newlines and HTTP failures remain retryable", async ({ page }) => {
  await mockChat(page, [
    { status: 429, detail: "Please wait a moment before asking another question." },
    reply('<script>alert("unsafe")</script>\n\nI can discuss my experience.'),
  ]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const input = page.getByLabel("Ask about my career");
  await input.fill("First line");
  await input.press("Shift+Enter");
  await input.pressSequentially("Second line");
  expect(await requests(page)).toHaveLength(0);
  await expect(input).toHaveValue("First line\nSecond line");
  await input.press("Enter");
  await expect(page.getByRole("log").getByRole("alert")).toContainText("Please wait a moment");
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator(".answer-content")).toContainText("I can discuss my experience.");
  await expect(page.locator(".answer-content")).not.toContainText("alert(");
  await expect(page.locator(".answer-content script")).toHaveCount(0);
  expect((await requests(page))[0].message).toBe("First line\nSecond line");
  await expect(input).toHaveAttribute("maxlength", "4000");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("history is bounded to completed pairs and the public proxy rejects oversized input", async ({ page }) => {
  await mockChat(page, [reply("A useful answer.")]);
  await page.goto("/");
  for (let index = 0; index < 6; index++) {
    await page.getByLabel("Ask about my career").fill(`Question ${index}`);
    await page.getByLabel("Ask about my career").press("Enter");
    await expect(page.getByRole("button", { name: "Stop response" })).toHaveCount(0);
    await expect(page.locator(".answer-content")).toHaveCount(index + 1);
    await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
  }
  const history = (await requests(page))[5].history;
  expect(history).toHaveLength(8);
  expect(history[0]).toEqual({ role: "user", content: "Question 1" });
  const oversized = await page.request.post("/api/chat", { data: { message: "x".repeat(66000), history: [] } });
  expect(oversized.status()).toBe(413);
  expect(oversized.headers()["cache-control"]).toContain("no-store");
});

test("long responses remain above the composer and Unicode history fits the body budget", async ({ page }) => {
  await mockChat(page, [reply("経".repeat(9000)), reply("経".repeat(7900)), reply("経".repeat(7900)), reply("A concise answer.")]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  for (let index = 0; index < 4; index++) {
    await page.getByLabel("Ask about my career").fill(`Question ${index}`);
    await page.getByLabel("Ask about my career").press("Enter");
    await expect(page.locator(".answer-content")).toHaveCount(index + 1);
    await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
    const answer = await page.locator(".answer-content").last().boundingBox();
    const composer = await page.locator(".chat-composer").boundingBox();
    expect(answer!.y + answer!.height).toBeLessThanOrEqual(composer!.y);
  }
  const sent = await requests(page);
  expect(sent[1].history[1].content).toHaveLength(8000);
  expect(sent[3].history).toHaveLength(4);
  expect(new TextEncoder().encode(JSON.stringify(sent[3])).byteLength).toBeLessThanOrEqual(65536);
  await expect(page.locator(".answer-content").first()).toHaveText("経".repeat(9000));
});

function projectRecord(id: number) {
  return {
    id, name: id === 7 ? "Legacy migration" : `Project ${id}`, role: "Lead engineer",
    start_month: "2024-01", end_month: null, ongoing: true,
    summary: "Built reliable tools and improved delivery for the team.",
    kind: id === 7 ? "personal" : "professional",
    job: id === 7 ? null : { id: 21, title: "Software engineer", company: "Acme" },
    skills: ["Python", "PostgreSQL"], action: { type: "show_project", token: `project-${id}` },
  };
}
function jobRecord(id: number) {
  return {
    id, title: `Software engineer ${id}`, company: "Acme", location: "Paris",
    start_month: "2020-01", end_month: "2024-01", ongoing: false,
    summary: "Led engineering delivery and collaborated across teams.",
    action: { type: "show_job", token: `job-${id}` },
  };
}
function projectList(page = 1, filter = "") {
  const all = Array.from({ length: 7 }, (_, index) => projectRecord(index + 1));
  const matches = all.filter((item) => !filter || item.name.toLowerCase().includes(filter.toLowerCase()));
  return { type: "project_list", token: "verified-project-list", total: 7, matched_total: matches.length,
    page, page_size: 5, filter, items: matches.slice((page - 1) * 5, page * 5) };
}
function componentReply(components: unknown[], intro = "Here is how my recorded experience matches your question."): Reply {
  const result = reply(intro);
  result.parts!.splice(1, 0, ...components.map((component, index) =>
    `event: component\ndata: ${JSON.stringify({ introduction: `Explore this part of my work (${index + 1}).`, component })}\n\n`));
  return result;
}

test("project lists paginate and filter all matches without AI, then open a grounded card", async ({ page }) => {
  const card = { type: "project_card", record: { ...projectRecord(7), description: "A carefully planned migration with a gradual rollout.", outcomes: "Improved reliability and reduced support work." } };
  const first = componentReply([projectList()]);
  first.fragmentBytes = 37;
  first.delay = 1;
  await mockChat(page, [first, componentReply([card])]);
  let pageRequests = 0;
  await page.route("**/api/chat/components/page", async (route) => {
    pageRequests++;
    const { page: current, filter } = route.request().postDataJSON();
    await route.fulfill({ json: projectList(current, filter) });
  });
  await page.goto("/");
  await page.getByLabel("Ask about my career").fill("List all my Python projects");
  await page.getByRole("button", { name: "Send message" }).click();
  const list = page.getByRole("region", { name: "Projects list", exact: true });
  await expect(list.getByRole("button", { name: /^Know more about/ })).toHaveCount(5);
  await expect(list.getByRole("textbox")).toHaveCount(1);
  await expect(list.getByRole("status")).toHaveText("1–5 of 7");
  await expect(page.getByText("Explore this part of my work (1).", { exact: true })).toBeVisible();
  await list.getByRole("button", { name: "Next" }).click();
  await expect(list.getByRole("status")).toHaveText("6–7 of 7");
  await expect(list.getByRole("button", { name: /^Know more about/ })).toHaveCount(2);
  expect((await requests(page)).length).toBe(1);
  await list.getByLabel("Filter projects").fill("Legacy");
  await expect(list.getByRole("status")).toHaveText("1–1 of 1 matching · 7 total");
  await expect(list.getByText("Page 1 of 1")).toBeVisible();
  expect((await requests(page)).length).toBe(1);
  expect(pageRequests).toBe(2);
  await captureThemes(page, "chat-project-list");
  await page.setViewportSize({ width: 390, height: 844 });
  await captureThemes(page, "chat-project-list-mobile");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await list.getByRole("button", { name: "Know more about Legacy migration" }).click();
  const detail = page.getByRole("region", { name: "Legacy migration project card" });
  await expect(detail).toBeVisible();
  await expect(detail).toContainText("PERSONAL PROJECT");
  await expect(detail).toContainText("Jan 2024 – Present");
  await expect(detail).toContainText("A carefully planned migration");
  await expect(detail.getByLabel("Associated skills")).toContainText("Python");
  const sent = (await requests(page))[1];
  expect(sent.action).toEqual({ type: "show_project", token: "project-7" });
  expect(sent.history[1].components).toEqual([{ type: "project", id: 7, label: "Legacy migration" }]);
  await captureThemes(page, "chat-project-card-mobile");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await captureThemes(page, "chat-project-card");
});

test("job details show the job card and all associated projects with separate introductions", async ({ page }) => {
  const jobs = { type: "job_list", token: "jobs", total: 6, matched_total: 6, page: 1, page_size: 5, filter: "", items: [1, 2, 3, 4, 5].map(jobRecord) };
  const card = { type: "job_card", record: { ...jobRecord(6), responsibilities: "Owned delivery and mentored engineers.", achievements: "Shipped the new platform." } };
  await mockChat(page, [componentReply([jobs]), componentReply([card, projectList()])]);
  await page.route("**/api/chat/components/page", async (route) => {
    await route.fulfill({ json: { ...jobs, page: 2, items: [jobRecord(6)] } });
  });
  await page.goto("/");
  await page.getByLabel("Ask about my career").fill("List all your jobs");
  await page.getByRole("button", { name: "Send message" }).click();
  const list = page.getByRole("region", { name: "Jobs list", exact: true });
  await expect(list.getByRole("row")).toHaveCount(6);
  await list.getByRole("button", { name: "Next" }).click();
  await expect(list.getByRole("status")).toHaveText("6–6 of 6");
  await list.getByRole("button", { name: "Know more about Software engineer 6 at Acme" }).click();
  const answer = page.locator(".chat-turn").last();
  await expect(answer.getByRole("region", { name: "Software engineer 6 job card" })).toContainText("Owned delivery and mentored engineers.");
  await expect(answer.getByRole("region", { name: "Projects list", exact: true })).toBeVisible();
  await expect(answer.locator(".answer-component > .answer-content")).toHaveCount(2);
  expect((await requests(page))[1].action).toEqual({ type: "show_job", token: "job-6" });
  await captureThemes(page, "chat-job-detail");
  for (const width of [320, 390, 768]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test("list errors retry locally and empty filters retain the original scope", async ({ page }) => {
  await mockChat(page, [componentReply([projectList()])]);
  let calls = 0;
  await page.route("**/api/chat/components/page", async (route) => {
    calls++;
    if (calls === 1) await route.fulfill({ status: 503, json: { detail: "Unavailable" } });
    else await route.fulfill({ json: projectList(1, "nothing") });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Projects & impact" }).click();
  const list = page.getByRole("region", { name: "Projects list", exact: true });
  await list.getByLabel("Filter projects").fill("nothing");
  await expect(list.getByRole("alert")).toContainText("could not be loaded");
  await list.getByRole("button", { name: "Try again" }).click();
  await expect(list.getByText("No matches for this filter. Try another word.")).toBeVisible();
  await expect(list.getByRole("status")).toHaveText("0–0 of 0 matching · 7 total");
  expect((await requests(page)).length).toBe(1);
  await list.getByLabel("Filter projects").focus();
  await expect(list.getByLabel("Filter projects")).toBeFocused();
});

test("malformed components fail safely and detail retries retain their record action", async ({ page }) => {
  const malformed = componentReply([{ type: "project_card", record: { id: 7, name: "Invented" } }]);
  await mockChat(page, [componentReply([projectList()]), malformed,
    componentReply([{ type: "project_card", record: { ...projectRecord(1), description: "Current facts", outcomes: "" } }])]);
  await page.goto("/");
  await page.getByRole("button", { name: "Projects & impact" }).click();
  await page.getByRole("button", { name: "Know more about Project 1", exact: true }).click();
  await expect(page.locator(".chat-turn").last().getByRole("alert")).toContainText("interrupted");
  await expect(page.getByRole("region", { name: "Invented project card" })).toHaveCount(0);
  await page.getByRole("button", { name: /Try again/ }).click();
  await expect(page.getByRole("region", { name: "Project 1 project card" })).toContainText("Current facts");
  const sent = await requests(page);
  expect(sent[2].action).toEqual(sent[1].action);
  expect(sent[2].history).toEqual(sent[1].history);
});
