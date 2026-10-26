import { JobForm } from "@/components/admin/content/job-form";
import { PageTitle } from "@/components/admin/ui";
import Link from "next/link";
import { adminData } from "@/lib/admin-server";
import type { Job, Project } from "@/lib/content";
import { notFound } from "next/navigation";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^[1-9]\d*$/.test(id)) notFound();
  const record = await adminData<Job>(`jobs/${id}`);
  const projects = (await adminData<Project[]>("projects")).filter(
    (project) => project.job_id === record.id,
  );
  return (
    <div className="admin-content">
      <Link className="back-link" href="/admin/jobs">
        ← Jobs
      </Link>
      <PageTitle eyebrow="JOBS" title="Edit job">
        Update your job details.
      </PageTitle>
      <JobForm job={record} projects={projects} />
    </div>
  );
}
