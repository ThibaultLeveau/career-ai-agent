import { expect, test, type Page } from "@playwright/test";
import { captureThemes, expectTheme, setTheme } from "./theme";

type ChatRequest = {
  message: string;
  history: { role: "user" | "assistant"; content: string }[];
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
  await expect(page.locator(".answer-content")).toContainText('<script>alert("unsafe")</script>');
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
