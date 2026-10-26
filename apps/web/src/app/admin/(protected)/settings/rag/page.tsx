import { RAGSettings } from "@/components/admin/rag-settings";
import { PageTitle } from "@/components/admin/ui";
import type { RagSettings } from "@/lib/admin";
import { adminData } from "@/lib/admin-server";

export default async function RAGPage() {
  const settings = await adminData<RagSettings>("settings");
  return (
    <>
      <PageTitle eyebrow="SETTINGS" title="RAG">
        Configure retrieval and content ingestion.
      </PageTitle>
      <RAGSettings initial={settings} />
    </>
  );
}
