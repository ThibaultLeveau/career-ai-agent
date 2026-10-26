import { JobForm } from "@/components/admin/content/job-form";
import { PageTitle } from "@/components/admin/ui";
import Link from "next/link";

export default async function Page() {
  return (
    <div className="admin-content">
      <Link className="back-link" href="/admin/jobs">
        ← Jobs
      </Link>
      <PageTitle eyebrow="JOBS" title="New job">
        Add your job details.
      </PageTitle>
      <JobForm />
    </div>
  );
}
