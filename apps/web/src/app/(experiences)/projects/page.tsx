import type { Metadata } from "next";
import { Suspense } from "react";
import { ExperienceCatalog } from "@/components/experiences/catalog";
import { LoadingExperiences } from "@/components/experiences/loading";
import type { CareerSearchParams } from "@/lib/public-career";

export const metadata: Metadata = { title: "Projects | Thibault Leveau", description: "Explore Thibault Leveau’s professional and personal projects, contributions, outcomes, and the skills behind the work." };

export default async function ProjectsPage({ searchParams }: { searchParams: Promise<CareerSearchParams> }) {
  return <Suspense fallback={<LoadingExperiences />}><ExperienceCatalog collection="projects" searchParams={await searchParams} /></Suspense>;
}
