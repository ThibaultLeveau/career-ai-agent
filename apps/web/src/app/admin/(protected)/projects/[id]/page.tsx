import { ProjectForm } from "@/components/admin/content/project-form";
import { PageTitle } from "@/components/admin/ui";
import Link from "next/link";
import { adminData } from "@/lib/admin-server";
import type { Job, Project, Skill } from "@/lib/content";
import { notFound } from "next/navigation";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^[1-9]\d*$/.test(id)) notFound();
  const record = await adminData<Project>(`projects/${id}`);
  const [jobs, skills] = await Promise.all([
    adminData<Job[]>("jobs"),
    adminData<Skill[]>("skills"),
  ]);
  return (
    <div className="admin-content">
      <Link className="back-link" href="/admin/projects">
        ← Projects
      </Link>
      <PageTitle eyebrow="PROJECTS" title="Edit project">
        Update your project details.
      </PageTitle>
      <ProjectForm project={record} jobs={jobs} skills={skills} />
    </div>
  );
}
