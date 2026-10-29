import { ChatComponentsSettings } from "@/components/admin/chat-components-settings";
import { PageTitle } from "@/components/admin/ui";
import type { RagSettings } from "@/lib/admin";
import { adminData } from "@/lib/admin-server";

export default async function ChatComponentsPage() {
  const settings = await adminData<RagSettings>("settings");
  return <>
    <PageTitle eyebrow="SETTINGS" title="Chat components">Choose how projects and jobs are presented in the conversation.</PageTitle>
    <ChatComponentsSettings initial={settings.chat_components} />
  </>;
}
