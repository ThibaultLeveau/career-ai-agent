import { NextRequest } from "next/server";
import { apiUrl } from "@/lib/admin-server";

export const dynamic = "force-dynamic";
const allowedPath =
  /^(login|logout|session|overview|credentials|settings|agents\/defaults|providers(?:\/(?:openai|anthropic))?|test\/(?:chat|embeddings|reranking|query_analyzer|database|rag|representative)|(?:jobs|projects|skills)(?:\/[1-9]\d*)?|ingestion\/(?:status|reingest|jobs(?:\/[1-9]\d*(?:\/logs)?)?|(?:jobs|projects|documents)\/[1-9]\d*\/reingest)|documents(?:\/[1-9]\d*(?:\/file)?)?)$/;

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = (await context.params).path.join("/");
  if (!allowedPath.test(path)) return new Response(null, { status: 404 });
  const query = new URLSearchParams();
  if (path.startsWith("ingestion/")) {
    for (const [key, value] of request.nextUrl.searchParams) {
      if (
        !["source_type", "status", "offset", "limit", "after_id"].includes(key)
      )
        return Response.json(
          { detail: "Unsupported query parameter" },
          { status: 400 },
        );
      query.set(key, value);
    }
  }
  const session = request.cookies.get("career_admin");
  try {
    let body: ArrayBuffer | undefined;
    if (request.method !== "GET" && request.body) {
      const limit = /^documents(?:\/\d+)?$/.test(path)
        ? 11 * 1024 * 1024
        : path === "settings" || path.startsWith("test/")
          ? 384 * 1024
          : 65536;
      const reader = request.body.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > limit) {
          await reader.cancel();
          return Response.json(
            {
              detail:
                /^documents(?:\/\d+)?$/.test(path)
                  ? "Request is too large. PDF files must be 10 MiB or smaller."
                  : "The settings request is too large.",
            },
            { status: 413, headers: { "Cache-Control": "no-store" } },
          );
        }
        chunks.push(value);
      }
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
      }
      body = bytes.buffer;
    }
    const upstream = await fetch(
      `${apiUrl}/admin/${path}${query.size ? `?${query}` : ""}`,
      {
        method: request.method,
        headers: {
          "Content-Type":
            request.headers.get("content-type") ?? "application/json",
          Origin: request.headers.get("origin") ?? "",
          Cookie: session ? `career_admin=${session.value}` : "",
        },
        body,
        cache: "no-store",
        redirect: "manual",
        signal: AbortSignal.timeout(35000),
      },
    );
    const headers = new Headers({ "Cache-Control": "no-store" });
    for (const name of [
      "Content-Type",
      "Content-Disposition",
      "X-Content-Type-Options",
    ]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie())
      headers.append("Set-Cookie", cookie);
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch {
    return Response.json(
      {
        detail: "The administration service is unavailable. Try again shortly.",
      },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as DELETE,
  proxy as PATCH,
};
