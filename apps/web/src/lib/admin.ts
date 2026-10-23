export type Provider = "openai" | "anthropic";
export type Stage = "chat" | "embeddings" | "reranking";
export type Generation = {
  provider: Provider;
  model: string;
  max_output_tokens: number;
};
export type RagSettings = {
  chat: Generation & { system_prompt: string };
  embeddings: {
    provider: "openai";
    model: "text-embedding-3-small" | "text-embedding-3-large";
    dimensions: number;
  };
  reranking: Generation & { enabled: boolean };
  retrieval: {
    candidate_count: number;
    context_count: number;
    chunk_size: number;
    chunk_overlap: number;
  };
};
export type ProviderStatus = { provider: Provider; configured: boolean };
export const providerNames: Record<Provider, string> = {
  openai: "OpenAI",
  anthropic: "Claude / Anthropic",
};

export async function adminRequest<T = undefined>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/admin/${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (response.status === 401 && path !== "login") {
    reloadAdmin("/admin/login");
    throw new Error("Your session expired. Please sign in again.");
  }
  const data = response.status === 204 ? undefined : await response.json();
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item: { msg: string }) => item.msg).join(". ")
          : "Something went wrong. Please try again.",
    );
  }
  return data as T;
}

export function reloadAdmin(path: "/admin" | "/admin/login") {
  window.location.replace(new URL(path, window.location.origin));
}
