import { NextRequest } from "next/server";
import { apiUrl } from "@/lib/admin-server";

export const dynamic = "force-dynamic";
const allowedPath =
  /^(login|logout|session|credentials|settings|providers(?:\/(?:openai|anthropic))?|test\/(?:chat|embeddings|reranking))$/;

async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = (await context.params).path.join("/");
  if (!allowedPath.test(path)) return new Response(null, { status: 404 });
  const body = request.method === "GET" ? undefined : await request.text();
  if (body && body.length > 65536) return new Response(null, { status: 413 });
  const session = request.cookies.get("career_admin");
  try {
    const upstream = await fetch(`${apiUrl}/admin/${path}`, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        Origin: request.headers.get("origin") ?? "",
        Cookie: session ? `career_admin=${session.value}` : "",
      },
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(35000),
    });
    const headers = new Headers({
      "Cache-Control": "no-store",
      "Content-Type": "application/json",
    });
    for (const cookie of upstream.headers.getSetCookie())
      headers.append("Set-Cookie", cookie);
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch {
    return Response.json(
      {
        detail: "The administration service is unavailable. Try again shortly.",
      },
      { status: 503 },
    );
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
