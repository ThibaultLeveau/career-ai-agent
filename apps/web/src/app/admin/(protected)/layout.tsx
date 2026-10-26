import { AdminShell } from "@/components/admin/shell";
import { adminData } from "@/lib/admin-server";

export default async function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await adminData<{ username: string }>("session");
  return <AdminShell username={session.username}>{children}</AdminShell>;
}
