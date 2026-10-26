import "server-only";
import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

export const apiUrl = process.env.API_INTERNAL_URL ?? "http://api:8000";

export async function adminData<T>(path: string): Promise<T> {
  const session = (await cookies()).get("career_admin");
  const response = await fetch(`${apiUrl}/admin/${path}`, {
    headers: { Cookie: session ? `career_admin=${session.value}` : "" },
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
  });
  if (response.status === 401) redirect("/admin/login");
  if (response.status === 404) notFound();
  if (!response.ok)
    throw new Error("The administration service is unavailable.");
  return response.json() as Promise<T>;
}
