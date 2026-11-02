import { expect, test, type Page } from "@playwright/test";

type StreamWindow = Window & { pushChatEvent: (name: string, payload: unknown) => void };

async function controlledChat(page: Page) {
  await page.addInitScript(() => {
    const original = window.fetch.bind(window);
    window.fetch = async (url, init) => {
      if (String(url) !== "/api/chat") return original(url, init);
      let closed = false;
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          (window as unknown as StreamWindow).pushChatEvent = (name, payload) => {
            controller.enqueue(new TextEncoder().encode(`event: ${name}\ndata: ${JSON.stringify(payload)}\n\n`));
            if (name === "done") { closed = true; controller.close(); }
          };
          init?.signal?.addEventListener("abort", () => {
            if (!closed) { closed = true; controller.error(new DOMException("Aborted", "AbortError")); }
          });
        },
        cancel() { closed = true; },
      });
      return new Response(stream, { headers: { "Content-Type": "text/event-stream" } });
    };
  });
}

async function push(page: Page, name: string, payload: unknown) {
  await page.evaluate(({ name, payload }) => (window as unknown as StreamWindow).pushChatEvent(name, payload), { name, payload });
}

const project = {
  id: 1, name: "Python delivery platform", role: "Engineer", kind: "personal", job: null,
  start_month: "2024-01", end_month: null, ongoing: true, summary: "Built useful Python tools.",
  skills: ["Python"], action: { type: "show_project", token: "project-1" },
};
const list = {
  type: "project_list", token: "projects", total: 2, matched_total: 2,
  page: 1, page_size: 1, filter: "", items: [project],
};
const card = { type: "project_card", record: { ...project, description: "Delivered the platform.", outcomes: "Improved reliability." } };

test("desktop keeps the streamed answer end visible when results narrow the transcript", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await controlledChat(page);
  await page.goto("/");
  await page.getByLabel("Ask about my career").fill("I need a Python AI engineer building RAG applications and FastAPI services. Are you a good candidate?");
  await page.getByLabel("Ask about my career").press("Enter");
  await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
  const transcript = page.getByRole("log", { name: "Conversation" });
  const atBottom = async () => {
    await expect.poll(() => transcript.evaluate((element) => element.scrollHeight - element.clientHeight - element.scrollTop)).toBeLessThanOrEqual(1);
  };
  const answer = "**Yes—I’m a strong candidate for your Python, RAG, and FastAPI requirements.** My demonstrated work covers all three; production-scale performance remains unquantified.\n\n**Direct experience**\n\n- Python AI backends integrating AWS Bedrock LLMs.\n- RAG ingestion, embeddings, PostgreSQL/pgvector, and hybrid retrieval.\n- Context expansion, reranking, and multi-agent retrieval workflows.\n- FastAPI copy server with secure token-based downloads.\n- RAG evaluation benchmarks measuring quality and regressions.\n\n**Transferable strengths**\n\nI’ve connected AI retrieval to authenticated APIs and engineering workflows, supporting practical application delivery.\n\nMy documentation generator saves engineers approximately one working day per use.\n\n**Evidence gaps**\n\nAvailable evidence doesn’t quantify service throughput, latency, availability, or deployment scale.";
  const resume = {
    type: "resume_download", id: 72, title: "Resume Python Backend", filename: "resume.pdf", size: 248832, token: "resume-token",
  };
  await page.evaluate(async ({ answer, list, resume }) => {
    const stream = window as unknown as StreamWindow;
    for (const text of answer.match(/[\s\S]{1,24}/g)!) {
      stream.pushChatEvent("delta", { text });
      await new Promise(requestAnimationFrame);
    }
    stream.pushChatEvent("component", { introduction: "These selected projects demonstrate my Python AI development, RAG implementation, and FastAPI service experience.", component: list });
    await new Promise(requestAnimationFrame);
    stream.pushChatEvent("component", { introduction: "You can download my resume here.", component: resume });
    stream.pushChatEvent("done", { sources: [{ id: "S1", label: "Career resume", source_type: "document", page_start: 1, page_end: 1 }] });
  }, { answer, list, resume });
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
  await atBottom();
  const composer = (await page.locator(".chat-composer").boundingBox())!;
  const resumeBounds = (await transcript.getByRole("button", { name: "Download Resume", exact: true }).boundingBox())!;
  const sourcesBounds = (await transcript.locator(".chat-sources").boundingBox())!;
  expect(resumeBounds.y + resumeBounds.height).toBeLessThanOrEqual(composer.y);
  expect(sourcesBounds.y + sourcesBounds.height).toBeLessThanOrEqual(composer.y);
});

