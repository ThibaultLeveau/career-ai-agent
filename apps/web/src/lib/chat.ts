import { componentReferences, isComponentEvent, type ChatBlock, type ComponentEvent, type ComponentReference, type DetailAction } from "./chat-components";

export type ChatSource = {
  id: string;
  label: string;
  source_type: "job" | "project" | "document";
  page_start: number | null;
  page_end: number | null;
};

export type ChatTurn = {
  id: number;
  question: string;
  answer: string;
  blocks: ChatBlock[];
  action?: DetailAction;
  status: "pending" | "complete" | "stopped" | "error";
  sources: ChatSource[];
  error?: string;
  activity?: ChatActivity;
};

export type AgentActivity = {
  id: string;
  agent: string;
  message: string;
  state: "running" | "complete" | "error";
};

export type ChatActivity = { stage: string; message: string; activities?: AgentActivity[] };

export function chatActivityRows(activity?: ChatActivity, writing = false): AgentActivity[] {
  if (activity?.activities) return activity.activities;
  const stage = activity?.stage ?? (writing ? "answering" : "analyzing");
  const agent = ["database", "fallback", "related"].includes(stage) ? "Database Agents"
    : stage === "rag" ? "RAG Agents"
      : stage === "answering" ? "Answer Agent"
        : stage === "analyzing" ? "Query Analyzer Agent" : "Assistant";
  return [{
    id: stage === "analyzing" ? "analyzer" : stage === "answering" ? "answer" : stage,
    agent,
    message: activity?.message ?? (writing ? "Writing your answer…" : "Understanding your question…"),
    state: "running",
  }];
}

export function chatActivityAnnouncement(activity?: ChatActivity, writing = false): string {
  const running = chatActivityRows(activity, writing).filter((item) => item.state === "running");
  return (running.length > 1 ? "Working in parallel. " : "")
    + running.map((item) => `${item.agent}: ${item.message}`).join(" ");
}

type ChatMessage = { role: "user" | "assistant"; content: string; components?: ComponentReference[] };

export function completedHistory(turns: ChatTurn[]): ChatMessage[] {
  const pairs = turns
    .filter((turn) => turn.status === "complete")
    .slice(-4)
    .map((turn): ChatMessage[] => [
      { role: "user", content: turn.question },
      {
        role: "assistant", content: turn.answer.slice(0, 8000),
        ...(turn.blocks.some((block) => block.type === "component") ? {
          components: turn.blocks.flatMap((block) => block.type === "component"
            ? componentReferences(block.component) : []).slice(0, 80),
        } : {}),
      },
    ]);
  while (
    pairs.flat().reduce((total, message) => total + message.content.length, 0) >
    24000
  ) {
    pairs.shift();
  }
  return pairs.flat();
}

const interrupted = "The connection was interrupted. Please try again.";

function boundedText(value: unknown, maximum: number): value is string {
  return typeof value === "string" && value.trim().length > 0 && value.length <= maximum;
}

function isAgentActivity(value: unknown): value is AgentActivity {
  if (typeof value !== "object" || value === null) return false;
  const activity = value as Record<string, unknown>;
  return boundedText(activity.id, 64)
    && boundedText(activity.agent, 80)
    && boundedText(activity.message, 500)
    && typeof activity.state === "string"
    && ["running", "complete", "error"].includes(activity.state);
}

function isChatActivity(item: Record<string, unknown>): item is ChatActivity {
  return boundedText(item.stage, 64) && boundedText(item.message, 500)
    && (!("activities" in item) || (Array.isArray(item.activities)
      && item.activities.length <= 8
      && item.activities.every(isAgentActivity)
      && new Set(item.activities.map((activity) => activity.id)).size === item.activities.length));
}

function isSource(value: unknown): value is ChatSource {
  if (typeof value !== "object" || value === null) return false;
  const source = value as Record<string, unknown>;
  return (
    typeof source.id === "string" &&
    typeof source.label === "string" &&
    ["job", "project", "document"].includes(String(source.source_type)) &&
    (source.page_start === null || Number.isInteger(source.page_start)) &&
    (source.page_end === null || Number.isInteger(source.page_end))
  );
}

export async function readChatStream(
  response: Response,
  onDelta: (text: string) => void,
  onStatus?: (activity: ChatActivity) => void,
  onComponent?: (component: ComponentEvent) => void,
): Promise<ChatSource[]> {
  if (
    !response.body ||
    !response.headers.get("content-type")?.includes("text/event-stream")
  ) {
    throw new Error(interrupted);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer)) !== null) {
        const frame = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        let event = "message";
        const data: string[] = [];
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
        }
        if (!data.length) continue;
        const payload: unknown = JSON.parse(data.join("\n"));
        if (typeof payload !== "object" || payload === null)
          throw new Error(interrupted);
        const item = payload as Record<string, unknown>;
        if (event === "delta" && typeof item.text === "string") {
          onDelta(item.text);
        } else if (event === "component" && isComponentEvent(item)) {
          onComponent?.(item);
        } else if (event === "status" && isChatActivity(item)) {
          onStatus?.({
            stage: item.stage,
            message: item.message,
            ...(item.activities ? { activities: item.activities } : {}),
          });
        } else if (
          event === "done" &&
          Array.isArray(item.sources) &&
          item.sources.every(isSource)
        ) {
          return item.sources;
        } else if (event === "error" && typeof item.message === "string") {
          throw new Error(item.message);
        } else {
          throw new Error(interrupted);
        }
      }
      if (done) throw new Error(interrupted);
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
