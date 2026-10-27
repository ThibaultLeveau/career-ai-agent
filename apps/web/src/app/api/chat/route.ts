import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
const apiUrl = process.env.API_INTERNAL_URL ?? "http://api:8000";
const headers = { "Cache-Control": "no-store, no-transform" };

export async function POST(request: NextRequest) {
  if (!request.headers.get("content-type")?.includes("application/json")) {
    return Response.json(
      { detail: "Send your message as JSON." },
      { status: 415, headers },
    );
  }
  const controller = new AbortController();
  const timeout = AbortSignal.timeout(180000);
  const signal = AbortSignal.any([request.signal, controller.signal, timeout]);
  try {
    const chunks: Uint8Array[] = [];
    let size = 0;
    if (request.body) {
      const reader = request.body.getReader();
      const cancelReading = () => { void reader.cancel().catch(() => undefined); };
      signal.addEventListener("abort", cancelReading, { once: true });
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (signal.aborted) throw new Error("Request interrupted");
          if (done) break;
          size += value.byteLength;
          if (size > 65536) {
            await reader.cancel();
            return Response.json(
              { detail: "This conversation is too long. Start a new conversation." },
              { status: 413, headers },
            );
          }
          chunks.push(value);
        }
      } finally {
        signal.removeEventListener("abort", cancelReading);
        reader.releaseLock();
      }
    }
    const body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.byteLength;
    }
    const upstream = await fetch(`${apiUrl}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Origin: request.headers.get("origin") ?? "",
      },
      body,
      cache: "no-store",
      redirect: "error",
      signal,
    });
    const responseHeaders = new Headers(headers);
    responseHeaders.set(
      "Content-Type",
      upstream.headers.get("content-type") ?? "application/json",
    );
    responseHeaders.set("X-Accel-Buffering", "no");
    const retryAfter = upstream.headers.get("retry-after");
    if (retryAfter) responseHeaders.set("Retry-After", retryAfter);
    const reader = upstream.body?.getReader();
    const stream = reader
      ? new ReadableStream<Uint8Array>({
          async pull(output) {
            try {
              const { done, value } = await reader.read();
              if (done) {
                reader.releaseLock();
                output.close();
              } else {
                output.enqueue(value);
              }
            } catch (error) {
              output.error(error);
            }
          },
          async cancel(reason) {
            controller.abort(reason);
            await reader.cancel(reason).catch(() => undefined);
          },
        })
      : null;
    return new Response(stream, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    controller.abort();
    return Response.json(
      {
        detail: timeout.aborted
          ? "The response took too long. Please try again."
          : "My career assistant is temporarily unavailable. Please try again shortly.",
      },
      { status: timeout.aborted ? 504 : 503, headers },
    );
  }
}
