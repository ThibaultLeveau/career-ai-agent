import type { Metadata } from "next";
import { JobExperienceDetail } from "@/components/experiences/details";
import { publicJob } from "@/lib/public-career-server";
import { returnHref, type CareerSearchParams } from "@/lib/public-career";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<CareerSearchParams> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const job = await publicJob((await params).id);
  return { title: `${job.title} at ${job.company} | Thibault Leveau`, description: `Explore Thibault Leveau’s work as ${job.title} at ${job.company}, including responsibilities, achievements, and related projects.` };
}

export default async function JobPage({ params, searchParams }: Props) {
  const [job, query] = await Promise.all([params.then(({ id }) => publicJob(id)), searchParams]);
  return <JobExperienceDetail job={job} back={returnHref("jobs", query.from)} />;
}
