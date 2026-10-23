import { SettingsNavigation } from "@/components/admin/settings-navigation";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="settings-layout">
      <SettingsNavigation />
      <div className="admin-content">{children}</div>
    </div>
  );
}
