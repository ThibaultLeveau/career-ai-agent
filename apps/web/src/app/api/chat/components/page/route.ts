import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
const apiUrl = process.env.API_INTERNAL_URL ?? "http://api:8000";
const headers = { "Cache-Control": "no-store" };

export async function POST(request: NextRequest) {
  if (!request.headers.get("content-type")?.includes("application/json"))
    return Response.json({ detail: "Send the list request as JSON." }, { status: 415, headers });
  const reader = request.body?.getReader();
  if (!reader) return Response.json({ detail: "A list reference is required." }, { status: 400, headers });
  const signal = AbortSignal.any([request.signal, AbortSignal.timeout(15000)]);
  const cancel = () => { void reader.cancel().catch(() => undefined); };
  signal.addEventListener("abort", cancel, { once: true });
  try {
    const chunks: Uint8Array[] = [];
    let size = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (signal.aborted) throw new Error("Request interrupted");
      if (done) break;
      size += value.byteLength;
      if (size > 256 * 1024) {
        await reader.cancel();
        return Response.json({ detail: "This list request is too large." }, { status: 413, headers });
      }
      chunks.push(value);
    }
    const body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { body.set(chunk, offset); offset += chunk.byteLength; }
    const response = await fetch(`${apiUrl}/chat/components/page`, {
      method: "POST", headers: { "Content-Type": "application/json", Origin: request.headers.get("origin") ?? "" },
      body, signal, redirect: "error", cache: "no-store",
    });
    return new Response(await response.arrayBuffer(), {
      status: response.status, headers: { ...headers, "Content-Type": "application/json" },
    });
  } catch {
    return Response.json({ detail: "This list could not be loaded. Please try again." }, { status: 503, headers });
  } finally {
    signal.removeEventListener("abort", cancel);
    reader.releaseLock();
  }
}
