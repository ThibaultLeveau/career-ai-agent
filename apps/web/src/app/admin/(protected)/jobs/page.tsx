import { JobsList } from "@/components/admin/content/lists";
import { PageTitle } from "@/components/admin/ui";
import { adminData } from "@/lib/admin-server";
import type { Job } from "@/lib/content";

export default async function Page() {
  const records = await adminData<Job[]>("jobs");

  return (
    <div className="admin-content">
      <PageTitle eyebrow="WORKSPACE" title="Jobs">
        Your roles, responsibilities, and achievements.
      </PageTitle>
      <JobsList jobs={records} />
    </div>
  );
}
