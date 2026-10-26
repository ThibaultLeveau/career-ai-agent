import { ProjectForm } from "@/components/admin/content/project-form";
import { PageTitle } from "@/components/admin/ui";
import Link from "next/link";
import { adminData } from "@/lib/admin-server";
import type { Job, Skill } from "@/lib/content";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ job?: string }>;
}) {
  const [jobs, skills] = await Promise.all([
    adminData<Job[]>("jobs"),
    adminData<Skill[]>("skills"),
  ]);
  const jobId = Number((await searchParams).job);
  return (
    <div className="admin-content">
      <Link className="back-link" href="/admin/projects">
        ← Projects
      </Link>
      <PageTitle eyebrow="PROJECTS" title="New project">
        Add your project details.
      </PageTitle>
      <ProjectForm
        jobs={jobs}
        skills={skills}
        jobId={jobs.some((job) => job.id === jobId) ? jobId : undefined}
      />
    </div>
  );
}