test("desktop transcript follows streaming until the reader scrolls away", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await controlledChat(page);
  await page.goto("/");
  await page.getByRole("button", { name: "The career overview" }).click();
  await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
  await push(page, "delta", { text: Array.from({ length: 60 }, (_, index) => `Career example ${index + 1}.`).join("\n\n") });
  const transcript = page.getByRole("log", { name: "Conversation" });
  await expect.poll(() => transcript.evaluate((element) => element.scrollTop)).toBeGreaterThan(500);
  await transcript.evaluate(async (element) => {
    element.scrollTop = 0;
    await new Promise(requestAnimationFrame);
    await new Promise(requestAnimationFrame);
  });
  await push(page, "delta", { text: "\n\nA final streamed example." });
  await expect(transcript).toContainText("A final streamed example.");
  expect(await transcript.evaluate((element) => element.scrollTop)).toBe(0);
  await push(page, "done", { sources: [] });
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
  expect(await transcript.evaluate((element) => element.scrollTop)).toBe(0);
  const composer = (await page.locator(".chat-composer").boundingBox())!;
  expect(composer.height).toBeGreaterThanOrEqual(64);
  expect(composer.height).toBeLessThanOrEqual(76);
  expect(composer.y + composer.height).toBeLessThanOrEqual(768);
});

test("streamed results preserve list state, input focus, and an earlier result selection", async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 768 });
  await controlledChat(page);
  await page.route("**/api/chat/components/page", (route) => route.fulfill({
    json: { ...list, filter: "Python", matched_total: 1 },
  }));
  await page.goto("/");
  await page.getByRole("button", { name: "Projects & impact" }).click();
  await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
  await push(page, "delta", { text: "I build practical engineering tools." });
  await push(page, "component", { introduction: "Explore these projects.", component: list });
  const pane = page.getByRole("complementary", { name: "Related work" });
  const filter = pane.getByLabel("Filter projects");
  await filter.fill("Python");
  await expect(pane.getByRole("status")).toHaveText("1–1 of 1 matching · 2 total");
  await expect(filter).toBeFocused();
  await push(page, "component", { introduction: "Here is one example.", component: card });
  await expect(pane.getByRole("region", { name: `${project.name} project card` })).toBeVisible();
  await expect(filter).toHaveValue("Python");
  await expect(filter).toBeFocused();
  await expect(pane.getByRole("status")).toHaveText("1–1 of 1 matching · 2 total");
  await push(page, "done", { sources: [] });
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();

  await page.getByLabel("Ask about my career").fill("Show another project.");
  await page.getByLabel("Ask about my career").press("Enter");
  await expect(page.getByRole("button", { name: "Stop response" })).toBeVisible();
  await page.getByRole("button", { name: "View results" }).click();
  await expect(pane.getByRole("heading", { name: "Related work" })).toBeFocused();
  await push(page, "component", { introduction: "Another example.", component: card });
  await expect(pane).toHaveAttribute("data-turn-id", "1");
  await expect(pane.locator(".chat-results-question")).toHaveText("Which projects best show the impact of your work?");
  await expect(pane.getByRole("heading", { name: "Related work" })).toBeFocused();
  await pane.getByRole("button", { name: "Latest results" }).click();
  await expect(pane).toHaveAttribute("data-turn-id", "2");
  await expect(pane.locator(".chat-results-question")).toHaveText("Show another project.");
  await push(page, "done", { sources: [] });
});
