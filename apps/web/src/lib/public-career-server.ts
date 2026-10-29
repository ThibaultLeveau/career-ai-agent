import "server-only";

import { cache } from "react";
import { notFound } from "next/navigation";
import type { PublicJobDetail, PublicProjectDetail } from "./public-career";

const apiUrl = process.env.API_INTERNAL_URL ?? "http://api:8000";

export async function publicCareerData<T>(path: string): Promise<T> {
  const response = await fetch(`${apiUrl}/public/${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  if (response.status === 404) notFound();
  if (!response.ok) throw new Error("Experiences could not be loaded. Please try again.");
  return response.json() as Promise<T>;
}

function recordId(value: string) {
  if (!/^[1-9]\d*$/.test(value) || !Number.isSafeInteger(Number(value))) notFound();
  return value;
}

export const publicJob = cache((id: string) => publicCareerData<PublicJobDetail>(`jobs/${recordId(id)}`));
export const publicProject = cache((id: string) => publicCareerData<PublicProjectDetail>(`projects/${recordId(id)}`));
