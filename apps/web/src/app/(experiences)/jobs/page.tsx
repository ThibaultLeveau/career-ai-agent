import type { Metadata } from "next";
import { Suspense } from "react";
import { ExperienceCatalog } from "@/components/experiences/catalog";
import { LoadingExperiences } from "@/components/experiences/loading";
import type { CareerSearchParams } from "@/lib/public-career";

export const metadata: Metadata = { title: "Jobs | Thibault Leveau", description: "Explore Thibault Leveau’s professional experience, responsibilities, achievements, and the projects behind each role." };

export default async function JobsPage({ searchParams }: { searchParams: Promise<CareerSearchParams> }) {
  return <Suspense fallback={<LoadingExperiences />}><ExperienceCatalog collection="jobs" searchParams={await searchParams} /></Suspense>;
}
