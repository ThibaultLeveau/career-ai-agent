import { CredentialsForm } from "@/components/admin/credentials";
import { PageTitle } from "@/components/admin/ui";
import { adminData } from "@/lib/admin-server";

export default async function SettingsPage() {
  const session = await adminData<{ username: string }>("session");
  return (
    <>
      <PageTitle eyebrow="SETTINGS" title="Account & security">
        Your workspace. Your credentials.
      </PageTitle>
      <CredentialsForm username={session.username} />
    </>
  );
}
