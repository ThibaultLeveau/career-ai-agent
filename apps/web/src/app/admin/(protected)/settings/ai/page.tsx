import { AISettings } from "@/components/admin/ai-settings";
import { PageTitle } from "@/components/admin/ui";
import { type ProviderStatus, type RagSettings } from "@/lib/admin";
import { adminData } from "@/lib/admin-server";

export default async function AIPage() {
  const [settings, providers] = await Promise.all([
    adminData<RagSettings>("settings"),
    adminData<ProviderStatus[]>("providers"),
  ]);
  return (
    <>
      <PageTitle eyebrow="SETTINGS" title="AI & RAG">
        Choose your models. Shape how your portfolio thinks.
      </PageTitle>
      <AISettings initial={settings} initialProviders={providers} />
    </>
  );
}
