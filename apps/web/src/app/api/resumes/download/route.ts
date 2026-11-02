import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
const apiUrl = process.env.API_INTERNAL_URL ?? "http://api:8000";
const headers = { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };

export async function GET(request: NextRequest) {
  const token = request.nextUrl.searchParams.get("token");
  if (!token || token.length > 2048) {
    return Response.json({ detail: "This resume is no longer available." }, { status: 404, headers });
  }
  try {
    const upstream = await fetch(`${apiUrl}/public/resumes/download?${new URLSearchParams({ token })}`, {
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(30_000)]),
    });
    if (!upstream.ok) {
      await upstream.body?.cancel();
      return Response.json({ detail: upstream.status === 404
        ? "This resume is no longer available. Please ask for a current resume."
        : "The resume could not be downloaded. Please try again." },
      { status: upstream.status === 404 ? 404 : 503, headers });
    }
    if (upstream.headers.get("content-type")?.split(";")[0] !== "application/pdf") {
      await upstream.body?.cancel();
      throw new Error("Invalid resume response");
    }
    const responseHeaders = new Headers(headers);
    responseHeaders.set("Content-Type", "application/pdf");
    responseHeaders.set("Content-Disposition", upstream.headers.get("content-disposition") ?? "attachment; filename=resume.pdf");
    return new Response(upstream.body, { headers: responseHeaders });
  } catch {
    return Response.json({ detail: "The resume could not be downloaded. Please try again." },
      { status: 503, headers });
  }
}
