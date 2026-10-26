import { Overview, type OverviewData } from "@/components/admin/overview";
import { PageTitle } from "@/components/admin/ui";
import { adminData } from "@/lib/admin-server";

export default async function HomePage() {
  const overview = await adminData<OverviewData>("overview");
  return (
    <div className="admin-content">
      <PageTitle eyebrow="WORKSPACE" title="Overview">
        Your experience, projects and knowledge base at a glance.
      </PageTitle>
      <Overview initial={overview} />
    </div>
  );
}
