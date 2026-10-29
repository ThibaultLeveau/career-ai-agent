import type { Metadata } from "next";
import { ProjectExperienceDetail } from "@/components/experiences/details";
import { publicProject } from "@/lib/public-career-server";
import { returnHref, type CareerSearchParams } from "@/lib/public-career";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<CareerSearchParams> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const project = await publicProject((await params).id);
  return { title: `${project.name} | Thibault Leveau`, description: `Explore ${project.name}: Thibault Leveau’s role, contributions, outcomes, and the skills behind the project.` };
}

export default async function ProjectPage({ params, searchParams }: Props) {
  const [project, query] = await Promise.all([params.then(({ id }) => publicProject(id)), searchParams]);
  return <ProjectExperienceDetail project={project} back={returnHref("projects", query.from)} />;
}
