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
  status: "pending" | "complete" | "stopped" | "error";
  sources: ChatSource[];
  error?: string;
};

type ChatMessage = { role: "user" | "assistant"; content: string };

export function completedHistory(turns: ChatTurn[]): ChatMessage[] {
  const pairs = turns
    .filter((turn) => turn.status === "complete")
    .slice(-4)
    .map((turn): ChatMessage[] => [
      { role: "user", content: turn.question },
      { role: "assistant", content: turn.answer.slice(0, 8000) },
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
