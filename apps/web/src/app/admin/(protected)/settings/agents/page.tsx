import { AgentsSettingsForm } from "@/components/admin/agents-settings";
import { PageTitle } from "@/components/admin/ui";
import type { AgentsSettings, RagSettings } from "@/lib/admin";
import { adminData } from "@/lib/admin-server";

export default async function AgentsPage() {
  const [settings, defaults] = await Promise.all([
    adminData<RagSettings>("settings"),
    adminData<AgentsSettings>("agents/defaults"),
  ]);
  return <>
    <PageTitle eyebrow="SETTINGS" title="Agents">Choose how the assistant investigates questions and represents your experience.</PageTitle>
    <AgentsSettingsForm initial={settings} defaults={defaults} />
  </>;
}
