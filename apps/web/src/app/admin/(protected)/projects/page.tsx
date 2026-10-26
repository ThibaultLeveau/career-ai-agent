import { ProjectsList } from "@/components/admin/content/lists";
import { PageTitle } from "@/components/admin/ui";
import { adminData } from "@/lib/admin-server";
import type { Project, Job } from "@/lib/content";

export default async function Page() {
  const records = await adminData<Project[]>("projects");
  const jobs = await adminData<Job[]>("jobs");
  return (
    <div className="admin-content">
      <PageTitle eyebrow="WORKSPACE" title="Projects">
        The work you built and the skills behind it.
      </PageTitle>
      <ProjectsList projects={records} jobs={jobs} />
    </div>
  );
}
