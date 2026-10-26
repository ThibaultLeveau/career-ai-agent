import { IngestionJobs } from "@/components/admin/ingestion-jobs";
import { PageTitle } from "@/components/admin/ui";

export default async function IngestionPage({
  searchParams,
}: {
  searchParams: Promise<{ job?: string }>;
}) {
  const { job } = await searchParams;
  const id = job && /^[1-9]\d*$/.test(job) ? Number(job) : undefined;
  return (
    <div className="admin-content">
      <PageTitle eyebrow="WORKSPACE" title="Ingestion Jobs">
        Follow content ingestion, inspect logs, and rebuild your knowledge base.
      </PageTitle>
      <IngestionJobs initialJobId={id} />
    </div>
  );
}
